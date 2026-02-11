"""Add price_is_per_unit column to hub_invoice_items

Revision ID: 20260211_0001
Revises: 20260125_0002
Create Date: 2026-02-11

Adds a boolean flag to indicate whether the invoice line item's unit_price
is per individual unit (EA/BTL) vs per case (CS). Set at mapping time by
comparing parsed UOM against vendor item's purchase_unit_abbr.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260211_0001'
down_revision = '20260125_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add price_is_per_unit column (nullable - NULL means not yet determined)
    op.add_column('hub_invoice_items',
        sa.Column('price_is_per_unit', sa.Boolean(), nullable=True,
                  comment='True if unit_price is per individual unit (EA/BTL), False if per case (CS). Set at mapping time.')
    )

    # Backfill: items with individual unit UOM → True
    op.execute("""
        UPDATE hub_invoice_items
        SET price_is_per_unit = TRUE
        WHERE UPPER(TRIM(unit_of_measure)) IN ('EA', 'EACH', 'BTL', 'BOTTLE', 'PC', 'PIECE')
          AND is_mapped = TRUE
    """)

    # Backfill: items with case UOM → False
    op.execute("""
        UPDATE hub_invoice_items
        SET price_is_per_unit = FALSE
        WHERE UPPER(TRIM(unit_of_measure)) IN ('CS', 'CASE')
          AND is_mapped = TRUE
          AND price_is_per_unit IS NULL
    """)

    # Backfill: mapped items linked to vendor items with purchase_unit_abbr = 'CS' → False
    op.execute("""
        UPDATE hub_invoice_items hii
        SET price_is_per_unit = FALSE
        FROM hub_vendor_items hvi
        WHERE hii.inventory_item_id = hvi.id
          AND hvi.purchase_unit_abbr = 'CS'
          AND hii.is_mapped = TRUE
          AND hii.price_is_per_unit IS NULL
    """)

    # Backfill: mapped items linked to vendor items with purchase_unit_abbr = 'EA' → True
    op.execute("""
        UPDATE hub_invoice_items hii
        SET price_is_per_unit = TRUE
        FROM hub_vendor_items hvi
        WHERE hii.inventory_item_id = hvi.id
          AND hvi.purchase_unit_abbr = 'EA'
          AND hii.is_mapped = TRUE
          AND hii.price_is_per_unit IS NULL
    """)


def downgrade() -> None:
    op.drop_column('hub_invoice_items', 'price_is_per_unit')
