"""
Backfill master item UOMs from Hub vendor items.

Re-runs sync_master_item_defaults() for all mapped vendor items to fix UOMs
that were incorrectly set by the old sync logic (which fell back to "Each").

Usage:
    docker compose exec integration-hub python scripts/backfill_master_item_uoms.py --dry-run
    docker compose exec integration-hub python scripts/backfill_master_item_uoms.py
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('HUB_INTERNAL_API_KEY', os.getenv('HUB_INTERNAL_API_KEY', 'dummy'))

from sqlalchemy import text, create_engine
from integration_hub.db.database import SessionLocal
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.api.vendor_items import (
    _find_inventory_uom, _find_specific_container_uom, sync_master_item_defaults
)


def main():
    parser = argparse.ArgumentParser(description='Backfill master item UOMs from Hub vendor items')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without applying')
    args = parser.parse_args()

    db = SessionLocal()
    inv_url = os.getenv(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )
    inv_engine = create_engine(inv_url)

    items = (
        db.query(HubVendorItem)
        .filter(
            HubVendorItem.inventory_master_item_id.isnot(None),
            HubVendorItem.size_unit_id.isnot(None)
        )
        .all()
    )

    print(f"Found {len(items)} mapped vendor items with size units")
    print()

    changes = []
    skipped = []
    unresolvable = []

    with inv_engine.connect() as conn:
        for item in items:
            # Resolve UOM with new priority order
            uom = None

            # 1. Container+size specific UOM
            if item.container_id and item.size_quantity and item.size_unit_id:
                container = db.execute(
                    text('SELECT name FROM hub_containers WHERE id = :id'),
                    {'id': item.container_id}
                ).fetchone()
                size_unit = db.execute(
                    text('SELECT symbol FROM hub_size_units WHERE id = :id'),
                    {'id': item.size_unit_id}
                ).fetchone()
                if container and size_unit:
                    uom = _find_specific_container_uom(
                        conn, container[0], float(item.size_quantity), size_unit[0]
                    )

            # 2. Size unit symbol/name
            if not uom:
                size_unit = db.execute(
                    text('SELECT symbol, name FROM hub_size_units WHERE id = :id'),
                    {'id': item.size_unit_id}
                ).fetchone()
                if size_unit and size_unit[0]:
                    uom = _find_inventory_uom(conn, abbreviation=size_unit[0])
                    if not uom:
                        uom = _find_inventory_uom(conn, name=size_unit[1])

            if not uom:
                su = db.execute(
                    text('SELECT symbol FROM hub_size_units WHERE id = :id'),
                    {'id': item.size_unit_id}
                ).fetchone()
                unresolvable.append(
                    f"  VI {item.id}: {item.vendor_product_name[:50]} (size_unit: {su[0] if su else '?'})"
                )
                continue

            # Check current master item state
            master = conn.execute(
                text('SELECT primary_uom_id, primary_uom_name FROM master_items WHERE id = :id'),
                {'id': item.inventory_master_item_id}
            ).fetchone()
            if not master:
                continue

            if master[0] == uom[0]:
                skipped.append(item.id)
                continue

            changes.append({
                'vi_id': item.id,
                'name': item.vendor_product_name[:50],
                'master_id': item.inventory_master_item_id,
                'current': master[1] or 'None',
                'new': uom[1],
            })

    print(f"Results:")
    print(f"  Already correct: {len(skipped)}")
    print(f"  Need update: {len(changes)}")
    print(f"  Unresolvable: {len(unresolvable)}")
    print()

    if changes:
        print("Changes:")
        for c in changes:
            print(f'  VI {c["vi_id"]}: {c["name"]}')
            print(f'    Master #{c["master_id"]}: "{c["current"]}" -> "{c["new"]}"')
        print()

    if unresolvable:
        print("Unresolvable (no matching Inventory UOM):")
        for line in unresolvable:
            print(line)
        print()

    if args.dry_run:
        print("DRY RUN — no changes applied. Run without --dry-run to apply.")
        return

    if not changes:
        print("Nothing to update.")
        return

    print(f"Applying {len(changes)} updates...")
    applied = 0
    for c in changes:
        item = db.query(HubVendorItem).filter(HubVendorItem.id == c['vi_id']).first()
        if item:
            sync_master_item_defaults(item, db)
            applied += 1

    print(f"Done. Applied {applied} updates.")
    db.close()


if __name__ == '__main__':
    main()
