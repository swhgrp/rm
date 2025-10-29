"""Initial migration - Add Nextcloud credential fields to users

Revision ID: 20251028_0001
Revises:
Create Date: 2025-10-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20251028_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add Nextcloud-specific fields to users table

    Note: This assumes the users table already exists in the HR database.
    We're just adding additional columns for Nextcloud integration.
    """
    # Add Nextcloud credential columns
    op.add_column('users', sa.Column('nextcloud_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('nextcloud_encrypted_password', sa.String(), nullable=True))
    op.add_column('users', sa.Column('can_access_nextcloud', sa.Boolean(), server_default='true'))


def downgrade() -> None:
    """Remove Nextcloud fields"""
    op.drop_column('users', 'can_access_nextcloud')
    op.drop_column('users', 'nextcloud_encrypted_password')
    op.drop_column('users', 'nextcloud_username')
