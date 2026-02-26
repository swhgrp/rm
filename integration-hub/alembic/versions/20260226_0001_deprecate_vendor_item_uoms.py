"""Deprecate vendor_item_uoms - drop FK from hub_invoice_items

Removes the matched_uom_id FK constraint from hub_invoice_items
and nulls out the column. The vendor_item_uoms table is kept for
historical data but is no longer actively used.

Each vendor item now has a single purchase UOM defined by its own
purchase_unit_abbr + pack_to_primary_factor fields.

Revision ID: 20260226_0001
Revises: 20260224_0001
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260226_0001'
down_revision = '20260224_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the FK constraint from hub_invoice_items.matched_uom_id → vendor_item_uoms
    op.drop_constraint(
        'hub_invoice_items_matched_uom_id_fkey',
        'hub_invoice_items',
        type_='foreignkey'
    )

    # Null out all matched_uom_id values (no longer used)
    op.execute("UPDATE hub_invoice_items SET matched_uom_id = NULL WHERE matched_uom_id IS NOT NULL")

    # Drop the index (no longer needed since column is unused)
    op.drop_index('ix_hub_invoice_items_matched_uom_id', 'hub_invoice_items')


def downgrade() -> None:
    # Recreate the index
    op.create_index('ix_hub_invoice_items_matched_uom_id',
                     'hub_invoice_items', ['matched_uom_id'])

    # Recreate the FK constraint
    op.create_foreign_key(
        'hub_invoice_items_matched_uom_id_fkey',
        'hub_invoice_items',
        'vendor_item_uoms',
        ['matched_uom_id'],
        ['id']
    )
