"""seed_initial_auth_data

Revision ID: 002_seed_initial_auth_data
Revises: 001_initial_baseline
Create Date: 2026-10-28 17:05:00.000000

"""
from typing import Sequence, Union
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision: str = '002_seed_initial_auth_data'
down_revision: Union[str, None] = '001_initial_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

now = datetime.utcnow()

# Seed IDs
SUPER_ADMIN_ROLE_ID = "a93f5563-415b-4733-8f46-5249009da2c3"
FIELD_ENGINEER_ROLE_ID = "ec52373a-c444-453a-a59a-52db228e59af"
MONITORING_MODULE_TYPE_ID = "b11c97a2-1b1a-4f51-b825-911223344556"
ADMIN_USER_ID = "a6066a42-caef-4c20-af86-51d004449ef8"
ADMIN_PASSWORD_HASH = "$2b$12$EibK34ognTvLscr1bZ6DZu18B07oE24DBhpvgru4VG3sWhhJA43y."  # admin123


def upgrade() -> None:
    # 1. Seed Roles
    roles_table = sa.table(
        'roles',
        sa.column('id', sa.String),
        sa.column('name', sa.String),
        sa.column('alias', sa.String),
        sa.column('color', sa.String),
        sa.column('description', sa.Text),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(
        roles_table,
        [
            {
                'id': SUPER_ADMIN_ROLE_ID,
                'name': 'Super Admin',
                'alias': 'super-admin',
                'color': '#2563eb',
                'description': 'Full access to ProtectQube AI Ops Gateway and Telemetry',
                'created_at': now,
                'updated_at': now,
            },
            {
                'id': FIELD_ENGINEER_ROLE_ID,
                'name': 'Field Engineer',
                'alias': 'engineer',
                'color': '#10b981',
                'description': 'Field technician for gateway inspection and maintenance',
                'created_at': now,
                'updated_at': now,
            },
        ]
    )

    # 2. Seed Module Type
    module_types_table = sa.table(
        'module_types',
        sa.column('id', sa.String),
        sa.column('name', sa.String),
        sa.column('icon', sa.String),
        sa.column('description', sa.Text),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(
        module_types_table,
        [
            {
                'id': MONITORING_MODULE_TYPE_ID,
                'name': 'Monitoring',
                'icon': 'Activity',
                'description': 'Diagnostic & telemetry monitoring modules',
                'created_at': now,
                'updated_at': now,
            }
        ]
    )

    # 3. Seed Modules
    modules_table = sa.table(
        'modules',
        sa.column('id', sa.Integer),
        sa.column('module_type_id', sa.String),
        sa.column('name', sa.String),
        sa.column('icon', sa.String),
        sa.column('route', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(
        modules_table,
        [
            {'id': 1, 'module_type_id': MONITORING_MODULE_TYPE_ID, 'name': 'Dashboard', 'icon': 'LayoutDashboard', 'route': '/', 'created_at': now, 'updated_at': now},
            {'id': 2, 'module_type_id': MONITORING_MODULE_TYPE_ID, 'name': 'Cellular Connectivity', 'icon': 'Radio', 'route': '#cellular', 'created_at': now, 'updated_at': now},
            {'id': 3, 'module_type_id': MONITORING_MODULE_TYPE_ID, 'name': 'DVR Recording', 'icon': 'Video', 'route': '#dvr', 'created_at': now, 'updated_at': now},
            {'id': 4, 'module_type_id': MONITORING_MODULE_TYPE_ID, 'name': 'System Health', 'icon': 'Activity', 'route': '#system', 'created_at': now, 'updated_at': now},
            {'id': 5, 'module_type_id': MONITORING_MODULE_TYPE_ID, 'name': 'Reports', 'icon': 'FileText', 'route': '#reports', 'created_at': now, 'updated_at': now},
        ]
    )

    # 4. Seed Role Modules (Permissions for Super Admin)
    role_modules_table = sa.table(
        'role_modules',
        sa.column('id', sa.String),
        sa.column('role_id', sa.String),
        sa.column('module_id', sa.Integer),
        sa.column('checked', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(
        role_modules_table,
        [
            {'id': f"rm-admin-mod-{m_id}", 'role_id': SUPER_ADMIN_ROLE_ID, 'module_id': m_id, 'checked': True, 'created_at': now, 'updated_at': now}
            for m_id in range(1, 6)
        ]
    )

    # 5. Seed Default Admin User
    users_table = sa.table(
        'users',
        sa.column('id', sa.String),
        sa.column('name', sa.String),
        sa.column('username', sa.String),
        sa.column('email', sa.String),
        sa.column('password', sa.String),
        sa.column('role_id', sa.String),
        sa.column('email_verified', sa.Boolean),
        sa.column('email_verification_status', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    op.bulk_insert(
        users_table,
        [
            {
                'id': ADMIN_USER_ID,
                'name': 'SmartBox Administrator',
                'username': 'admin',
                'email': 'admin@smartbox.local',
                'password': ADMIN_PASSWORD_HASH,
                'role_id': SUPER_ADMIN_ROLE_ID,
                'email_verified': True,
                'email_verification_status': 'VERIFIED',
                'created_at': now,
                'updated_at': now,
            }
        ]
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM users WHERE id = '{ADMIN_USER_ID}'")
    op.execute(f"DELETE FROM role_modules WHERE role_id = '{SUPER_ADMIN_ROLE_ID}'")
    op.execute(f"DELETE FROM modules WHERE module_type_id = '{MONITORING_MODULE_TYPE_ID}'")
    op.execute(f"DELETE FROM module_types WHERE id = '{MONITORING_MODULE_TYPE_ID}'")
    op.execute(f"DELETE FROM roles WHERE id IN ('{SUPER_ADMIN_ROLE_ID}', '{FIELD_ENGINEER_ROLE_ID}')")
