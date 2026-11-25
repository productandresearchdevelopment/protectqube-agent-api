import logging
import uuid
from datetime import datetime, time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.database import get_db
from app.models.base_models import Device, Client, User, GatewayTelemetryHistory
from app.schemas.device import DeviceUpdate
from app.api.deps import get_current_user
from app.core.rbac import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["Devices"], dependencies=[Depends(require_permission("/configuration"))])


def get_device_detected_cameras(db: Session, dev_id: uuid.UUID, dev_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extracts real camera channels detected from incoming MQTT telemetry snapshots.
    Fast path: checks live in-memory telemetry first (O(1) < 1ms), falls back to DB.
    """
    try:
        from app.api.v1.endpoints.monitoring import dvr_service
        if dvr_service and hasattr(dvr_service, "_live_gateways"):
            matched_g = None
            if dev_name and dev_name in dvr_service._live_gateways:
                matched_g = dvr_service._live_gateways[dev_name]
            elif str(dev_id) in dvr_service._live_gateways:
                matched_g = dvr_service._live_gateways[str(dev_id)]
            else:
                for k, v in dvr_service._live_gateways.items():
                    if str(v.get("device_uuid", "")).lower() == str(dev_id).lower():
                        matched_g = v
                        break
            if matched_g:
                cams = (
                    matched_g.get("raw_payload", {}).get("nvr_surveillance", {}).get("cameras", {}).get("camera_list")
                    or matched_g.get("detail_item", {}).get("cameras")
                )
                if cams and isinstance(cams, list):
                    results = []
                    for idx, c in enumerate(cams):
                        c_id = str(c.get("id") or c.get("channel") or (idx + 1))
                        results.append({
                            "id": c_id,
                            "channel": int(c_id) if c_id.isdigit() else (idx + 1),
                            "name": c.get("name") or f"CAM {c_id}",
                            "is_online": bool(c.get("is_online", c.get("status") == "Online")),
                            "resolution": c.get("resolution") or ("1080P" if c.get("is_online", c.get("status") == "Online") else "NO VIDEO"),
                            "recording_status": c.get("recording_status") or ("RECORD" if c.get("is_recording") else "NOT_RECORD"),
                        })
                    return results
    except Exception as e:
        logger.debug(f"Fast in-memory detected cameras lookup skipped: {e}")

    try:
        latest = (
            db.query(GatewayTelemetryHistory)
            .filter(
                GatewayTelemetryHistory.device_id == dev_id,
                GatewayTelemetryHistory.raw_payload.isnot(None),
            )
            .order_by(GatewayTelemetryHistory.recorded_at.desc())
            .first()
        )
        if not latest or not latest.raw_payload:
            return []

        nvr = latest.raw_payload.get("nvr_surveillance", {})
        cams_info = nvr.get("cameras", {})
        cam_list = cams_info.get("camera_list", [])

        if cam_list and isinstance(cam_list, list):
            results = []
            for idx, c in enumerate(cam_list):
                c_id = str(c.get("id") or (idx + 1))
                results.append({
                    "id": c_id,
                    "channel": int(c_id) if c_id.isdigit() else (idx + 1),
                    "name": c.get("name") or f"CAM {c_id}",
                    "is_online": bool(c.get("is_online", False)),
                    "resolution": c.get("resolution") or ("1080P" if c.get("is_online") else "NO VIDEO"),
                    "recording_status": c.get("recording_status") or ("RECORD" if c.get("is_online") else "NOT_RECORD"),
                })
            return results

        # Fallback if no camera_list but has total_cameras
        tot = cams_info.get("total_cameras", 4) or 4
        on_cnt = cams_info.get("online_count", tot)
        return [
            {
                "id": str(i + 1),
                "channel": i + 1,
                "name": f"Camera {i + 1:02d}",
                "is_online": i < on_cnt,
                "resolution": "1080P" if i < on_cnt else "NO VIDEO",
                "recording_status": "RECORD" if i < on_cnt else "NOT_RECORD",
            }
            for i in range(tot)
        ]
    except Exception as e:
        logger.warning(f"Error fetching detected cameras for device {dev_id}: {e}")
        return []


@router.get("")
def list_devices(
    search: Optional[str] = Query(None, description="Search by name, location, model"),
    client_id: Optional[str] = Query(None, description="Filter by client UUID ('unassigned' for null)"),
    is_active: Optional[str] = Query(None, description="Filter by active status ('true', 'false', 'all')"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists gateway devices with client info, hardware specs, and properties.
    Read-only collection of existing ingested hardware devices.
    """
    search_str = search if isinstance(search, str) else None
    client_id_str = client_id if isinstance(client_id, str) else None
    active_bool = None
    if is_active is not None:
        if isinstance(is_active, bool):
            active_bool = is_active
        elif str(is_active).lower() in ["true", "1", "yes", "active"]:
            active_bool = True
        elif str(is_active).lower() in ["false", "0", "no", "inactive"]:
            active_bool = False

    page_num = page if isinstance(page, int) else 1
    page_size_num = page_size if isinstance(page_size, int) else 25

    query = db.query(Device).filter(Device.deleted_at.is_(None))

    if active_bool is not None:
        query = query.filter(Device.is_active == active_bool)

    if client_id_str and client_id_str.strip():
        c_val = client_id_str.strip()
        if c_val.lower() in ["unassigned", "none", "null"]:
            query = query.filter(Device.client_id.is_(None))
        else:
            try:
                c_uuid = uuid.UUID(c_val)
                query = query.filter(Device.client_id == c_uuid)
            except ValueError:
                pass

    if search_str and search_str.strip():
        term = f"%{search_str.strip()}%"
        query = query.join(Client, Device.client_id == Client.id, isouter=True).filter(
            or_(
                Device.name.ilike(term),
                Device.location.ilike(term),
                Device.hardware_model.ilike(term),
                Client.name.ilike(term),
            )
        )

    total = query.count()
    offset = (page_num - 1) * page_size_num
    devices = (
        query.options(joinedload(Device.client))
        .order_by(Device.name.asc())
        .offset(offset)
        .limit(page_size_num)
        .all()
    )

    results = []
    for d in devices:
        prop = d.property or {}
        sel_cams = prop.get("selected_cameras")
        tot_cams = len(sel_cams) if (sel_cams is not None and isinstance(sel_cams, list)) else prop.get("total_cameras")

        results.append({
            "id": str(d.id),
            "name": d.name,
            "location": d.location,
            "lat": d.lat,
            "long": d.long,
            "hardware_model": d.hardware_model,
            "operational_start": d.operational_start.strftime("%H:%M:%S") if d.operational_start else None,
            "operational_end": d.operational_end.strftime("%H:%M:%S") if d.operational_end else None,
            "is_active": d.is_active,
            "client_id": str(d.client_id) if d.client_id else None,
            "client_name": d.client.name if d.client else None,
            "property": prop,
            "total_cameras": tot_cams,
            "selected_cameras": sel_cams,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        })

    return {
        "status": True,
        "data": results,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


from pydantic import BaseModel as _PydanticBaseModel


class BulkRawMqttExportRequest(_PydanticBaseModel):
    device_ids: Optional[List[str]] = None
    search: Optional[str] = None
    client_id: Optional[str] = None
    is_active: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM-DD (WIB)
    end_date: Optional[str] = None    # YYYY-MM-DD (WIB)


def _check_device_export_permission(current_user: User, db: Session) -> None:
    from app.core.rbac import is_privileged_role
    from app.models.base_models import RoleModule, Module

    if not current_user.role_id:
        if is_privileged_role(current_user.role):
            return
        raise HTTPException(status_code=403, detail="Anda tidak memiliki izin untuk export Raw MQTT.")

    has_any_config = (
        db.query(RoleModule.id)
        .filter(RoleModule.role_id == current_user.role_id, RoleModule.deleted_at.is_(None))
        .first()
    )
    if not has_any_config and is_privileged_role(current_user.role):
        return

    allowed = (
        db.query(RoleModule.id)
        .join(Module, RoleModule.module_id == Module.id)
        .filter(
            RoleModule.role_id == current_user.role_id,
            RoleModule.checked.is_(True),
            RoleModule.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Module.route == "/api/v1/devices/export-raw-mqtt",
        )
        .first()
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Role Anda tidak memiliki izin untuk export Raw MQTT pada halaman Devices.",
        )


def _iter_device_raw_mqtt_json_chunks(
    dev_id_str: str,
    dev_name: str,
    dev_loc: str,
    stats_override: Optional[tuple] = None,
    shared_db: Optional[Session] = None,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
    date_range_label: str = "All Time",
):
    """
    High-speed streaming generator yielding UTF-8 JSON chunks for a single device.
    Reads raw_payload::text directly from PostgreSQL to bypass Python json.loads/json.dumps overhead.
    """
    import json
    from datetime import timezone, timedelta
    from sqlalchemy import func, cast, Text
    from app.core.database import SessionLocal

    WIB = timezone(timedelta(hours=7))

    def _fmt_wib(dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        dt_wib = dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(WIB)
        return dt_wib.strftime("%Y-%m-%d %H:%M:%S WIB")

    owns_db = shared_db is None
    stream_db = shared_db if shared_db is not None else SessionLocal()
    try:
        if stats_override is not None:
            total_records, first_dt, last_dt = stats_override
        else:
            sq = stream_db.query(
                func.count(GatewayTelemetryHistory.id),
                func.min(GatewayTelemetryHistory.recorded_at),
                func.max(GatewayTelemetryHistory.recorded_at),
            ).filter(GatewayTelemetryHistory.device_id == dev_id_str)
            if start_utc is not None:
                sq = sq.filter(GatewayTelemetryHistory.recorded_at >= start_utc)
            if end_utc is not None:
                sq = sq.filter(GatewayTelemetryHistory.recorded_at <= end_utc)
            stats = sq.first()
            total_records = int(stats[0] or 0) if stats else 0
            first_dt = stats[1] if stats else None
            last_dt = stats[2] if stats else None

        header_meta = {
            "device_id": dev_name,
            "location": dev_loc,
            "date_range": date_range_label,
            "exported_at_wib": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
            "total_records": int(total_records or 0),
            "first_record_wib": _fmt_wib(first_dt),
            "last_record_wib": _fmt_wib(last_dt),
        }
        meta_json = json.dumps(header_meta, ensure_ascii=False)
        yield meta_json[:-1] + ',\n  "records": [\n'

        q = stream_db.query(
            GatewayTelemetryHistory.recorded_at,
            cast(GatewayTelemetryHistory.raw_payload, Text),
        ).filter(GatewayTelemetryHistory.device_id == dev_id_str)
        if start_utc is not None:
            q = q.filter(GatewayTelemetryHistory.recorded_at >= start_utc)
        if end_utc is not None:
            q = q.filter(GatewayTelemetryHistory.recorded_at <= end_utc)
        q = q.order_by(GatewayTelemetryHistory.recorded_at.asc()).yield_per(2000)

        first_item = True
        buf: List[str] = []
        for rec_at, raw_text in q:
            ts_wib = _fmt_wib(rec_at)
            ts_wib_json = f'"{ts_wib}"' if ts_wib else "null"
            ts_utc_json = f'"{rec_at.isoformat()}"' if rec_at else "null"
            payload_json = raw_text if raw_text else "null"
            prefix = "    " if first_item else ",\n    "
            first_item = False
            buf.append(
                f'{prefix}{{"timestamp_wib": {ts_wib_json}, "recorded_at_utc": {ts_utc_json}, "raw_payload": {payload_json}}}'
            )
            if len(buf) >= 200:
                yield "".join(buf)
                buf.clear()

        if buf:
            yield "".join(buf)
            buf.clear()

        yield "\n  ]\n}\n"
    finally:
        if owns_db:
            stream_db.close()


@router.post("/export-raw-mqtt")
def export_devices_raw_mqtt(
    payload: BulkRawMqttExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bulk or single export of raw MQTT JSON telemetry from Devices Configuration:
    - 1 device selected/matched -> returns direct .json file
    - Multiple devices selected/matched -> returns .zip archive containing one .json file per device
    """
    import os
    import re
    import tempfile
    import zipfile
    from datetime import timezone, timedelta
    from fastapi.responses import StreamingResponse

    _check_device_export_permission(current_user, db)

    WIB = timezone(timedelta(hours=7))
    date_str = datetime.now(WIB).strftime("%Y%m%d")

    # Parse optional WIB date range -> naive UTC for PostgreSQL recorded_at comparison
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None
    date_range_label = "All Time"
    range_suffix = date_str

    try:
        if payload.start_date and payload.start_date.strip():
            s_wib = datetime.strptime(payload.start_date.strip()[:10], "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=WIB
            )
            start_utc = s_wib.astimezone(timezone.utc).replace(tzinfo=None)
        if payload.end_date and payload.end_date.strip():
            e_wib = datetime.strptime(payload.end_date.strip()[:10], "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=WIB
            )
            end_utc = e_wib.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=400, detail="Format tanggal harus YYYY-MM-DD.")

    if start_utc and end_utc and start_utc > end_utc:
        raise HTTPException(status_code=400, detail="Start date tidak boleh lebih besar dari end date.")

    if payload.start_date and payload.end_date:
        date_range_label = f"{payload.start_date[:10]} to {payload.end_date[:10]} (WIB)"
        range_suffix = f"{payload.start_date[:10].replace('-', '')}_{payload.end_date[:10].replace('-', '')}"
    elif payload.start_date:
        date_range_label = f"From {payload.start_date[:10]} (WIB)"
        range_suffix = f"from_{payload.start_date[:10].replace('-', '')}"
    elif payload.end_date:
        date_range_label = f"Until {payload.end_date[:10]} (WIB)"
        range_suffix = f"until_{payload.end_date[:10].replace('-', '')}"

    query = db.query(Device).filter(Device.deleted_at.is_(None))

    if payload.device_ids and len(payload.device_ids) > 0:
        valid_uuids = []
        raw_names = []
        for did in payload.device_ids:
            try:
                valid_uuids.append(uuid.UUID(str(did)))
            except ValueError:
                raw_names.append(str(did))
        conds = []
        if valid_uuids:
            conds.append(Device.id.in_(valid_uuids))
        if raw_names:
            conds.append(Device.name.in_(raw_names))
        if conds:
            query = query.filter(or_(*conds))
    else:
        if payload.is_active is not None:
            if str(payload.is_active).lower() in ["true", "1", "yes", "active"]:
                query = query.filter(Device.is_active.is_(True))
            elif str(payload.is_active).lower() in ["false", "0", "no", "inactive"]:
                query = query.filter(Device.is_active.is_(False))

        if payload.client_id and payload.client_id.strip() and payload.client_id.strip().lower() != "all":
            c_val = payload.client_id.strip()
            if c_val.lower() in ["unassigned", "none", "null"]:
                query = query.filter(Device.client_id.is_(None))
            else:
                try:
                    query = query.filter(Device.client_id == uuid.UUID(c_val))
                except ValueError:
                    pass

        if payload.search and payload.search.strip():
            term = f"%{payload.search.strip()}%"
            query = query.join(Client, Device.client_id == Client.id, isouter=True).filter(
                or_(
                    Device.name.ilike(term),
                    Device.location.ilike(term),
                    Device.hardware_model.ilike(term),
                    Client.name.ilike(term),
                )
            )

    devices = query.order_by(Device.name.asc()).all()
    if not devices:
        raise HTTPException(status_code=404, detail="Tidak ada device yang ditemukan untuk di-export.")

    # Single device -> direct .json download
    if len(devices) == 1:
        dev = devices[0]
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", dev.name)
        filename = f"RAW_MQTT_{safe_name}_{range_suffix}.json"
        return StreamingResponse(
            _iter_device_raw_mqtt_json_chunks(
                str(dev.id),
                dev.name,
                dev.location or "-",
                start_utc=start_utc,
                end_utc=end_utc,
                date_range_label=date_range_label,
            ),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Multiple devices -> ultra-fast .zip (compresslevel=1) using 1 batch stats query + 1 single streaming data query
    import json as _json
    from sqlalchemy import func as _sql_func, cast as _sql_cast, Text as _SqlText
    from app.core.database import SessionLocal as _SessionLocal

    def _fmt_wib_dt(dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        dt_wib = dt.astimezone(WIB) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(WIB)
        return dt_wib.strftime("%Y-%m-%d %H:%M:%S WIB")

    dev_uuids = [dev.id for dev in devices]
    stats_q = db.query(
        GatewayTelemetryHistory.device_id,
        _sql_func.count(GatewayTelemetryHistory.id),
        _sql_func.min(GatewayTelemetryHistory.recorded_at),
        _sql_func.max(GatewayTelemetryHistory.recorded_at),
    ).filter(GatewayTelemetryHistory.device_id.in_(dev_uuids))
    if start_utc is not None:
        stats_q = stats_q.filter(GatewayTelemetryHistory.recorded_at >= start_utc)
    if end_utc is not None:
        stats_q = stats_q.filter(GatewayTelemetryHistory.recorded_at <= end_utc)
    stats_rows = stats_q.group_by(GatewayTelemetryHistory.device_id).all()
    stats_map = {str(r[0]): (int(r[1] or 0), r[2], r[3]) for r in stats_rows}

    # Pre-compute unique archive filenames for each device
    used_arcnames = set()
    dev_info_map: Dict[str, tuple] = {}
    for dev in devices:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", dev.name)
        safe_loc = re.sub(r"[^a-zA-Z0-9_-]", "_", (dev.location or "").strip())[:40].strip("_")
        base_arc = f"{safe_name}_{safe_loc}" if safe_loc else safe_name
        arcname = f"{base_arc}.json"
        counter = 2
        while arcname in used_arcnames:
            arcname = f"{base_arc}_{counter}.json"
            counter += 1
        used_arcnames.add(arcname)
        dev_info_map[str(dev.id)] = (dev.name, dev.location or "-", arcname)

    exported_at_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")

    def _build_header_prefix(dev_id_str: str) -> bytes:
        d_name, d_loc, _ = dev_info_map[dev_id_str]
        tot, f_dt, l_dt = stats_map.get(dev_id_str, (0, None, None))
        header_meta = {
            "device_id": d_name,
            "location": d_loc,
            "date_range": date_range_label,
            "exported_at_wib": exported_at_wib,
            "total_records": int(tot or 0),
            "first_record_wib": _fmt_wib_dt(f_dt),
            "last_record_wib": _fmt_wib_dt(l_dt),
        }
        return (_json.dumps(header_meta, ensure_ascii=False)[:-1] + ',\n  "records": [\n').encode("utf-8")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.close()

    shared_db = _SessionLocal()
    try:
        written_dev_ids = set()
        with zipfile.ZipFile(
            tmp_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1,
            allowZip64=True,
        ) as zf:
            # 1 single streaming query for all devices that actually have records in this date range
            active_dev_uuids = [dev.id for dev in devices if stats_map.get(str(dev.id), (0,))[0] > 0]
            if active_dev_uuids:
                data_q = shared_db.query(
                    GatewayTelemetryHistory.device_id,
                    GatewayTelemetryHistory.recorded_at,
                    _sql_cast(GatewayTelemetryHistory.raw_payload, _SqlText),
                ).filter(GatewayTelemetryHistory.device_id.in_(active_dev_uuids))
                if start_utc is not None:
                    data_q = data_q.filter(GatewayTelemetryHistory.recorded_at >= start_utc)
                if end_utc is not None:
                    data_q = data_q.filter(GatewayTelemetryHistory.recorded_at <= end_utc)
                data_q = data_q.order_by(
                    GatewayTelemetryHistory.device_id.asc(),
                    GatewayTelemetryHistory.recorded_at.asc(),
                ).yield_per(2000)

                current_dev_id: Optional[str] = None
                current_zentry = None
                first_item = True
                buf: List[str] = []

                try:
                    for row_dev_id, rec_at, raw_text in data_q:
                        d_key = str(row_dev_id)
                        if d_key != current_dev_id:
                            if current_zentry is not None:
                                if buf:
                                    current_zentry.write("".join(buf).encode("utf-8"))
                                    buf.clear()
                                current_zentry.write(b"\n  ]\n}\n")
                                current_zentry.close()
                            current_dev_id = d_key
                            written_dev_ids.add(d_key)
                            _, _, arcname = dev_info_map[d_key]
                            current_zentry = zf.open(arcname, mode="w")
                            current_zentry.write(_build_header_prefix(d_key))
                            first_item = True

                        ts_wib = _fmt_wib_dt(rec_at)
                        ts_wib_json = f'"{ts_wib}"' if ts_wib else "null"
                        ts_utc_json = f'"{rec_at.isoformat()}"' if rec_at else "null"
                        payload_json = raw_text if raw_text else "null"
                        prefix = "    " if first_item else ",\n    "
                        first_item = False
                        buf.append(
                            f'{prefix}{{"timestamp_wib": {ts_wib_json}, "recorded_at_utc": {ts_utc_json}, "raw_payload": {payload_json}}}'
                        )
                        if len(buf) >= 200:
                            current_zentry.write("".join(buf).encode("utf-8"))
                            buf.clear()

                    if current_zentry is not None:
                        if buf:
                            current_zentry.write("".join(buf).encode("utf-8"))
                            buf.clear()
                        current_zentry.write(b"\n  ]\n}\n")
                        current_zentry.close()
                        current_zentry = None
                finally:
                    if current_zentry is not None:
                        try:
                            current_zentry.close()
                        except Exception:
                            pass

            # Write empty JSON stubs for devices with 0 records in the selected range (no DB query needed)
            for dev in devices:
                d_key = str(dev.id)
                if d_key not in written_dev_ids:
                    _, _, arcname = dev_info_map[d_key]
                    with zf.open(arcname, mode="w") as zentry:
                        zentry.write(_build_header_prefix(d_key))
                        zentry.write(b"  ]\n}\n")
    except Exception as e:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        logger.error(f"Bulk raw MQTT ZIP export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gagal membuat arsip ZIP Raw MQTT: {str(e)}")
    finally:
        shared_db.close()

    def iter_zip_and_cleanup():
        try:
            with open(tmp_path, "rb") as f:
                while True:
                    buf = f.read(1024 * 256)
                    if not buf:
                        break
                    yield buf
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    zip_filename = f"RAW_MQTT_BULK_{len(devices)}_DEVICES_{range_suffix}.zip"
    return StreamingResponse(
        iter_zip_and_cleanup(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@router.get("/{device_id}")
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dev = None
    try:
        d_uuid = uuid.UUID(device_id)
        dev = db.query(Device).filter(Device.id == d_uuid, Device.deleted_at.is_(None)).first()
    except ValueError:
        pass

    if not dev:
        dev = db.query(Device).filter(Device.name == device_id, Device.deleted_at.is_(None)).first()

    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    prop = dev.property or {}
    detected = get_device_detected_cameras(db, dev.id, str(dev.name))
    sel_cams = prop.get("selected_cameras")
    tot_cams = len(sel_cams) if (sel_cams is not None and isinstance(sel_cams, list)) else prop.get("total_cameras")
    raw_has_dvr = prop.get("has_dvr")
    has_dvr = raw_has_dvr if raw_has_dvr is not None else (False if (tot_cams == 0 and prop.get("total_cameras") == 0) else True)

    return {
        "status": True,
        "data": {
            "id": str(dev.id),
            "name": dev.name,
            "location": dev.location,
            "lat": dev.lat,
            "long": dev.long,
            "hardware_model": dev.hardware_model,
            "operational_start": dev.operational_start.strftime("%H:%M:%S") if dev.operational_start else None,
            "operational_end": dev.operational_end.strftime("%H:%M:%S") if dev.operational_end else None,
            "is_active": dev.is_active,
            "client_id": str(dev.client_id) if dev.client_id else None,
            "client_name": dev.client.name if dev.client else None,
            "has_dvr": has_dvr,
            "property": prop,
            "total_cameras": tot_cams,
            "selected_cameras": sel_cams,
            "detected_cameras": detected,
            "created_at": dev.created_at,
            "updated_at": dev.updated_at,
        }
    }


@router.put("/{device_id}")
def update_device(
    device_id: str,
    payload: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dev = None
    try:
        d_uuid = uuid.UUID(device_id)
        dev = db.query(Device).filter(Device.id == d_uuid, Device.deleted_at.is_(None)).first()
    except ValueError:
        pass

    if not dev:
        dev = db.query(Device).filter(Device.name == device_id, Device.deleted_at.is_(None)).first()

    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    # 1. Update client_id
    if payload.client_id is not None:
        if payload.client_id.strip() in ["", "none", "null"]:
            dev.client_id = None
        else:
            try:
                target_c_uuid = uuid.UUID(payload.client_id.strip())
                client = db.query(Client).filter(Client.id == target_c_uuid, Client.deleted_at.is_(None)).first()
                if not client:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target Client does not exist.")
                dev.client_id = target_c_uuid
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Client UUID format.")

    # 2. Update basic fields
    if payload.location is not None:
        dev.location = payload.location.strip()
    if payload.lat is not None:
        dev.lat = payload.lat
    if payload.long is not None:
        dev.long = payload.long
    if payload.hardware_model is not None:
        dev.hardware_model = payload.hardware_model.strip()
    if payload.is_active is not None:
        dev.is_active = payload.is_active

    # 3. Update operational hours
    if payload.operational_start is not None:
        if payload.operational_start.strip():
            try:
                dev.operational_start = time.fromisoformat(payload.operational_start.strip())
            except ValueError:
                pass
        else:
            dev.operational_start = None

    if payload.operational_end is not None:
        if payload.operational_end.strip():
            try:
                dev.operational_end = time.fromisoformat(payload.operational_end.strip())
            except ValueError:
                pass
        else:
            dev.operational_end = None

    # 4. Update property JSONB, has_dvr, selected_cameras & total_cameras shortcut
    current_prop = dict(dev.property or {})
    if payload.property is not None:
        current_prop.update(payload.property)

    if payload.has_dvr is not None:
        current_prop["has_dvr"] = payload.has_dvr
        if not payload.has_dvr:
            current_prop["total_cameras"] = 0
            current_prop["selected_cameras"] = []

    if payload.has_dvr is not False:
        if payload.selected_cameras is not None:
            current_prop["selected_cameras"] = [str(x) for x in payload.selected_cameras]
            current_prop["total_cameras"] = len(payload.selected_cameras)
        elif payload.total_cameras is not None:
            current_prop["total_cameras"] = payload.total_cameras

    dev.property = current_prop
    dev.updated_at = datetime.utcnow()
    dev.updated_by = current_user.id if hasattr(current_user, "id") else None

    db.commit()
    db.refresh(dev)

    # Fast O(1) in-memory hot-update for the specific device across all live monitoring & report services
    try:
        from app.api.v1.endpoints.monitoring import (
            dvr_service,
            dvr_report_service,
            system_health_service,
            health_report_service,
            cellular_service,
            cellular_report_service,
            sla_report_service,
        )

        dev_name = str(dev.name)
        dev_uuid_str = str(dev.id)
        client_name = dev.client.name if dev.client else "-"
        dev_loc = dev.location or ""
        dev_prop = dev.property or {}

        # 0. Update Centralized Telemetry Loader Cache (metadata & active status)
        try:
            from app.services.telemetry_loader import update_cached_device_metadata, set_device_active_status
            update_cached_device_metadata(
                device_name=dev_name,
                device_uuid=dev_uuid_str,
                location=dev_loc,
                customer=client_name,
                dev_prop=dev_prop,
            )
            set_device_active_status(
                device_name=dev_name,
                device_uuid=dev_uuid_str,
                is_active=dev.is_active,
            )
        except Exception as t_err:
            logger.debug(f"Could not update telemetry loader metadata/active cache: {t_err}")

        all_services = [
            dvr_service,
            dvr_report_service,
            system_health_service,
            health_report_service,
            cellular_service,
            cellular_report_service,
            sla_report_service,
        ]

        # Helper to apply authoritative location & client to raw payload
        def _apply_meta_to_raw(p: dict) -> dict:
            p["property"] = dev_prop
            p["location"] = dev_loc
            p["location_name"] = dev_loc
            p["site_name"] = dev_loc
            p["customer"] = client_name
            if "site_info" in p and isinstance(p["site_info"], dict):
                p["site_info"]["location_name"] = dev_loc
                p["site_info"]["site_name"] = dev_loc
            return p

        if not dev.is_active:
            # =====================================================================
            # DEVICE INACTIVE: Immediately evict from live fleet across all services
            # =====================================================================
            for svc in all_services:
                if svc is not None:
                    if hasattr(svc, "_inactive_gateways"):
                        svc._inactive_gateways.add(dev_name)
                        svc._inactive_gateways.add(dev_uuid_str)
                    if hasattr(svc, "_live_gateways"):
                        svc._live_gateways.pop(dev_name, None)
                        svc._live_gateways.pop(dev_uuid_str, None)
                        # Also purge any entry matching dev_name or dev_uuid_str in its payload/item
                        keys_to_del = [
                            k for k, v in svc._live_gateways.items()
                            if k in (dev_name, dev_uuid_str)
                            or (isinstance(v, dict) and (
                                v.get("item", {}).get("id") in (dev_name, dev_uuid_str)
                                or v.get("item", {}).get("device_uuid") in (dev_name, dev_uuid_str)
                                or v.get("device_id") in (dev_name, dev_uuid_str)
                                or v.get("device_uuid") in (dev_name, dev_uuid_str)
                            ))
                        ]
                        for k in keys_to_del:
                            svc._live_gateways.pop(k, None)
                    if hasattr(svc, "_device_locations"):
                        svc._device_locations.pop(dev_name, None)
                        svc._device_locations.pop(dev_uuid_str, None)
        else:
            # =====================================================================
            # DEVICE ACTIVE: Restore from inactive & immediately hydrate into live fleet
            # =====================================================================
            for svc in all_services:
                if svc is not None:
                    if hasattr(svc, "_inactive_gateways"):
                        svc._inactive_gateways.discard(dev_name)
                        svc._inactive_gateways.discard(dev_uuid_str)
                    if hasattr(svc, "_device_properties"):
                        svc._device_properties[dev_name] = dev_prop
                        svc._device_properties[dev_uuid_str] = dev_prop
                    if hasattr(svc, "_device_locations"):
                        svc._device_locations[dev_name] = dev_loc
                        svc._device_locations[dev_uuid_str] = dev_loc

            # Find latest telemetry history in DB to hydrate into services
            latest_hist = (
                db.query(GatewayTelemetryHistory)
                .filter(
                    or_(
                        GatewayTelemetryHistory.device_id == dev.id,
                        GatewayTelemetryHistory.location == dev.name,
                    )
                )
                .order_by(GatewayTelemetryHistory.recorded_at.desc())
                .first()
            )

            base_raw = (
                dict(latest_hist.raw_payload)
                if (latest_hist and latest_hist.raw_payload)
                else {
                    "device_id": dev_name,
                    "device_uuid": dev_uuid_str,
                    "type": dev.hardware_model or "SmartBox Hitam",
                    "location": dev_loc,
                    "status": "Online",
                }
            )
            raw_p = _apply_meta_to_raw(base_raw)

            for svc in all_services:
                if svc is not None and hasattr(svc, "update_from_telemetry"):
                    try:
                        svc.update_from_telemetry(raw_p, save_cache=False)
                    except TypeError:
                        try:
                            svc.update_from_telemetry(raw_p)
                        except Exception as te:
                            logger.debug(f"Service hydration error: {te}")
    except Exception as e:
        logger.debug(f"Could not hot-update in-memory cache: {e}")

    tot_cams = (
        len(current_prop["selected_cameras"])
        if ("selected_cameras" in current_prop and isinstance(current_prop["selected_cameras"], list))
        else current_prop.get("total_cameras")
    )

    return {
        "status": True,
        "message": f"Device '{dev.name}' updated successfully",
        "data": {
            "id": str(dev.id),
            "name": dev.name,
            "location": dev.location,
            "hardware_model": dev.hardware_model,
            "client_id": str(dev.client_id) if dev.client_id else None,
            "client_name": dev.client.name if dev.client else None,
            "is_active": dev.is_active,
            "property": dev.property or {},
            "total_cameras": tot_cams,
            "selected_cameras": current_prop.get("selected_cameras"),
            "updated_at": dev.updated_at,
        }
    }
