#!/usr/bin/env python3
"""
UOM Migration Script: Inventory to Hub

This script migrates UOM references from Inventory's local units_of_measure table
to Hub's units_of_measure table (source of truth).

Migration strategy:
1. Pure units (Pound, Gallon, Each) map directly by name/abbreviation
2. Compound units (Bottle 1Lt, Can 16oz) map to generic container (Bottle, Can)
   with size stored in master_item_count_units.uom_size field

Tables affected in Inventory:
- master_items.unit_of_measure_id -> hub_uom_id (new column)
- master_item_count_units.uom_id -> hub_uom_id (new column)

Usage:
    python migrate_uom_to_hub.py --dry-run  # Preview changes
    python migrate_uom_to_hub.py --execute  # Apply changes
"""

import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from typing import Dict, List, Tuple, Optional

# Configuration
HUB_API_URL = os.getenv("HUB_API_URL", "http://integration-hub:8000")
INVENTORY_DB = {
    "host": os.getenv("INVENTORY_DB_HOST", "inventory-db"),
    "port": os.getenv("INVENTORY_DB_PORT", "5432"),
    "dbname": os.getenv("INVENTORY_DB_NAME", "inventory_db"),
    "user": os.getenv("INVENTORY_DB_USER", "inventory_user"),
    "password": os.getenv("INVENTORY_DB_PASSWORD", "inventory_pass")
}

# Manual mapping for compound units to Hub generic units
# Format: inventory_abbreviation -> (hub_abbreviation, size_description)
COMPOUND_UOM_MAPPING = {
    # Bottles - map to generic "Bottle" (btl) in Hub
    "btl187ml": ("btl", "187ml"),
    "Btl1lt": ("btl", "1Lt"),
    "Blt20oz": ("btl", "20oz"),
    "btl4oz": ("btl", "4oz"),
    "btl750ml": ("btl", "750ml"),

    # Cans - map to generic "Can" (can) in Hub
    "can11.2oz": ("can", "11.2oz"),
    "Can11.5oz": ("can", "11.5oz"),
    "can12oz": ("can", "12oz"),
    "can16oz": ("can", "16oz"),
    "can24oz": ("can", "24oz"),
    "can355ml": ("can", "355ml"),
    "can8.4oz": ("can", "8.4oz"),

    # Cases with size - map to generic "Case" (cs)
    "cs-6": ("cs", "6-pack"),
    "cs-12": ("cs", "12-pack"),
    "cs-24": ("cs", "24-pack"),
    "case24/16oz Can": ("cs", "24x16oz"),

    # Kegs - map to generic "Keg" (keg)
    "keg1/2": ("keg", "1/2 Barrel"),
    "keg1/4": ("keg", "1/4 Barrel"),
    "keg50l": ("keg", "50L"),
}

# Direct mappings (same unit, different IDs between systems)
# Format: inventory_abbreviation -> hub_abbreviation
DIRECT_UOM_MAPPING = {
    "ea": "ea",
    "dz": "dz",
    "lb": "lb",
    "oz": "oz",
    "g": "g",
    "kg": "kg",
    "gal": "gal",
    "qt": "qt",
    "pt": "pt",
    "c": "c",
    "fl oz": "fl oz",
    "L": "L",
    "mL": "mL",
    "tbsp": "tbsp",
    "tsp": "tsp",
}


def get_hub_uoms() -> Dict[str, dict]:
    """Fetch all UOMs from Hub API"""
    try:
        response = requests.get(f"{HUB_API_URL}/api/uom/", timeout=10)
        response.raise_for_status()
        uoms = response.json()
        # Index by abbreviation (lowercase for case-insensitive matching)
        return {uom["abbreviation"].lower(): uom for uom in uoms}
    except Exception as e:
        print(f"Error fetching Hub UOMs: {e}")
        sys.exit(1)


def get_inventory_uoms(cursor) -> List[dict]:
    """Fetch all UOMs from Inventory database"""
    cursor.execute("""
        SELECT id, name, abbreviation, dimension, to_base_factor, is_base_unit, is_active
        FROM units_of_measure
        ORDER BY id
    """)
    return cursor.fetchall()


