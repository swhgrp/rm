#!/usr/bin/env python3
"""
Backfill vendor item product names to title case.

Usage:
    docker compose exec integration-hub python scripts/backfill_vendor_item_names.py [--dry-run]
"""
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text
from integration_hub.utils.text_utils import to_title_case
from integration_hub.db.database import SessionLocal


def backfill(dry_run=False):
    db = SessionLocal()
    try:
        # Get all vendor items
        rows = db.execute(
            text("SELECT id, vendor_product_name FROM hub_vendor_items ORDER BY id")
        ).fetchall()

        updated = 0
        skipped = 0

        for row in rows:
            item_id, name = row
            if not name:
                skipped += 1
                continue

            new_name = to_title_case(name)
            if new_name == name:
                skipped += 1
                continue

            if dry_run:
                print(f"  [{item_id}] {name!r} -> {new_name!r}")
            else:
                db.execute(
                    text("UPDATE hub_vendor_items SET vendor_product_name = :name, updated_at = NOW() WHERE id = :id"),
                    {"name": new_name, "id": item_id}
                )
            updated += 1

        if not dry_run:
            db.commit()

        print(f"\nDone: {updated} updated, {skipped} already correct (total: {len(rows)})")
        if dry_run:
            print("(dry run — no changes written)")

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    backfill(dry_run=dry_run)
