#!/usr/bin/env python3
"""
Fix pack_to_primary_factor for container items where primary count unit is a container.

When the primary count unit is a container (Can 16oz, Bottle 750ml, etc.), the
pack_to_primary_factor should be units_per_case (not units_per_case × size_quantity).
The auto-calc incorrectly multiplies by size_quantity for weight/count items,
but for containers, each container IS one primary unit.

Usage:
    docker compose exec integration-hub python scripts/fix_container_pack_factors.py --dry-run
    docker compose exec integration-hub python scripts/fix_container_pack_factors.py
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text, create_engine
from integration_hub.db.database import SessionLocal

# Container-type UOM prefixes in Inventory
CONTAINER_PREFIXES = ('Can', 'Bottle', 'Keg', 'Tub', 'Jar')


def get_inventory_engine():
    inventory_db_url = os.environ.get(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )
    return create_engine(inventory_db_url)


def main():
    parser = argparse.ArgumentParser(description='Fix container item pack_to_primary_factor')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()

    db = SessionLocal()
    inv_engine = get_inventory_engine()

    print("=" * 80)
    print("Fix Container Item pack_to_primary_factor")
    print("=" * 80)
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    # Get all vendor items with containers linked to master items
    rows = db.execute(text("""
        SELECT vi.id, vi.vendor_product_name, vi.units_per_case, vi.size_quantity,
               vi.pack_to_primary_factor, vi.inventory_master_item_id,
               c.name as container_name, su.symbol as size_symbol, su.measure_type
        FROM hub_vendor_items vi
        JOIN hub_containers c ON vi.container_id = c.id
        JOIN hub_size_units su ON vi.size_unit_id = su.id
        WHERE vi.inventory_master_item_id IS NOT NULL
          AND vi.units_per_case IS NOT NULL
        ORDER BY vi.inventory_master_item_id, vi.id
    """)).fetchall()

    print(f"Found {len(rows)} vendor items with containers linked to master items\n")

    # Look up primary count units from Inventory
    with inv_engine.connect() as conn:
        master_ids = list(set(r[5] for r in rows))
        primary_units = {}
        for mid in master_ids:
            cu = conn.execute(text("""
                SELECT uom_name FROM master_item_count_units
                WHERE master_item_id = :mid AND is_primary = true AND is_active = true
            """), {"mid": mid}).fetchone()
            if cu:
                primary_units[mid] = cu[0]

    fixed = 0
    skipped_correct = 0
    skipped_not_container = 0

    for row in rows:
        vi_id, name, upc, sq, ptpf, mid, container, size_sym, measure_type = row
        upc = float(upc or 1)
        sq = float(sq or 1)
        ptpf = float(ptpf or 0)

        primary_uom = primary_units.get(mid, '')

        # Check if primary unit is a container type
        is_container_primary = any(primary_uom.startswith(prefix) for prefix in CONTAINER_PREFIXES)

        if not is_container_primary:
            skipped_not_container += 1
            continue

        correct_factor = upc
        if ptpf == correct_factor:
            skipped_correct += 1
            continue

        print(f"  VI #{vi_id}: {name}")
        print(f"    Container: {container} {sq}{size_sym} | Primary unit: {primary_uom}")
        print(f"    pack_to_primary_factor: {ptpf} → {correct_factor} (units_per_case={upc})")

        if not args.dry_run:
            db.execute(text("""
                UPDATE hub_vendor_items
                SET pack_to_primary_factor = :factor, conversion_factor = :factor
                WHERE id = :id
            """), {"factor": correct_factor, "id": vi_id})

        fixed += 1

    if not args.dry_run and fixed > 0:
        db.commit()

    print()
    print("=" * 80)
    print(f"Results:")
    print(f"  Fixed:                    {fixed}")
    print(f"  Already correct:          {skipped_correct}")
    print(f"  Non-container primary:    {skipped_not_container} (correctly using base unit)")
    print("=" * 80)

    if args.dry_run and fixed > 0:
        print(f"\nRun without --dry-run to apply {fixed} changes.")

    db.close()


if __name__ == '__main__':
    main()
