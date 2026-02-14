"""Add send_to_inventory and send_to_accounting intent flags to vendors

Revision ID: 20260213_0002
Revises: 20260213_0001
Create Date: 2026-02-13

Stores the user's intent for which systems a vendor should sync to.
Previously, the sync process auto-pushed vendors to ALL systems,
ignoring whether the user only wanted e.g. Accounting but not Inventory.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260213_0002'
down_revision = '20260213_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default True so existing vendors (which were already pushed to both) keep their status
    op.add_column('vendors', sa.Column('send_to_inventory', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('vendors', sa.Column('send_to_accounting', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('vendors', 'send_to_accounting')
    op.drop_column('vendors', 'send_to_inventory')
