"""Add sharing tables

Revision ID: 20251029_0001
Revises:
Create Date: 2025-10-29 03:45:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251029_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add can_share column to existing folder_permissions table
    op.add_column('folder_permissions', sa.Column('can_share', sa.Boolean(), nullable=False, server_default='false'))

    # Create share_links table
    op.create_table('share_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_type', sa.Enum('FOLDER', 'FILE', name='sharelinktype'), nullable=False),
        sa.Column('folder_id', sa.Integer(), nullable=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('share_token', sa.String(length=64), nullable=False),
        sa.Column('access_type', sa.Enum('READ_ONLY', 'UPLOAD_ONLY', 'READ_WRITE', 'EDIT', 'ADMIN', name='shareaccesstype'), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('require_login', sa.Boolean(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_downloads', sa.Integer(), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('use_count', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('allow_download', sa.Boolean(), nullable=True),
        sa.Column('allow_preview', sa.Boolean(), nullable=True),
        sa.Column('notify_on_access', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_share_links_id'), 'share_links', ['id'], unique=False)
    op.create_index(op.f('ix_share_links_share_token'), 'share_links', ['share_token'], unique=True)

    # Create share_access_logs table
    op.create_table('share_access_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('share_link_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['share_link_id'], ['share_links.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_share_access_logs_id'), 'share_access_logs', ['id'], unique=False)

    # Create internal_shares table
    op.create_table('internal_shares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_type', sa.Enum('FOLDER', 'FILE', name='sharelinktype'), nullable=False),
        sa.Column('folder_id', sa.Integer(), nullable=True),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('shared_with_user_id', sa.Integer(), nullable=True),
        sa.Column('shared_with_group_id', sa.Integer(), nullable=True),
        sa.Column('shared_with_role', sa.String(length=50), nullable=True),
        sa.Column('shared_with_department', sa.String(length=100), nullable=True),
        sa.Column('shared_with_location', sa.String(length=100), nullable=True),
        sa.Column('can_view', sa.Boolean(), nullable=True),
        sa.Column('can_download', sa.Boolean(), nullable=True),
        sa.Column('can_upload', sa.Boolean(), nullable=True),
        sa.Column('can_edit', sa.Boolean(), nullable=True),
        sa.Column('can_delete', sa.Boolean(), nullable=True),
        sa.Column('can_share', sa.Boolean(), nullable=True),
        sa.Column('can_comment', sa.Boolean(), nullable=True),
        sa.Column('shared_by', sa.Integer(), nullable=False),
        sa.Column('shared_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('notify_by_email', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['file_id'], ['file_metadata.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint('shared_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_internal_shares_id'), 'internal_shares', ['id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_internal_shares_id'), table_name='internal_shares')
    op.drop_table('internal_shares')

    op.drop_index(op.f('ix_share_access_logs_id'), table_name='share_access_logs')
    op.drop_table('share_access_logs')

    op.drop_index(op.f('ix_share_links_share_token'), table_name='share_links')
    op.drop_index(op.f('ix_share_links_id'), table_name='share_links')
    op.drop_table('share_links')

    # Drop enums
    op.execute('DROP TYPE shareaccesstype')
    op.execute('DROP TYPE sharelinktype')

    # Remove can_share column from folder_permissions
    op.drop_column('folder_permissions', 'can_share')
