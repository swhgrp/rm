"""add portal access permissions

Revision ID: portal_access_001
Revises: 20251016_0339_d56ff029a98b
Create Date: 2025-10-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'portal_access_001'
down_revision = 'd56ff029a98b'
branch_labels = None
depends_on = None


def upgrade():
    # Add portal access permission columns
    op.add_column('users', sa.Column('can_access_portal', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('can_access_inventory', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('can_access_accounting', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('can_access_integration_hub', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('can_access_hr', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('accounting_role_id', sa.Integer(), nullable=True))


def downgrade():
    # Remove portal access permission columns
    op.drop_column('users', 'accounting_role_id')
    op.drop_column('users', 'can_access_hr')
    op.drop_column('users', 'can_access_integration_hub')
    op.drop_column('users', 'can_access_accounting')
    op.drop_column('users', 'can_access_inventory')
    op.drop_column('users', 'can_access_portal')
