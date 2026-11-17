import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("telemetry-loader")

_CACHED_INITIAL_PAYLOADS: Optional[List[Dict[str, Any]]] = None
_CACHED_INACTIVE_GATEWAYS: Optional[set] = None


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
                inactive_rows = db.query(Device.name).filter(
                    (Device.is_active.is_(False)) | (Device.deleted_at.isnot(None))
                ).all()
                inactive_gateways = {r[0] for r in inactive_rows if r[0]}
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
                    payloads = [item for item in data if isinstance(item, dict)]
                elif isinstance(data, dict):
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
