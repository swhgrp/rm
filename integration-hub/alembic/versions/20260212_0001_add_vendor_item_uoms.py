"""Add vendor_item_uoms table and matched_uom_id to invoice items

Revision ID: 20260212_0001
Revises: 20260211_0001
Create Date: 2026-02-12

Creates the vendor_item_uoms junction table for multi-UOM vendor items.
Each vendor item can have multiple purchase UOMs (e.g., Case + Each) with
conversion factors. Adds matched_uom_id FK to hub_invoice_items to replace
the fragile price_is_per_unit flag.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260212_0001'
down_revision = '20260211_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create vendor_item_uoms table
    op.create_table(
        'vendor_item_uoms',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('vendor_item_id', sa.Integer(),
                  sa.ForeignKey('hub_vendor_items.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('uom_id', sa.Integer(),
                  sa.ForeignKey('units_of_measure.id'),
                  nullable=False),
        sa.Column('conversion_factor', sa.Numeric(20, 10), nullable=False,
                  server_default='1.0',
                  comment='Inventory primary units per 1 of this purchase UOM'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false',
                  comment='True if this is the primary purchase UOM for this vendor item'),
        sa.Column('expected_price', sa.Numeric(10, 4), nullable=True,
                  comment='Expected price for anomaly detection'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint('vendor_item_id', 'uom_id', name='uq_vendor_item_uom_pair'),
    )

    # Add matched_uom_id to hub_invoice_items
    op.add_column(
        'hub_invoice_items',
        sa.Column('matched_uom_id', sa.Integer(),
                  sa.ForeignKey('vendor_item_uoms.id'),
                  nullable=True,
                  comment='Matched purchase UOM from vendor item (replaces price_is_per_unit)')
    )
    op.create_index('ix_hub_invoice_items_matched_uom_id',
                     'hub_invoice_items', ['matched_uom_id'])


def downgrade() -> None:
    op.drop_index('ix_hub_invoice_items_matched_uom_id', 'hub_invoice_items')
    op.drop_column('hub_invoice_items', 'matched_uom_id')
    op.drop_table('vendor_item_uoms')
