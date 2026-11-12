import logging
import uuid
from datetime import datetime, time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.models.base_models import Device, Client, User, GatewayTelemetryHistory
from app.schemas.device import DeviceUpdate
from app.api.deps import get_current_user
from app.core.rbac import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["Devices"], dependencies=[Depends(require_permission("/configuration"))])


def get_device_detected_cameras(db: Session, dev_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Extracts real camera channels detected from incoming MQTT telemetry snapshots.
    """
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
    page_size: int = Query(25, ge=1, le=500),
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
    devices = query.order_by(Device.name.asc()).offset(offset).limit(page_size_num).all()

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
    detected = get_device_detected_cameras(db, dev.id)
    sel_cams = prop.get("selected_cameras")
    tot_cams = len(sel_cams) if (sel_cams is not None and isinstance(sel_cams, list)) else prop.get("total_cameras")

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

    # 4. Update property JSONB, selected_cameras & total_cameras shortcut
    current_prop = dict(dev.property or {})
    if payload.property is not None:
        current_prop.update(payload.property)

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

    # Trigger hot-update in services so DVR and SLA reports immediately reflect the new camera setup
    try:
        from app.services.sla_report_service import sla_report_service
        from app.services.system_health_service import system_health_service
        from app.services.dvr_service import DVRService
        from app.services.dvr_report_service import DVRReportService

        if dev.name in sla_report_service._live_gateways:
            g = sla_report_service._live_gateways[dev.name]
            g["location"] = dev.location or g["location"]
            g["customer"] = dev.client.name if dev.client else "-"
            if dev.property:
                g["property"] = dev.property

        if dev.name in system_health_service._live_gateways:
            g = system_health_service._live_gateways[dev.name]
            g["table_item"]["location"] = dev.location or g["table_item"]["location"]
            g["table_item"]["customer"] = dev.client.name if dev.client else "-"
            g["detail_item"]["location"] = dev.location or g["detail_item"]["location"]
            g["detail_item"]["customer"] = dev.client.name if dev.client else "-"

        # Reload all live monitoring & report services caches
        from app.api.v1.endpoints.monitoring import (
            dvr_service,
            dvr_report_service,
            system_health_service,
            health_report_service,
            cellular_service,
            cellular_report_service,
            sla_report_service,
        )
        for srv in [
            dvr_service,
            dvr_report_service,
            system_health_service,
            health_report_service,
            cellular_service,
            cellular_report_service,
            sla_report_service,
        ]:
            if srv and hasattr(srv, "reload_telemetry_cache"):
                try:
                    srv.reload_telemetry_cache()
                except Exception:
                    pass
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
