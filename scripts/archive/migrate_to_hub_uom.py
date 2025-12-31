#!/usr/bin/env python3
"""
Migration Script: Migrate Master Items to Hub UoM

This script migrates master_items from using Inventory's unit_of_measure_id
to Hub's primary_uom_id.

The Hub owns UoM as the source of truth. Master items should reference Hub UoM IDs.

Mapping Strategy:
1. Direct match by abbreviation (e.g., 'lb' -> Hub Pound)
2. Direct match by name (e.g., 'Pound' -> Hub Pound)
3. Complex units map to base units (e.g., 'Bottle 20oz' -> Hub 'Fluid Ounce')
   - These will need conversions added separately

Run with: python3 scripts/migrate_to_hub_uom.py [--dry-run]
"""

import sys
import os
from decimal import Decimal

# Add paths
sys.path.insert(0, '/opt/restaurant-system/integration-hub/src')
sys.path.insert(0, '/opt/restaurant-system/inventory/src')

# Mapping from Inventory UoM abbreviation to Hub UoM ID
# Hub UoMs: 1=Each, 2=Dozen, 3=Case, 5=Bag, 7=Bottle, 8=Can, 9=Keg,
#           11=Ounce, 12=Pound, 13=Gram, 14=Kilogram,
#           15=Fluid Ounce, 16=Cup, 17=Pint, 18=Quart, 19=Gallon, 20=Liter, 21=Milliliter, 22=Tablespoon, 23=Teaspoon

INVENTORY_TO_HUB_MAP = {
    # Count units
    'ea': (1, 'Each', 'ea'),
    'dz': (2, 'Dozen', 'dz'),
    'cs': (3, 'Case', 'cs'),
    'cs-6': (3, 'Case', 'cs'),      # Map to generic Case
    'cs-12': (3, 'Case', 'cs'),     # Map to generic Case
    'cs-24': (3, 'Case', 'cs'),     # Map to generic Case

    # Weight units
    'lb': (12, 'Pound', 'lb'),
    'oz': (11, 'Ounce', 'oz'),
    'g': (13, 'Gram', 'g'),
    'kg': (14, 'Kilogram', 'kg'),

    # Volume units
    'fl oz': (15, 'Fluid Ounce', 'fl oz'),
    'c': (16, 'Cup', 'c'),
    'pt': (17, 'Pint', 'pt'),
    'qt': (18, 'Quart', 'qt'),
    'gal': (19, 'Gallon', 'gal'),
    'L': (20, 'Liter', 'L'),
    'mL': (21, 'Milliliter', 'mL'),
    'tbsp': (22, 'Tablespoon', 'tbsp'),
    'tsp': (23, 'Teaspoon', 'tsp'),

    # Complex bottle/can units -> map to Fluid Ounce (will need conversions)
    'btl187ml': (21, 'Milliliter', 'mL'),      # 187ml -> mL base
    'Btl1lt': (20, 'Liter', 'L'),              # 1L -> L base
    'Blt20oz': (15, 'Fluid Ounce', 'fl oz'),   # 20oz -> fl oz base
    'btl4oz': (15, 'Fluid Ounce', 'fl oz'),    # 4oz -> fl oz base
    'btl750ml': (21, 'Milliliter', 'mL'),      # 750ml -> mL base
    'can11.2oz': (15, 'Fluid Ounce', 'fl oz'), # 11.2oz -> fl oz base
    'Can11.5oz': (15, 'Fluid Ounce', 'fl oz'), # 11.5oz -> fl oz base
    'can12oz': (15, 'Fluid Ounce', 'fl oz'),   # 12oz -> fl oz base
    'can16oz': (15, 'Fluid Ounce', 'fl oz'),   # 16oz -> fl oz base
    'can24oz': (15, 'Fluid Ounce', 'fl oz'),   # 24oz -> fl oz base
    'can355ml': (21, 'Milliliter', 'mL'),      # 355ml -> mL base
    'can8.4oz': (15, 'Fluid Ounce', 'fl oz'),  # 8.4oz -> fl oz base
    'case24/16oz Can': (15, 'Fluid Ounce', 'fl oz'),  # Complex -> fl oz

    # Keg units -> map to Gallon
    'keg1/2': (19, 'Gallon', 'gal'),   # 1/2 barrel = 15.5 gal
    'keg1/4': (19, 'Gallon', 'gal'),   # 1/4 barrel = 7.75 gal
    'keg50l': (20, 'Liter', 'L'),      # 50L keg -> L base
}


