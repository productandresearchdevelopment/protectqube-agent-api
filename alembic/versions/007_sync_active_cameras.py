"""sync_active_cameras

Revision ID: 007_sync_active_cameras
Revises: 006_device_schema_refactoring
Create Date: 2026-11-12 18:42:00.000000

"""
import json
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '007_sync_active_cameras'
down_revision: Union[str, None] = '006_device_schema_refactoring'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Auto-populate devices.property['selected_cameras'] and ['total_cameras']
    from each device's latest gateway_telemetry_history snapshot (is_online=True).
    """
    bind = op.get_bind()

    devices = bind.execute(
        sa.text("SELECT id, property FROM devices WHERE deleted_at IS NULL")
    ).fetchall()

    for dev_id, raw_prop in devices:
        prop = dict(raw_prop) if isinstance(raw_prop, dict) else {}
        if prop.get("selected_cameras"):
            continue

        latest = bind.execute(
            sa.text("""
                SELECT raw_payload
                FROM gateway_telemetry_history
                WHERE device_id = :dev_id
                  AND deleted_at IS NULL
                ORDER BY recorded_at DESC NULLS LAST
                LIMIT 1
            """),
            {"dev_id": dev_id},
        ).fetchone()

        if not latest or not isinstance(latest[0], dict):
            continue

        raw_payload = latest[0]
        nvr = raw_payload.get("nvr_surveillance") or {}
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
            continue

        prop["selected_cameras"] = active_ids
        prop["total_cameras"] = len(active_ids)

        bind.execute(
            sa.text("""
                UPDATE devices
                SET property = CAST(:prop AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :dev_id
            """),
            {"prop": json.dumps(prop), "dev_id": dev_id},
        )


def downgrade() -> None:
    pass
