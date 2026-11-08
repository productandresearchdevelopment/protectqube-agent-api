from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004_notification_system'
down_revision: Union[str, None] = '003_incident_alerts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'notification_events' not in existing_tables:
        op.create_table(
            'notification_events',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('event_code', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('category', sa.String(length=50), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('channels', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.String(length=36), nullable=True),
            sa.Column('updated_by', sa.String(length=36), nullable=True),
            sa.Column('deleted_by', sa.String(length=36), nullable=True),
        )
        op.create_index('ix_notification_events_event_code', 'notification_events', ['event_code'], unique=True)
        op.create_index('ix_notification_events_category', 'notification_events', ['category'])

    if 'notification_destinations' not in existing_tables:
        op.create_table(
            'notification_destinations',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('provider_key', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('config', sa.JSON(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='CONNECTED'),
            sa.Column('last_tested_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.String(length=36), nullable=True),
            sa.Column('updated_by', sa.String(length=36), nullable=True),
            sa.Column('deleted_by', sa.String(length=36), nullable=True),
        )
        op.create_index('ix_notification_destinations_provider_key', 'notification_destinations', ['provider_key'])

    if 'notification_targets' not in existing_tables:
        op.create_table(
            'notification_targets',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('provider_key', sa.String(length=50), nullable=False),
            sa.Column('external_id', sa.String(length=255), nullable=False),
            sa.Column('display_name', sa.String(length=255), nullable=False),
            sa.Column('type', sa.String(length=50), nullable=False, server_default='chat'),
            sa.Column('source', sa.String(length=50), nullable=False, server_default='manual'),
            sa.Column('config', sa.JSON(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('last_synced_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.String(length=36), nullable=True),
            sa.Column('updated_by', sa.String(length=36), nullable=True),
            sa.Column('deleted_by', sa.String(length=36), nullable=True),
        )
        op.create_index('ix_notification_targets_provider_key', 'notification_targets', ['provider_key'])
        op.create_index('ix_notification_targets_external_id', 'notification_targets', ['external_id'])

    if 'notifications' not in existing_tables:
        op.create_table(
            'notifications',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('event_code', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('severity', sa.String(length=20), nullable=False, server_default='WARNING'),
            sa.Column('data', sa.JSON(), nullable=True),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.String(length=36), nullable=True),
            sa.Column('updated_by', sa.String(length=36), nullable=True),
            sa.Column('deleted_by', sa.String(length=36), nullable=True),
        )
        op.create_index('ix_notifications_event_code', 'notifications', ['event_code'])
        op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
        op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])

    if 'notification_deliveries' not in existing_tables:
        op.create_table(
            'notification_deliveries',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('notification_id', sa.String(length=36), nullable=True),
            sa.Column('destination_id', sa.String(length=36), nullable=True),
            sa.Column('channel_type', sa.String(length=50), nullable=False),
            sa.Column('recipient', sa.String(length=255), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='SUCCESS'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('response_payload', sa.JSON(), nullable=True),
            sa.Column('sent_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_by', sa.String(length=36), nullable=True),
            sa.Column('updated_by', sa.String(length=36), nullable=True),
            sa.Column('deleted_by', sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['destination_id'], ['notification_destinations.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_notification_deliveries_notification_id', 'notification_deliveries', ['notification_id'])
        op.create_index('ix_notification_deliveries_destination_id', 'notification_deliveries', ['destination_id'])
        op.create_index('ix_notification_deliveries_channel_type', 'notification_deliveries', ['channel_type'])
        op.create_index('ix_notification_deliveries_status', 'notification_deliveries', ['status'])
        op.create_index('ix_notification_deliveries_sent_at', 'notification_deliveries', ['sent_at'])


def downgrade() -> None:
    op.drop_table('notification_deliveries')
    op.drop_table('notifications')
    op.drop_table('notification_targets')
    op.drop_table('notification_destinations')
    op.drop_table('notification_events')
