"""device_schema_refactoring

Revision ID: 006_device_schema_refactoring
Revises: 005_base_model_audit_columns
Create Date: 2026-11-11 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '006_device_schema_refactoring'
down_revision: Union[str, None] = '005_base_model_audit_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Ensure pgcrypto or uuid-ossp extension exists for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # 1. Table: clients
    op.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            code VARCHAR(100) UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            created_by UUID,
            updated_by UUID,
            deleted_by UUID
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_clients_is_active ON clients (is_active);")

    # 2. Table: devices
    op.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
            name VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            lat DOUBLE PRECISION,
            long DOUBLE PRECISION,
            hardware_model VARCHAR(100),
            operational_start TIME,
            operational_end TIME,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            property JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            created_by UUID,
            updated_by UUID,
            deleted_by UUID
        );
    """)
    op.execute("ALTER TABLE devices ALTER COLUMN client_id DROP NOT NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_client_id ON devices (client_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_name ON devices (name);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_is_active ON devices (is_active);")

    # 3. Seed devices from existing distinct telemetry & alerts (without client_id)
    op.execute("""
        INSERT INTO devices (id, client_id, name, location, hardware_model, is_active)
        SELECT 
            gen_random_uuid(),
            NULL,
            t.device_id,
            t.location,
            t.hardware_model,
            TRUE
        FROM (
            SELECT DISTINCT ON (device_id) 
                device_id, 
                location, 
                hardware_model 
            FROM gateway_telemetry_history 
            WHERE device_id IS NOT NULL AND device_id::text != ''
            ORDER BY device_id, recorded_at DESC NULLS LAST
        ) t
        WHERE NOT EXISTS (
            SELECT 1 FROM devices d WHERE d.name = t.device_id
        );
    """)

    # Also seed any device_id that only exists in incident alerts
    op.execute("""
        INSERT INTO devices (id, client_id, name, is_active)
        SELECT DISTINCT
            gen_random_uuid(),
            NULL,
            a.device_id,
            TRUE
        FROM gateway_incident_alerts a
        WHERE a.device_id IS NOT NULL 
          AND a.device_id::text != ''
          AND NOT EXISTS (
              SELECT 1 FROM devices d WHERE d.name = a.device_id
          );
    """)

    # 4. Table: gateway_telemetry_history - Add audit columns if not exists
    op.execute("ALTER TABLE gateway_telemetry_history ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
    op.execute("ALTER TABLE gateway_telemetry_history ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

    # 5. Table: gateway_telemetry_history - Convert device_id VARCHAR to UUID FK
    # Check if device_id is already UUID or VARCHAR
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name']: str(c['type']) for c in insp.get_columns('gateway_telemetry_history')}

    if 'device_id' in cols and 'UUID' not in cols['device_id'].upper():
        op.execute("ALTER TABLE gateway_telemetry_history ADD COLUMN IF NOT EXISTS device_uuid UUID;")
        op.execute("""
            UPDATE gateway_telemetry_history th
            SET device_uuid = d.id
            FROM devices d
            WHERE th.device_id = d.name
              AND th.device_uuid IS NULL;
        """)
        op.execute("DROP INDEX IF EXISTS ix_gateway_telemetry_history_device_id;")
        op.execute("ALTER TABLE gateway_telemetry_history DROP COLUMN device_id;")
        op.execute("ALTER TABLE gateway_telemetry_history RENAME COLUMN device_uuid TO device_id;")
        op.execute("ALTER TABLE gateway_telemetry_history ALTER COLUMN device_id SET NOT NULL;")
        op.execute("CREATE INDEX IF NOT EXISTS ix_gateway_telemetry_history_device_id ON gateway_telemetry_history (device_id);")
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_telemetry_history_device'
                ) THEN
                    ALTER TABLE gateway_telemetry_history
                    ADD CONSTRAINT fk_telemetry_history_device
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """)

    # 6. Table: gateway_incident_alerts - Convert device_id VARCHAR to UUID FK
    alert_cols = {c['name']: str(c['type']) for c in insp.get_columns('gateway_incident_alerts')}
    if 'device_id' in alert_cols and 'UUID' not in alert_cols['device_id'].upper():
        op.execute("ALTER TABLE gateway_incident_alerts ADD COLUMN IF NOT EXISTS device_uuid UUID;")
        op.execute("""
            UPDATE gateway_incident_alerts gia
            SET device_uuid = d.id
            FROM devices d
            WHERE gia.device_id = d.name
              AND gia.device_uuid IS NULL;
        """)
        op.execute("DROP INDEX IF EXISTS idx_gia_device_id;")
        op.execute("ALTER TABLE gateway_incident_alerts DROP COLUMN device_id;")
        op.execute("ALTER TABLE gateway_incident_alerts RENAME COLUMN device_uuid TO device_id;")
        op.execute("ALTER TABLE gateway_incident_alerts ALTER COLUMN device_id SET NOT NULL;")
        op.execute("CREATE INDEX IF NOT EXISTS idx_gia_device_id ON gateway_incident_alerts (device_id);")
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_incident_alerts_device'
                ) THEN
                    ALTER TABLE gateway_incident_alerts
                    ADD CONSTRAINT fk_incident_alerts_device
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """)


def downgrade() -> None:
    # Downgrade drops constraints and tables in reverse dependency order
    op.execute("ALTER TABLE gateway_incident_alerts DROP CONSTRAINT IF EXISTS fk_incident_alerts_device;")
    op.execute("ALTER TABLE gateway_telemetry_history DROP CONSTRAINT IF EXISTS fk_telemetry_history_device;")
    op.execute("DROP TABLE IF EXISTS devices CASCADE;")
    op.execute("DROP TABLE IF EXISTS clients CASCADE;")
