#!/usr/bin/env python3
"""
Backfill master item category and count unit from linked Hub vendor items.

Sets category, primary_uom, and creates master_item_count_units record
for master items that are currently missing these values.

Also fixes existing records where uom_id doesn't match uom_name
(caused by wrong hardcoded IDs in earlier code).

Usage:
    docker compose exec integration-hub python scripts/backfill_master_item_defaults.py [--dry-run]
    docker compose exec integration-hub python scripts/backfill_master_item_defaults.py --fix-ids [--dry-run]
"""
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text, create_engine
from integration_hub.db.database import SessionLocal
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.size_unit import SizeUnit
from integration_hub.models.container import Container
from integration_hub.api.vendor_items import (
    _find_inventory_uom, _find_specific_container_uom, GENERIC_CONTAINERS
)


def determine_count_unit(item, db, inv_conn):
    """Determine the primary count unit for a vendor item using dynamic Inventory UOM lookup."""
    size_unit = db.query(SizeUnit).filter(SizeUnit.id == item.size_unit_id).first() if item.size_unit_id else None
    container = db.query(Container).filter(Container.id == item.container_id).first() if item.container_id else None

    each_uom = _find_inventory_uom(inv_conn, name='Each') or (14, 'Each', 'ea')

    # Volume items → Fluid Ounce
    if size_unit and size_unit.measure_type == 'volume':
        return _find_inventory_uom(inv_conn, name='Fluid Ounce') or each_uom
    # Container with specific UOM (Can 12oz, Bottle 750ml, etc.)
    elif container and container.name.lower() in ('can', 'bottle', 'keg'):
        specific = _find_specific_container_uom(
            inv_conn, container.name.lower(),
            float(item.size_quantity) if item.size_quantity else None,
            size_unit.symbol if size_unit else None
        )
        return specific or each_uom
    # Generic containers → Each
    elif container and container.name.lower() in GENERIC_CONTAINERS:
        return each_uom
    # Weight item without container
    elif size_unit and size_unit.measure_type == 'weight':
        return _find_inventory_uom(inv_conn, abbreviation=size_unit.symbol) or each_uom
    else:
        return each_uom


def fix_mismatched_ids(inv_engine, dry_run=False):
    """Fix existing records where uom_id doesn't match uom_name."""
    print("\n=== Fixing mismatched UOM IDs ===")
    with inv_engine.connect() as conn:
        # Fix master_item_count_units
        bad_cus = conn.execute(text("""
            SELECT cu.id, cu.master_item_id, cu.uom_id, cu.uom_name, cu.uom_abbreviation
            FROM master_item_count_units cu
            LEFT JOIN units_of_measure u ON u.id = cu.uom_id
            WHERE cu.uom_name != COALESCE(u.name, '')
        """)).fetchall()

        fixed_cu = 0
        for cu in bad_cus:
            # Look up correct ID by name
            correct = conn.execute(
                text("SELECT id, name, abbreviation FROM units_of_measure WHERE LOWER(name) = LOWER(:name)"),
                {"name": cu[3]}
            ).fetchone()
            if correct:
                if dry_run:
                    print(f"  count_unit [{cu[0]}] master={cu[1]}: {cu[3]} id {cu[2]} -> {correct[0]}")
                else:
                    # Check if there's already a record with the correct uom_id for this master item
                    existing = conn.execute(
                        text("""SELECT id FROM master_item_count_units
                                WHERE master_item_id = :mid AND uom_id = :uid AND id != :id"""),
                        {"mid": cu[1], "uid": correct[0], "id": cu[0]}
                    ).fetchone()
                    if existing:
                        # Delete the duplicate bad record
                        conn.execute(text("DELETE FROM master_item_count_units WHERE id = :id"), {"id": cu[0]})
                    else:
                        conn.execute(
                            text("UPDATE master_item_count_units SET uom_id = :uid WHERE id = :id"),
                            {"uid": correct[0], "id": cu[0]}
                        )
                fixed_cu += 1
            else:
                print(f"  WARNING: No UOM found for name '{cu[3]}' (count_unit {cu[0]})")

        # Fix master_items.primary_uom_id
        bad_uoms = conn.execute(text("""
            SELECT mi.id, mi.name, mi.primary_uom_id, mi.primary_uom_name, mi.primary_uom_abbr
            FROM master_items mi
            LEFT JOIN units_of_measure u ON u.id = mi.primary_uom_id
            WHERE mi.primary_uom_id IS NOT NULL AND mi.primary_uom_name IS NOT NULL
            AND mi.primary_uom_name != COALESCE(u.name, '')
        """)).fetchall()

        fixed_uom = 0
        for mi in bad_uoms:
            correct = conn.execute(
                text("SELECT id, name, abbreviation FROM units_of_measure WHERE LOWER(name) = LOWER(:name)"),
                {"name": mi[3]}
            ).fetchone()
            if correct:
                if dry_run:
                    print(f"  master [{mi[0]}] {mi[1]}: primary_uom {mi[3]} id {mi[2]} -> {correct[0]}")
                else:
                    conn.execute(
                        text("UPDATE master_items SET primary_uom_id = :uid, primary_uom_abbr = :abbr WHERE id = :id"),
                        {"uid": correct[0], "abbr": correct[2], "id": mi[0]}
                    )
                fixed_uom += 1
            else:
                print(f"  WARNING: No UOM found for name '{mi[3]}' (master item {mi[0]})")

        if not dry_run:
            conn.commit()

        print(f"\nFixed UOM IDs:")
        print(f"  Count unit records: {fixed_cu}")
        print(f"  Master item primary_uom: {fixed_uom}")
        if dry_run:
            print("(dry run — no changes written)")


