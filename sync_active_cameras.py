"""
One-shot / repeatable script to auto-populate Device.property['selected_cameras']
and Device.property['total_cameras'] in PostgreSQL from each device's latest
telemetry snapshot, selecting only currently active (is_online=True) cameras.

Usage:
    python backend/sync_active_cameras.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm.attributes import flag_modified
from app.core.database import SessionLocal
from app.models.base_models import Device, GatewayTelemetryHistory


def sync_active_cameras() -> None:
    db = SessionLocal()
    updated = 0
    skipped_no_history = 0
    skipped_no_active = 0

    try:
        devices = db.query(Device).filter(Device.deleted_at.is_(None)).all()
        for dev in devices:
            latest = (
                db.query(GatewayTelemetryHistory)
                .filter(
                    GatewayTelemetryHistory.device_id == dev.id,
                    GatewayTelemetryHistory.deleted_at.is_(None),
                )
                .order_by(GatewayTelemetryHistory.recorded_at.desc())
                .first()
            )
            if not latest or not isinstance(latest.raw_payload, dict):
                skipped_no_history += 1
                continue

            nvr = latest.raw_payload.get("nvr_surveillance") or {}
            cameras_info = nvr.get("cameras") or {}
            cam_list = cameras_info.get("camera_list") if isinstance(cameras_info, dict) else None
            if not cam_list:
                cam_list = nvr.get("camera_channels") or []

            active_ids = []
            for c in cam_list:
                if not isinstance(c, dict):
                    continue
                if c.get("is_online"):
                    cid = c.get("id") if c.get("id") is not None else c.get("channel")
                    if cid is not None and str(cid).strip() != "":
                        cid_str = str(cid).strip()
                        if cid_str not in active_ids:
                            active_ids.append(cid_str)

            if not active_ids:
                skipped_no_active += 1
                continue

            prop = dict(dev.property or {})
            prop["selected_cameras"] = active_ids
            prop["total_cameras"] = len(active_ids)
            dev.property = prop
            dev.updated_at = datetime.utcnow()
            flag_modified(dev, "property")
            updated += 1

        db.commit()
        print(
            f"Done! Total active devices: {len(devices)} | "
            f"Updated selected_cameras: {updated} | "
            f"Skipped (no telemetry): {skipped_no_history} | "
            f"Skipped (0 online cams): {skipped_no_active}"
        )
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sync_active_cameras()
