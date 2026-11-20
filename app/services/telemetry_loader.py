import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("telemetry-loader")

_CACHED_INITIAL_PAYLOADS: Optional[List[Dict[str, Any]]] = None
_CACHED_INACTIVE_GATEWAYS: Optional[set] = None
_CACHED_DEVICE_METADATA: Optional[Dict[str, Dict[str, Any]]] = None


def get_device_metadata_cache(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Centralized dictionary mapping device_name and device_uuid to authoritative DB device metadata:
    location, customer (client_name), property, is_active, hardware_model.
    Ensures Device DB is the single source of truth across all 7 monitoring & report services.
    """
    global _CACHED_DEVICE_METADATA
    if _CACHED_DEVICE_METADATA is not None and not force_refresh:
        return _CACHED_DEVICE_METADATA

    res: Dict[str, Dict[str, Any]] = {}
    try:
        from app.core.database import SessionLocal
        from app.models.base_models import Device
        db = SessionLocal()
        try:
            devs = db.query(Device).filter(Device.deleted_at.is_(None)).all()
            for d in devs:
                cust = d.client.name if (d.client and d.client.name) else "-"
                info = {
                    "device_name": d.name,
                    "device_uuid": str(d.id),
                    "location": d.location or f"Gateway {d.name}",
                    "customer": cust,
                    "property": d.property or {},
                    "is_active": d.is_active,
                    "hardware_model": d.hardware_model or "-",
                }
                res[d.name] = info
                res[str(d.id)] = info
            _CACHED_DEVICE_METADATA = res
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not load device metadata cache from DB: {e}")
        if _CACHED_DEVICE_METADATA is None:
            _CACHED_DEVICE_METADATA = {}

    return _CACHED_DEVICE_METADATA or {}


def update_cached_device_metadata(
    device_name: str,
    device_uuid: Optional[str] = None,
    location: Optional[str] = None,
    customer: Optional[str] = None,
    dev_prop: Optional[Dict[str, Any]] = None,
):
    """Updates in-memory device metadata cache immediately upon device edit in DB."""
    global _CACHED_DEVICE_METADATA
    cache = get_device_metadata_cache()
    existing = cache.get(device_name) or (cache.get(device_uuid) if device_uuid else {})
    updated = dict(existing)
    updated["device_name"] = device_name
    if device_uuid:
        updated["device_uuid"] = device_uuid
    if location is not None:
        updated["location"] = location
    if customer is not None:
        updated["customer"] = customer
    if dev_prop is not None:
        updated["property"] = dev_prop

    cache[device_name] = updated
    if device_uuid:
        cache[device_uuid] = updated
    if updated.get("device_uuid"):
        cache[updated["device_uuid"]] = updated
    _CACHED_DEVICE_METADATA = cache


def get_initial_telemetry_payloads() -> List[Dict[str, Any]]:
    """
    Centralized, high-performance telemetry hydration for all monitoring & report services.
    Instead of 7 services scanning 360,000+ rows in PostgreSQL individually (causing 15-20s server hangs),
    this queries the database ONCE (taking ~0.5s with the composite index) and shares the result.
    """
    global _CACHED_INITIAL_PAYLOADS, _CACHED_INACTIVE_GATEWAYS

    if _CACHED_INITIAL_PAYLOADS is not None:
        return _CACHED_INITIAL_PAYLOADS

    payloads: List[Dict[str, Any]] = []
    inactive_gateways: set = set()
    loaded_from_db = False

    try:
        from app.core.database import SessionLocal
        from app.models.base_models import GatewayTelemetryHistory, Device
        db = SessionLocal()
        try:
            # 1. Fetch inactive / soft-deleted devices
            try:
                inactive_rows = db.query(Device.name, Device.id).filter(
                    (Device.is_active.is_(False)) | (Device.deleted_at.isnot(None))
                ).all()
                inactive_gateways = set()
                for r in inactive_rows:
                    if r[0]:
                        inactive_gateways.add(str(r[0]))
                    if r[1]:
                        inactive_gateways.add(str(r[1]))
                _CACHED_INACTIVE_GATEWAYS = inactive_gateways
            except Exception as ie:
                logger.debug(f"Could not query inactive devices: {ie}")

            # 2. Fast DISTINCT ON device_id query utilizing composite index (device_id, recorded_at DESC)
            query = db.query(GatewayTelemetryHistory)
            if hasattr(GatewayTelemetryHistory, "deleted_at"):
                query = query.filter(GatewayTelemetryHistory.deleted_at.is_(None))
            latest_records = (
                query.distinct(GatewayTelemetryHistory.device_id)
                .order_by(GatewayTelemetryHistory.device_id, GatewayTelemetryHistory.recorded_at.desc())
                .all()
            )

            WIB = timezone(timedelta(hours=7))

            for latest in latest_records:
                if not latest or not latest.raw_payload:
                    continue
                if latest.device and (not latest.device.is_active or latest.device.deleted_at is not None):
                    continue

                p = dict(latest.raw_payload)
                if latest.device:
                    p["device_id"] = latest.device.name
                    p["device_uuid"] = str(latest.device.id)
                    p["customer"] = latest.device.client.name if (latest.device.client and latest.device.client.name) else "-"
                    p["property"] = latest.device.property or {}
                    if latest.device.location:
                        p["location"] = latest.device.location
                        p["location_name"] = latest.device.location
                        p["site_name"] = latest.device.location
                        if "site_info" in p and isinstance(p["site_info"], dict):
                            p["site_info"]["location_name"] = latest.device.location
                            p["site_info"]["site_name"] = latest.device.location
                if latest.recorded_at:
                    t_wib = latest.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if latest.recorded_at.tzinfo is None else latest.recorded_at.astimezone(WIB)
                    p["recorded_at"] = t_wib.strftime("%Y-%m-%d %H:%M:%S")

                payloads.append(p)

            if payloads:
                loaded_from_db = True
                logger.info(f"TelemetryLoader: Successfully loaded {len(payloads)} gateways from PostgreSQL in single batch")
        finally:
            db.close()
    except Exception as dbe:
        logger.warning(f"TelemetryLoader: PostgreSQL hydration failed: {dbe}")

    # Fallback to local cache file if DB is empty or unreachable
    if not loaded_from_db:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cache_file = os.path.join(base_dir, "telemetry_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    payloads = [
                        item for item in data
                        if isinstance(item, dict)
                        and item.get("device_id") not in inactive_gateways
                        and str(item.get("device_uuid", "")) not in inactive_gateways
                    ]
                elif isinstance(data, dict):
                    if (
                        data.get("device_id") not in inactive_gateways
                        and str(data.get("device_uuid", "")) not in inactive_gateways
                    ):
                        payloads = [data]
                logger.info(f"TelemetryLoader: Loaded {len(payloads)} gateways from disk cache fallback: {cache_file}")
            except Exception as fe:
                logger.warning(f"TelemetryLoader: Disk cache load error: {fe}")

    _CACHED_INITIAL_PAYLOADS = payloads
    return _CACHED_INITIAL_PAYLOADS


def get_cached_inactive_gateways() -> set:
    global _CACHED_INACTIVE_GATEWAYS
    if _CACHED_INACTIVE_GATEWAYS is None:
        get_initial_telemetry_payloads()
    return _CACHED_INACTIVE_GATEWAYS or set()


def set_device_active_status(device_name: str, device_uuid: Optional[str] = None, is_active: bool = True):
    """Immediately updates inactive gateway cache and device metadata when a device's is_active changes."""
    global _CACHED_INACTIVE_GATEWAYS, _CACHED_DEVICE_METADATA
    if _CACHED_INACTIVE_GATEWAYS is None:
        _CACHED_INACTIVE_GATEWAYS = set()

    if is_active:
        _CACHED_INACTIVE_GATEWAYS.discard(device_name)
        if device_uuid:
            _CACHED_INACTIVE_GATEWAYS.discard(device_uuid)
    else:
        _CACHED_INACTIVE_GATEWAYS.add(device_name)
        if device_uuid:
            _CACHED_INACTIVE_GATEWAYS.add(device_uuid)

    cache = get_device_metadata_cache()
    if device_name in cache:
        cache[device_name]["is_active"] = is_active
    if device_uuid and device_uuid in cache:
        cache[device_uuid]["is_active"] = is_active
    _CACHED_DEVICE_METADATA = cache