def backfill(dry_run=False):
    db = SessionLocal()
    try:
        # Get all vendor items linked to master items
        items = db.query(HubVendorItem).filter(
            HubVendorItem.inventory_master_item_id.isnot(None)
        ).order_by(HubVendorItem.id).all()

        print(f"Found {len(items)} vendor items linked to master items")

        # Group by master item (first vendor item wins for each master item)
        master_items_seen = {}
        for item in items:
            mid = item.inventory_master_item_id
            if mid not in master_items_seen:
                master_items_seen[mid] = item

        print(f"Unique master items: {len(master_items_seen)}")

        # Connect to Inventory DB
        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)

        updated_category = 0
        updated_uom = 0
        created_count_unit = 0
        skipped = 0

        with inv_engine.connect() as conn:
            for mid, item in master_items_seen.items():
                master = conn.execute(
                    text("SELECT id, category, primary_uom_id FROM master_items WHERE id = :id"),
                    {"id": mid}
                ).fetchone()

                if not master:
                    continue

                existing_category = master[1]
                existing_primary_uom_id = master[2]
                uom_id, uom_name, uom_abbr = determine_count_unit(item, db, conn)
                changes = []

                # Set category if NULL
                if not existing_category and item.category:
                    if not dry_run:
                        conn.execute(
                            text("UPDATE master_items SET category = :category, updated_at = NOW() WHERE id = :id"),
                            {"id": mid, "category": item.category}
                        )
                    changes.append(f"category='{item.category}'")
                    updated_category += 1

                # Set primary UOM if NULL
                if not existing_primary_uom_id:
                    if not dry_run:
                        conn.execute(
                            text("""UPDATE master_items
                                    SET primary_uom_id = :uom_id, primary_uom_name = :uom_name,
                                        primary_uom_abbr = :uom_abbr, updated_at = NOW()
                                    WHERE id = :id"""),
                            {"id": mid, "uom_id": uom_id, "uom_name": uom_name, "uom_abbr": uom_abbr}
                        )
                    changes.append(f"primary_uom='{uom_name}'")
                    updated_uom += 1

                # Create primary count unit if none exists
                existing_cu = conn.execute(
                    text("""SELECT id FROM master_item_count_units
                            WHERE master_item_id = :mid AND is_primary = true AND is_active = true"""),
                    {"mid": mid}
                ).fetchone()

                if not existing_cu:
                    if not dry_run:
                        conn.execute(
                            text("""INSERT INTO master_item_count_units
                                    (master_item_id, uom_id, uom_name, uom_abbreviation, is_primary,
                                     conversion_to_primary, display_order, is_active, created_at)
                                    VALUES (:mid, :uom_id, :uom_name, :uom_abbr, true,
                                            1.0, 0, true, NOW())
                                    ON CONFLICT (master_item_id, uom_id) DO NOTHING"""),
                            {"mid": mid, "uom_id": uom_id, "uom_name": uom_name, "uom_abbr": uom_abbr}
                        )
                    changes.append(f"count_unit='{uom_name}'")
                    created_count_unit += 1

                if changes:
                    item_name = item.vendor_product_name or f"vendor_item_{item.id}"
                    print(f"  [{mid}] {item_name}: {', '.join(changes)}")
                else:
                    skipped += 1

            if not dry_run:
                conn.commit()

        print(f"\nDone:")
        print(f"  Category set: {updated_category}")
        print(f"  Primary UOM set: {updated_uom}")
        print(f"  Count unit created: {created_count_unit}")
        print(f"  Already complete: {skipped}")
        if dry_run:
            print("(dry run — no changes written)")

    finally:
        db.close()


