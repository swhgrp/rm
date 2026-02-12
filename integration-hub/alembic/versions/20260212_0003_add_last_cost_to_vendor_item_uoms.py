"""Add last_cost and last_cost_date to vendor_item_uoms

Revision ID: 20260212_0003
Revises: 20260212_0002
Create Date: 2026-02-11

Tracks the most recent invoice price per purchase UOM,
auto-populated by the cost updater when processing invoices.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260212_0003'
down_revision = '20260212_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vendor_item_uoms', sa.Column('last_cost', sa.Numeric(10, 4), nullable=True))
    op.add_column('vendor_item_uoms', sa.Column('last_cost_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('vendor_item_uoms', 'last_cost_date')
    op.drop_column('vendor_item_uoms', 'last_cost')