def get_master_items_using_uom(cursor, uom_id: int) -> List[dict]:
    """Get master items using a specific UOM"""
    cursor.execute("""
        SELECT id, name, unit_of_measure_id
        FROM master_items
        WHERE unit_of_measure_id = %s
    """, (uom_id,))
    return cursor.fetchall()


def get_count_units_using_uom(cursor, uom_id: int) -> List[dict]:
    """Get count unit records using a specific UOM"""
    cursor.execute("""
        SELECT id, master_item_id, uom_id, uom_name
        FROM master_item_count_units
        WHERE uom_id = %s
    """, (uom_id,))
    return cursor.fetchall()


def create_uom_mapping(inventory_uoms: List[dict], hub_uoms: Dict[str, dict]) -> Dict[int, Tuple[int, Optional[str]]]:
    """
    Create mapping from Inventory UOM IDs to Hub UOM IDs.

    Returns: Dict of {inventory_uom_id: (hub_uom_id, size_description or None)}
    """
    mapping = {}
    unmapped = []

    for inv_uom in inventory_uoms:
        inv_id = inv_uom["id"]
        inv_abbr = inv_uom["abbreviation"]
        inv_name = inv_uom["name"]

        # Check compound mapping first
        if inv_abbr in COMPOUND_UOM_MAPPING:
            hub_abbr, size_desc = COMPOUND_UOM_MAPPING[inv_abbr]
            if hub_abbr.lower() in hub_uoms:
                hub_uom = hub_uoms[hub_abbr.lower()]
                mapping[inv_id] = (hub_uom["id"], size_desc)
                print(f"  Compound: {inv_name} ({inv_abbr}) -> {hub_uom['name']} ({hub_abbr}) + size={size_desc}")
                continue

        # Check direct mapping
        if inv_abbr.lower() in DIRECT_UOM_MAPPING:
            hub_abbr = DIRECT_UOM_MAPPING[inv_abbr.lower()]
            if hub_abbr.lower() in hub_uoms:
                hub_uom = hub_uoms[hub_abbr.lower()]
                mapping[inv_id] = (hub_uom["id"], None)
                print(f"  Direct: {inv_name} ({inv_abbr}) -> {hub_uom['name']} ({hub_abbr})")
                continue

        # Try exact abbreviation match (case-insensitive)
        if inv_abbr.lower() in hub_uoms:
            hub_uom = hub_uoms[inv_abbr.lower()]
            mapping[inv_id] = (hub_uom["id"], None)
            print(f"  Exact: {inv_name} ({inv_abbr}) -> {hub_uom['name']} ({hub_uom['abbreviation']})")
            continue

        # Unmapped
        unmapped.append(inv_uom)

    if unmapped:
        print(f"\nUnmapped UOMs ({len(unmapped)}):")
        for uom in unmapped:
            print(f"  - {uom['name']} ({uom['abbreviation']}) [id={uom['id']}]")

    return mapping


def add_hub_uom_columns(cursor, dry_run: bool):
    """Add hub_uom_id columns to Inventory tables if they don't exist"""

    # Check if columns exist
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'master_items' AND column_name = 'hub_uom_id'
    """)
    mi_has_column = cursor.fetchone() is not None

    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'master_item_count_units' AND column_name = 'hub_uom_id'
    """)
    micu_has_column = cursor.fetchone() is not None

    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'master_item_count_units' AND column_name = 'uom_size'
    """)
    micu_has_size = cursor.fetchone() is not None

    if not mi_has_column:
        sql = "ALTER TABLE master_items ADD COLUMN hub_uom_id INTEGER"
        print(f"  SQL: {sql}")
        if not dry_run:
            cursor.execute(sql)

    if not micu_has_column:
        sql = "ALTER TABLE master_item_count_units ADD COLUMN hub_uom_id INTEGER"
        print(f"  SQL: {sql}")
        if not dry_run:
            cursor.execute(sql)

    if not micu_has_size:
        sql = "ALTER TABLE master_item_count_units ADD COLUMN uom_size VARCHAR(50)"
        print(f"  SQL: {sql}")
        if not dry_run:
            cursor.execute(sql)


def migrate_master_items(cursor, mapping: Dict[int, Tuple[int, Optional[str]]], dry_run: bool) -> int:
    """Migrate master_items.unit_of_measure_id to hub_uom_id"""
    updated = 0

    for inv_uom_id, (hub_uom_id, _) in mapping.items():
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM master_items WHERE unit_of_measure_id = %s
        """, (inv_uom_id,))
        count = cursor.fetchone()["cnt"]

        if count > 0:
            sql = f"UPDATE master_items SET hub_uom_id = {hub_uom_id} WHERE unit_of_measure_id = {inv_uom_id}"
            if not dry_run:
                cursor.execute(sql)
            updated += count

    return updated