def recheck_count_units(dry_run=False):
    """Re-evaluate all primary count units and fix mismatches."""
    print("\n=== Rechecking all primary count units ===\n")
    db = SessionLocal()
    try:
        items = db.query(HubVendorItem).filter(
            HubVendorItem.inventory_master_item_id.isnot(None),
            HubVendorItem.is_active == True
        ).order_by(HubVendorItem.id).all()

        master_map = {}
        for item in items:
            mid = item.inventory_master_item_id
            if mid not in master_map:
                master_map[mid] = item

        print(f"Checking {len(master_map)} master items with linked vendor items")

        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)

        fixed = 0
        already_correct = 0

        with inv_engine.connect() as conn:
            for mid, item in master_map.items():
                expected_id, expected_name, expected_abbr = determine_count_unit(item, db, conn)

                existing = conn.execute(
                    text("""SELECT id, uom_id, uom_name FROM master_item_count_units
                            WHERE master_item_id = :mid AND is_primary = true AND is_active = true"""),
                    {"mid": mid}
                ).fetchone()

                if not existing:
                    # Verify master item exists in Inventory before creating
                    master_exists = conn.execute(
                        text("SELECT id FROM master_items WHERE id = :mid"),
                        {"mid": mid}
                    ).fetchone()
                    if not master_exists:
                        continue

                    # No count unit exists — create one
                    if not dry_run:
                        conn.execute(
                            text("""INSERT INTO master_item_count_units
                                    (master_item_id, uom_id, uom_name, uom_abbreviation, is_primary,
                                     conversion_to_primary, display_order, is_active, created_at)
                                    VALUES (:mid, :uom_id, :uom_name, :uom_abbr, true,
                                            1.0, 0, true, NOW())
                                    ON CONFLICT (master_item_id, uom_id) DO NOTHING"""),
                            {"mid": mid, "uom_id": expected_id, "uom_name": expected_name, "uom_abbr": expected_abbr}
                        )
                    print(f"  CREATE [{mid}] {item.vendor_product_name}: → {expected_name}")
                    fixed += 1
                elif existing[1] != expected_id:
                    # Mismatch — fix it
                    if not dry_run:
                        # Check if target uom_id already exists as a non-primary record
                        dup = conn.execute(
                            text("""SELECT id FROM master_item_count_units
                                    WHERE master_item_id = :mid AND uom_id = :uom_id AND id != :id"""),
                            {"mid": mid, "uom_id": expected_id, "id": existing[0]}
                        ).fetchone()
                        if dup:
                            # Target UOM already exists — promote it to primary and remove old primary
                            conn.execute(
                                text("UPDATE master_item_count_units SET is_primary = true, updated_at = NOW() WHERE id = :id"),
                                {"id": dup[0]}
                            )
                            conn.execute(
                                text("DELETE FROM master_item_count_units WHERE id = :id"),
                                {"id": existing[0]}
                            )
                        else:
                            conn.execute(
                                text("""UPDATE master_item_count_units
                                        SET uom_id = :uom_id, uom_name = :uom_name, uom_abbreviation = :uom_abbr,
                                            updated_at = NOW()
                                        WHERE id = :id"""),
                                {"uom_id": expected_id, "uom_name": expected_name, "uom_abbr": expected_abbr, "id": existing[0]}
                            )
                    print(f"  FIX [{mid}] {item.vendor_product_name}: {existing[2]} → {expected_name}")
                    fixed += 1
                else:
                    already_correct += 1

            if not dry_run:
                conn.commit()

        print(f"\nDone: {fixed} fixed, {already_correct} already correct")
        if dry_run:
            print("(dry run — no changes written)")

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    fix_ids = "--fix-ids" in sys.argv
    recheck = "--recheck" in sys.argv

    inventory_db_url = os.getenv(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )

    if fix_ids:
        inv_engine = create_engine(inventory_db_url)
        fix_mismatched_ids(inv_engine, dry_run=dry_run)
    elif recheck:
        recheck_count_units(dry_run=dry_run)
    else:
        backfill(dry_run=dry_run)
