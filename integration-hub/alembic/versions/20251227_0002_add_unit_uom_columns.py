"""Add unit_uom columns to hub_vendor_items for price comparison

Revision ID: 20251227_0002
Revises: 20251227_0001
Create Date: 2025-12-27

Unit UOM captures individual unit size within pack (750ml, 1L, 25lb, etc.)
This enables price-per-unit comparisons across different pack configurations.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251227_0002'
down_revision = '20251227_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unit_uom_id - references units_of_measure for individual unit size
    op.add_column('hub_vendor_items', sa.Column('unit_uom_id', sa.Integer(), nullable=True))

    # Add cached unit_uom_name for display
    op.add_column('hub_vendor_items', sa.Column('unit_uom_name', sa.String(50), nullable=True))

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_hub_vendor_items_unit_uom',
        'hub_vendor_items',
        'units_of_measure',
        ['unit_uom_id'],
        ['id']
    )

    # Create index for unit_uom_id
    op.create_index('ix_hub_vendor_items_unit_uom_id', 'hub_vendor_items', ['unit_uom_id'])


def downgrade() -> None:
    op.drop_index('ix_hub_vendor_items_unit_uom_id', table_name='hub_vendor_items')
    op.drop_constraint('fk_hub_vendor_items_unit_uom', 'hub_vendor_items', type_='foreignkey')
    op.drop_column('hub_vendor_items', 'unit_uom_name')
    op.drop_column('hub_vendor_items', 'unit_uom_id')