def get_inventory_connection():
    """Get connection to Inventory database"""
    from sqlalchemy import create_engine
    db_url = os.getenv('INVENTORY_DATABASE_URL', 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')
    engine = create_engine(db_url)
    return engine.connect()


def migrate_master_items(dry_run=False):
    """Migrate master_items to use Hub UoM IDs"""
    from sqlalchemy import text

    conn = get_inventory_connection()

    print("=" * 60)
    print("MIGRATE MASTER ITEMS TO HUB UOM")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Get all master items with their current UoM
    items = conn.execute(text("""
        SELECT mi.id, mi.name, mi.unit_of_measure_id,
               u.name as uom_name, u.abbreviation as uom_abbr,
               mi.primary_uom_id, mi.primary_uom_name, mi.primary_uom_abbr
        FROM master_items mi
        LEFT JOIN units_of_measure u ON mi.unit_of_measure_id = u.id
        WHERE mi.is_active = true
        ORDER BY mi.id
    """)).fetchall()

    print(f"Found {len(items)} active master items")
    print()

    # Track statistics
    stats = {
        'already_migrated': 0,
        'migrated': 0,
        'no_uom': 0,
        'unmapped': 0,
    }
    unmapped_items = []

    for item in items:
        item_id = item[0]
        item_name = item[1]
        inv_uom_id = item[2]
        inv_uom_name = item[3]
        inv_uom_abbr = item[4]
        current_hub_id = item[5]
        current_hub_name = item[6]

        # Skip if already migrated
        if current_hub_id:
            stats['already_migrated'] += 1
            continue

        # Skip if no UoM set
        if not inv_uom_id or not inv_uom_abbr:
            stats['no_uom'] += 1
            print(f"  SKIP (no UoM): {item_id} - {item_name}")
            continue

        # Look up Hub UoM
        hub_mapping = INVENTORY_TO_HUB_MAP.get(inv_uom_abbr)

        if not hub_mapping:
            stats['unmapped'] += 1
            unmapped_items.append((item_id, item_name, inv_uom_abbr, inv_uom_name))
            print(f"  UNMAPPED: {item_id} - {item_name} (UoM: {inv_uom_abbr} / {inv_uom_name})")
            continue

        hub_id, hub_name, hub_abbr = hub_mapping

        # Update the master item
        if not dry_run:
            conn.execute(text("""
                UPDATE master_items
                SET primary_uom_id = :hub_id,
                    primary_uom_name = :hub_name,
                    primary_uom_abbr = :hub_abbr
                WHERE id = :item_id
            """), {
                'hub_id': hub_id,
                'hub_name': hub_name,
                'hub_abbr': hub_abbr,
                'item_id': item_id
            })

        stats['migrated'] += 1
        print(f"  MIGRATED: {item_id} - {item_name}: {inv_uom_abbr} -> {hub_abbr} (Hub ID {hub_id})")

    if not dry_run:
        conn.commit()

    conn.close()

    # Print summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Already migrated: {stats['already_migrated']}")
    print(f"Migrated this run: {stats['migrated']}")
    print(f"No UoM set: {stats['no_uom']}")
    print(f"Unmapped (need manual fix): {stats['unmapped']}")

    if unmapped_items:
        print()
        print("UNMAPPED ITEMS (need manual mapping):")
        for item_id, item_name, abbr, name in unmapped_items:
            print(f"  {item_id}: {item_name} - UoM: {abbr} ({name})")

    return stats


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate_master_items(dry_run=dry_run)
