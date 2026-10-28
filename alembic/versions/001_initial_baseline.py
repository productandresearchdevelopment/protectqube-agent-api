"""initial_baseline_models

Revision ID: 001_initial_baseline
Revises: 
Create Date: 2026-10-27 11:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. roles
    op.create_table(
        'roles',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('alias', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=False, server_default='#3b82f6'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_roles_name', 'roles', ['name'])

    # 2. module_types
    op.create_table(
        'module_types',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )

    # 3. modules
    op.create_table(
        'modules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('module_type_id', sa.String(length=36), sa.ForeignKey('module_types.id', onupdate='CASCADE', ondelete='RESTRICT'), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('modules.id', onupdate='CASCADE', ondelete='SET NULL'), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('route', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_modules_module_type_id', 'modules', ['module_type_id'])
    op.create_index('ix_modules_parent_id', 'modules', ['parent_id'])

    # 4. role_modules
    op.create_table(
        'role_modules',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('role_id', sa.String(length=36), sa.ForeignKey('roles.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False),
        sa.Column('module_id', sa.Integer(), sa.ForeignKey('modules.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False),
        sa.Column('checked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_role_modules_role_id', 'role_modules', ['role_id'])
    op.create_index('ix_role_modules_module_id', 'role_modules', ['module_id'])

    # 5. uploads
    op.create_table(
        'uploads',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('mime', sa.String(length=100), nullable=False),
        sa.Column('extension', sa.String(length=20), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('filename_origin', sa.String(length=255), nullable=False),
        sa.Column('bucket', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )

    # 6. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('avatar_id', sa.String(length=36), sa.ForeignKey('uploads.id', onupdate='CASCADE', ondelete='SET NULL'), unique=True, nullable=True),
        sa.Column('role_id', sa.String(length=36), sa.ForeignKey('roles.id', onupdate='CASCADE', ondelete='RESTRICT'), nullable=False),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('email_verified_at', sa.DateTime(), nullable=True),
        sa.Column('email_verification_status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_role_id', 'users', ['role_id'])

    # 7. user_sessions
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False),
        sa.Column('refresh_token_hash', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('device_name', sa.String(length=100), nullable=True),
        sa.Column('last_module_id', sa.Integer(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])

    # 8. user_otps
    op.create_table(
        'user_otps',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', onupdate='CASCADE', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('otp_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('cooldown_until', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_otps_user_id', 'user_otps', ['user_id'])


def downgrade() -> None:
    op.drop_table('user_otps')
    op.drop_table('user_sessions')
    op.drop_table('users')
    op.drop_table('uploads')
    op.drop_table('role_modules')
    op.drop_table('modules')
    op.drop_table('module_types')
    op.drop_table('roles')
