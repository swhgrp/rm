"""Demote active vendor items with incomplete UOM to needs_review

Revision ID: 20260125_0001
Revises: 20251228_0001
Create Date: 2026-01-25

This migration demotes all active vendor items that are missing required UOM fields
(size_quantity, size_unit_id, container_id, units_per_case) to needs_review status.

This ensures that items without proper UOM cannot be used for costing until fixed.
Items will appear in the "Needs Review" filter on the Vendor Items page.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260125_0001'
down_revision = '20251228_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Demote all active items with incomplete UOM to needs_review
    # Incomplete UOM means: size_quantity IS NULL OR size_unit_id IS NULL
    #                    OR container_id IS NULL OR units_per_case IS NULL OR units_per_case = 0
    op.execute("""
        UPDATE hub_vendor_items
        SET status = 'needs_review',
            notes = COALESCE(notes || E'\\n', '') ||
                    'Demoted to needs_review on 2026-01-25: Incomplete UOM data. Please set size, unit, and container fields.'
        WHERE status = 'active'
          AND (
              size_quantity IS NULL
              OR size_unit_id IS NULL
              OR container_id IS NULL
              OR units_per_case IS NULL
              OR units_per_case = 0
          )
    """)


def downgrade() -> None:
    # Revert items that were demoted back to active
    # This is a best-effort downgrade - it looks for items with the specific note
    op.execute("""
        UPDATE hub_vendor_items
        SET status = 'active',
            notes = REPLACE(
                notes,
                E'\\nDemoted to needs_review on 2026-01-25: Incomplete UOM data. Please set size, unit, and container fields.',
                ''
            )
        WHERE status = 'needs_review'
          AND notes LIKE '%Demoted to needs_review on 2026-01-25%'
    """)