def migrate_count_units(cursor, mapping: Dict[int, Tuple[int, Optional[str]]], dry_run: bool) -> int:
    """Migrate master_item_count_units.uom_id to hub_uom_id"""
    updated = 0

    for inv_uom_id, (hub_uom_id, size_desc) in mapping.items():
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM master_item_count_units WHERE uom_id = %s
        """, (inv_uom_id,))
        count = cursor.fetchone()["cnt"]

        if count > 0:
            if size_desc:
                sql = f"UPDATE master_item_count_units SET hub_uom_id = {hub_uom_id}, uom_size = '{size_desc}' WHERE uom_id = {inv_uom_id}"
            else:
                sql = f"UPDATE master_item_count_units SET hub_uom_id = {hub_uom_id} WHERE uom_id = {inv_uom_id}"
            if not dry_run:
                cursor.execute(sql)
            updated += count

    return updated


def main():
    parser = argparse.ArgumentParser(description="Migrate UOM from Inventory to Hub")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--execute", action="store_true", help="Apply changes to database")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        sys.exit(1)

    dry_run = args.dry_run
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"\n{'='*60}")
    print(f"UOM Migration: Inventory -> Hub ({mode})")
    print(f"{'='*60}\n")

    # Fetch Hub UOMs
    print("Fetching Hub UOMs...")
    hub_uoms = get_hub_uoms()
    print(f"  Found {len(hub_uoms)} UOMs in Hub\n")

    # Connect to Inventory database
    print("Connecting to Inventory database...")
    try:
        conn = psycopg2.connect(**INVENTORY_DB, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        print("  Connected successfully\n")
    except Exception as e:
        print(f"  Error connecting: {e}")
        sys.exit(1)

    try:
        # Fetch Inventory UOMs
        print("Fetching Inventory UOMs...")
        inventory_uoms = get_inventory_uoms(cursor)
        print(f"  Found {len(inventory_uoms)} UOMs in Inventory\n")

        # Create mapping
        print("Creating UOM mapping...")
        mapping = create_uom_mapping(inventory_uoms, hub_uoms)
        print(f"\n  Mapped {len(mapping)} of {len(inventory_uoms)} UOMs\n")

        # Add columns
        print("Adding hub_uom_id columns...")
        add_hub_uom_columns(cursor, dry_run)
        print()

        # Migrate master_items
        print("Migrating master_items...")
        mi_updated = migrate_master_items(cursor, mapping, dry_run)
        print(f"  Updated {mi_updated} master items\n")

        # Migrate count_units
        print("Migrating master_item_count_units...")
        cu_updated = migrate_count_units(cursor, mapping, dry_run)
        print(f"  Updated {cu_updated} count unit records\n")

        # Commit or rollback
        if dry_run:
            print("DRY RUN - Rolling back changes...")
            conn.rollback()
        else:
            print("Committing changes...")
            conn.commit()

        print(f"\n{'='*60}")
        print(f"Migration {'preview' if dry_run else 'complete'}!")
        print(f"  Master items: {mi_updated}")
        print(f"  Count units: {cu_updated}")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
