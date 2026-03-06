#!/usr/bin/env python3
"""
Backfill invoice items with canonical vendor item SKU and product name.

For all mapped invoice items (is_mapped=true, inventory_item_id IS NOT NULL),
sets item_code = vendor_sku and item_description = vendor_product_name from
the linked hub_vendor_items record.

Usage:
    docker compose exec integration-hub python scripts/backfill_invoice_item_names.py [--dry-run]
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text
from integration_hub.db.database import SessionLocal


def backfill(dry_run=False):
    db = SessionLocal()
    try:
        # Preview what will change
        preview = db.execute(text("""
            SELECT
                ii.id, ii.item_code AS old_code, vi.vendor_sku AS new_code,
                ii.item_description AS old_desc, vi.vendor_product_name AS new_desc
            FROM hub_invoice_items ii
            JOIN hub_vendor_items vi ON ii.inventory_item_id = vi.id
            WHERE ii.is_mapped = true
              AND (
                  (vi.vendor_sku IS NOT NULL AND ii.item_code IS DISTINCT FROM vi.vendor_sku)
                  OR (vi.vendor_product_name IS NOT NULL AND ii.item_description IS DISTINCT FROM vi.vendor_product_name)
              )
        """)).fetchall()

        print(f"Found {len(preview)} mapped invoice items that differ from vendor item canonical values")

        if preview:
            # Show sample
            for row in preview[:20]:
                changes = []
                if row.old_code != row.new_code and row.new_code:
                    changes.append(f"code: '{row.old_code}' → '{row.new_code}'")
                if row.old_desc != row.new_desc and row.new_desc:
                    changes.append(f"desc: '{(row.old_desc or '')[:50]}' → '{(row.new_desc or '')[:50]}'")
                print(f"  Item {row.id}: {', '.join(changes)}")
            if len(preview) > 20:
                print(f"  ... and {len(preview) - 20} more")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return

        # Do the update
        result = db.execute(text("""
            UPDATE hub_invoice_items ii
            SET
                item_code = COALESCE(vi.vendor_sku, ii.item_code),
                item_description = COALESCE(vi.vendor_product_name, ii.item_description)
            FROM hub_vendor_items vi
            WHERE ii.inventory_item_id = vi.id
              AND ii.is_mapped = true
              AND (
                  (vi.vendor_sku IS NOT NULL AND ii.item_code IS DISTINCT FROM vi.vendor_sku)
                  OR (vi.vendor_product_name IS NOT NULL AND ii.item_description IS DISTINCT FROM vi.vendor_product_name)
              )
        """))
        db.commit()
        print(f"\nUpdated {result.rowcount} invoice items with canonical vendor item values.")

    finally:
        db.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    backfill(dry_run=dry_run)
