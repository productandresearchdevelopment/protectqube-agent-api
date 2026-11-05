"""update_incident_alerts_and_telemetry

Revision ID: 003_incident_alerts
Revises: 002_seed_initial_auth_data
Create Date: 2026-11-05 15:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_incident_alerts'
down_revision: Union[str, None] = '002_seed_initial_auth_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. gateway_telemetry_history
    if 'gateway_telemetry_history' not in existing_tables:
        op.create_table(
            'gateway_telemetry_history',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('device_id', sa.String(length=50), nullable=False),
            sa.Column('recorded_at', sa.DateTime(), nullable=True),
            sa.Column('overall_status', sa.String(length=20), nullable=True),
            sa.Column('location', sa.String(length=100), nullable=True),
            sa.Column('hardware_model', sa.String(length=100), nullable=True),
            sa.Column('cpu_percent', sa.Float(), nullable=True),
            sa.Column('temperature_c', sa.Float(), nullable=True),
            sa.Column('ram_used_mb', sa.Float(), nullable=True),
            sa.Column('ram_total_mb', sa.Float(), nullable=True),
            sa.Column('disk_used_percent', sa.Float(), nullable=True),
            sa.Column('operator', sa.String(length=50), nullable=True),
            sa.Column('sim_status', sa.String(length=50), nullable=True),
            sa.Column('signal_csq', sa.Integer(), nullable=True),
            sa.Column('signal_rsrp', sa.Integer(), nullable=True),
            sa.Column('phone_number', sa.String(length=50), nullable=True),
            sa.Column('cellular_ip', sa.String(length=50), nullable=True),
            sa.Column('nvr_status', sa.String(length=50), nullable=True),
            sa.Column('nvr_recording', sa.Boolean(), nullable=True),
            sa.Column('cameras_online', sa.Integer(), nullable=True),
            sa.Column('cameras_total', sa.Integer(), nullable=True),
            sa.Column('raw_payload', sa.JSON(), nullable=True),
        )
        op.create_index('ix_gateway_telemetry_history_device_id', 'gateway_telemetry_history', ['device_id'])
        op.create_index('ix_gateway_telemetry_history_recorded_at', 'gateway_telemetry_history', ['recorded_at'])

    # 2. gateway_incident_alerts
    recreate_alerts = False
    if 'gateway_incident_alerts' in existing_tables:
        existing_cols = [c['name'] for c in inspector.get_columns('gateway_incident_alerts')]
        if 'metric' not in existing_cols:
            op.drop_table('gateway_incident_alerts')
            recreate_alerts = True
    else:
        recreate_alerts = True

    if recreate_alerts:
        op.create_table(
            'gateway_incident_alerts',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('device_id', sa.String(length=50), nullable=False),
            sa.Column('telemetry_history_id', sa.String(length=36), sa.ForeignKey('gateway_telemetry_history.id', ondelete='SET NULL'), nullable=True),
            sa.Column('metric', sa.String(length=30), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('start_time', sa.DateTime(), nullable=False),
            sa.Column('end_time', sa.DateTime(), nullable=True),
            sa.Column('duration_minutes', sa.Float(), nullable=True, server_default='0.0'),
            sa.Column('duration_str', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True, server_default='RESOLVED'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_gateway_incident_alerts_device_id', 'gateway_incident_alerts', ['device_id'])
        op.create_index('ix_gateway_incident_alerts_telemetry_history_id', 'gateway_incident_alerts', ['telemetry_history_id'])
        op.create_index('ix_gateway_incident_alerts_metric', 'gateway_incident_alerts', ['metric'])
        op.create_index('ix_gateway_incident_alerts_start_time', 'gateway_incident_alerts', ['start_time'])
        op.create_index('ix_gateway_incident_alerts_status', 'gateway_incident_alerts', ['status'])


def downgrade() -> None:
    op.drop_table('gateway_incident_alerts')
    op.drop_table('gateway_telemetry_history')
