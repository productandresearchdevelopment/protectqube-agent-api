from typing import Sequence, Union
from alembic import op

revision: str = '005_base_model_audit_columns'
down_revision: Union[str, None] = '004_notification_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = [
    'roles',
    'module_types',
    'modules',
    'role_modules',
    'uploads',
    'users',
    'user_sessions',
    'user_otps',
    'gateway_telemetry_history',
    'gateway_incident_alerts',
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_by VARCHAR(36);")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(36);")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS created_by;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS updated_by;")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS deleted_by;")
