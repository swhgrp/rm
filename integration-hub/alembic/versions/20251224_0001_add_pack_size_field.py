"""Add pack_size field to hub_invoice_items

Revision ID: 20251224_0001
Revises: 20251221_0001
Create Date: 2025-12-24
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251224_0001'
down_revision = '20251221_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add pack_size column to hub_invoice_items
    op.add_column('hub_invoice_items', sa.Column('pack_size', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('hub_invoice_items', 'pack_size')
