#!/usr/bin/env python3
"""
Migration Script: Location-Aware Costing Architecture

This script migrates the existing data model to the new location-aware costing architecture.

Phase 1: Hub Schema Updates
- Add measure_type to UOM (map from dimension)
- Add location_id, status, pack_to_primary_factor to VendorItems
- Migrate conversion_factor to pack_to_primary_factor
- Migrate unit_price to last_purchase_price

Phase 2: Inventory Schema Updates
- Create master_item_count_units table
- Create master_item_location_costs table
- Create master_item_location_cost_history table
- Migrate existing cost data to location costs

Phase 3: Data Migration
- Set default location_id for existing vendor items
- Migrate cost data from master_items to location costs
- Create primary count units for all items

Run with: python3 scripts/migrate_location_aware_costing.py [--dry-run]
"""

import sys
import os
from datetime import datetime
from decimal import Decimal

# Add paths
sys.path.insert(0, '/opt/restaurant-system/integration-hub/src')
sys.path.insert(0, '/opt/restaurant-system/inventory/src')


def migrate_hub_uom(conn, dry_run=False):
    """Phase 1a: Add measure_type to Hub UOM table"""
    from sqlalchemy import text
    print("\n=== Phase 1a: Hub UOM measure_type Migration ===")

    # Check if measure_type column exists
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'units_of_measure' AND column_name = 'measure_type'
    """)).fetchone()

    if result:
        print("  measure_type column already exists")
        # Migrate dimension values to measure_type
        print("  Migrating dimension -> measure_type...")
        count = conn.execute(text("""
            SELECT COUNT(*) FROM units_of_measure
            WHERE dimension IS NOT NULL AND measure_type IS NULL
        """)).scalar()
        print(f"  {count} UOMs to migrate")
    else:
        print("  Adding measure_type column...")
        if not dry_run:
            conn.execute(text("""
                ALTER TABLE units_of_measure
                ADD COLUMN measure_type VARCHAR(20)
            """))
            conn.commit()
        print("  Added measure_type column")
        # In dry run, estimate count from dimension
        count = conn.execute(text("""
            SELECT COUNT(*) FROM units_of_measure WHERE dimension IS NOT NULL
        """)).scalar()
        print(f"  {count} UOMs would need migration")

    if count and count > 0 and not dry_run:
        # Map old dimension to new measure_type
        conn.execute(text("""
            UPDATE units_of_measure
            SET measure_type = CASE
                WHEN dimension = 'count' THEN 'each'
                WHEN dimension = 'volume' THEN 'volume'
                WHEN dimension = 'weight' THEN 'weight'
                ELSE NULL
            END
            WHERE dimension IS NOT NULL AND measure_type IS NULL
        """))
        conn.commit()
        print(f"  Migrated {count} UOMs")


def migrate_hub_vendor_items(conn, dry_run=False, default_location_id=1):
    """Phase 1b: Add new columns to Hub VendorItems"""
    from sqlalchemy import text
    print("\n=== Phase 1b: Hub Vendor Items Schema Updates ===")

    # Check and add location_id column
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'location_id'
    """)).fetchone()

    if not result:
        print("  Adding location_id column...")
        if not dry_run:
            conn.execute(text("ALTER TABLE hub_vendor_items ADD COLUMN location_id INTEGER"))
            conn.execute(text(f"UPDATE hub_vendor_items SET location_id = {default_location_id}"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hub_vendor_items_location_id ON hub_vendor_items(location_id)"))
            conn.commit()
        print(f"  Added location_id column (default={default_location_id})")
    else:
        print("  location_id column already exists")

    # Check and add status column
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'status'
    """)).fetchone()

    if not result:
        print("  Adding status column...")
        if not dry_run:
            conn.execute(text("ALTER TABLE hub_vendor_items ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            conn.execute(text("""
                UPDATE hub_vendor_items
                SET status = CASE WHEN is_active = true THEN 'active' ELSE 'inactive' END
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hub_vendor_items_status ON hub_vendor_items(status)"))
            conn.commit()
        print("  Added status column")
    else:
        print("  status column already exists")

    # Check and add pack_to_primary_factor column
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'pack_to_primary_factor'
    """)).fetchone()

    if not result:
        print("  Adding pack_to_primary_factor column...")
        if not dry_run:
            conn.execute(text("ALTER TABLE hub_vendor_items ADD COLUMN pack_to_primary_factor NUMERIC(20, 10) DEFAULT 1.0"))
            conn.execute(text("UPDATE hub_vendor_items SET pack_to_primary_factor = COALESCE(conversion_factor, 1.0)"))
            conn.commit()
        print("  Added pack_to_primary_factor column (copied from conversion_factor)")
    else:
        print("  pack_to_primary_factor column already exists")

    # Check and add last_purchase_price column
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'last_purchase_price'
    """)).fetchone()

    if not result:
        print("  Adding last_purchase_price column...")
        if not dry_run:
            conn.execute(text("ALTER TABLE hub_vendor_items ADD COLUMN last_purchase_price NUMERIC(10, 2)"))
            conn.execute(text("ALTER TABLE hub_vendor_items ADD COLUMN previous_purchase_price NUMERIC(10, 2)"))
            conn.execute(text("""
                UPDATE hub_vendor_items
                SET last_purchase_price = unit_price,
                    previous_purchase_price = last_price
            """))
            conn.commit()
        print("  Added last_purchase_price column (copied from unit_price)")
    else:
        print("  last_purchase_price column already exists")

    # Count items
    count = conn.execute(text("SELECT COUNT(*) FROM hub_vendor_items")).scalar()
    print(f"  Total vendor items: {count}")


def create_inventory_tables(conn, dry_run=False):
    """Phase 2: Create new Inventory tables"""
    from sqlalchemy import text
    print("\n=== Phase 2: Create Inventory Tables ===")

    # Check if master_item_count_units exists
    result = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'master_item_count_units'
    """)).fetchone()

    if not result:
        print("  Creating master_item_count_units table...")
        if not dry_run:
            conn.execute(text("""
                CREATE TABLE master_item_count_units (
                    id SERIAL PRIMARY KEY,
                    master_item_id INTEGER NOT NULL REFERENCES master_items(id) ON DELETE CASCADE,
                    uom_id INTEGER NOT NULL,
                    uom_name VARCHAR(50),
                    uom_abbreviation VARCHAR(20),
                    is_primary BOOLEAN DEFAULT FALSE,
                    conversion_to_primary NUMERIC(20, 10) DEFAULT 1.0,
                    display_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(master_item_id, uom_id)
                )
            """))
            conn.execute(text("CREATE INDEX ix_master_item_count_units_master_item_id ON master_item_count_units(master_item_id)"))
            conn.execute(text("CREATE INDEX ix_master_item_count_units_is_primary ON master_item_count_units(is_primary)"))
            conn.commit()
        print("  Created master_item_count_units table")
    else:
        print("  master_item_count_units table already exists")

    # Check if master_item_location_costs exists
    result = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'master_item_location_costs'
    """)).fetchone()

    if not result:
        print("  Creating master_item_location_costs table...")
        if not dry_run:
            conn.execute(text("""
                CREATE TABLE master_item_location_costs (
                    id SERIAL PRIMARY KEY,
                    master_item_id INTEGER NOT NULL REFERENCES master_items(id) ON DELETE CASCADE,
                    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
                    current_weighted_avg_cost NUMERIC(12, 4),
                    total_qty_on_hand NUMERIC(12, 4) DEFAULT 0,
                    last_purchase_cost NUMERIC(12, 4),
                    last_purchase_qty NUMERIC(12, 4),
                    last_purchase_date TIMESTAMP WITH TIME ZONE,
                    last_vendor_id INTEGER,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(master_item_id, location_id)
                )
            """))
            conn.execute(text("CREATE INDEX ix_master_item_location_costs_master_item_id ON master_item_location_costs(master_item_id)"))
            conn.execute(text("CREATE INDEX ix_master_item_location_costs_location_id ON master_item_location_costs(location_id)"))
            conn.commit()
        print("  Created master_item_location_costs table")
    else:
        print("  master_item_location_costs table already exists")

    # Check if master_item_location_cost_history exists
    result = conn.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'master_item_location_cost_history'
    """)).fetchone()

    if not result:
        print("  Creating master_item_location_cost_history table...")
        if not dry_run:
            conn.execute(text("""
                CREATE TABLE master_item_location_cost_history (
                    id SERIAL PRIMARY KEY,
                    location_cost_id INTEGER NOT NULL REFERENCES master_item_location_costs(id) ON DELETE CASCADE,
                    master_item_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    old_cost NUMERIC(12, 4),
                    old_qty NUMERIC(12, 4),
                    change_qty NUMERIC(12, 4),
                    change_cost_per_unit NUMERIC(12, 4),
                    new_cost NUMERIC(12, 4),
                    new_qty NUMERIC(12, 4),
                    vendor_id INTEGER,
                    invoice_id INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX ix_master_item_location_cost_history_location_cost_id ON master_item_location_cost_history(location_cost_id)"))
            conn.execute(text("CREATE INDEX ix_master_item_location_cost_history_master_item_id ON master_item_location_cost_history(master_item_id)"))
            conn.execute(text("CREATE INDEX ix_master_item_location_cost_history_location_id ON master_item_location_cost_history(location_id)"))
            conn.commit()
        print("  Created master_item_location_cost_history table")
    else:
        print("  master_item_location_cost_history table already exists")

    # Add new columns to master_items if needed
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'master_items' AND column_name = 'primary_uom_id'
    """)).fetchone()

    if not result:
        print("  Adding new columns to master_items...")
        if not dry_run:
            conn.execute(text("ALTER TABLE master_items ADD COLUMN IF NOT EXISTS category_id INTEGER"))
            conn.execute(text("ALTER TABLE master_items ADD COLUMN IF NOT EXISTS primary_uom_id INTEGER"))
            conn.execute(text("ALTER TABLE master_items ADD COLUMN IF NOT EXISTS primary_uom_name VARCHAR(50)"))
            conn.execute(text("ALTER TABLE master_items ADD COLUMN IF NOT EXISTS primary_uom_abbr VARCHAR(20)"))
            conn.execute(text("ALTER TABLE master_items ADD COLUMN IF NOT EXISTS shelf_life_days INTEGER"))
            conn.commit()
        print("  Added new columns to master_items")
    else:
        print("  master_items already has new columns")


def migrate_item_data(conn, dry_run=False):
    """Phase 3a: Migrate master item data to new structure"""
    from sqlalchemy import text
    print("\n=== Phase 3a: Migrate Master Item Data ===")

    # Get all locations
    locations = conn.execute(text("SELECT id, name FROM locations ORDER BY id")).fetchall()
    print(f"  Found {len(locations)} locations")

    # Get all master items with current costs
    items = conn.execute(text("""
        SELECT id, name, category, unit_of_measure, unit_of_measure_id, current_cost, average_cost
        FROM master_items
        WHERE is_active = true
    """)).fetchall()
    print(f"  Found {len(items)} active master items")

    # Check how many items have costs
    items_with_costs = [i for i in items if i[5] is not None]
    print(f"  {len(items_with_costs)} items have current_cost set")

    if dry_run:
        print("  [DRY RUN] Would migrate costs to all locations")
        return

    # For each item, create location costs for all locations
    migrated = 0
    for item in items:
        item_id, name, category, uom_str, uom_id, current_cost, average_cost = item

        # Create primary count unit if not exists
        existing = conn.execute(text(
            "SELECT id FROM master_item_count_units WHERE master_item_id = :item_id AND is_primary = true"
        ), {"item_id": item_id}).fetchone()

        if not existing and uom_id:
            # Get UOM details
            uom = conn.execute(text(
                "SELECT id, name, abbreviation FROM units_of_measure WHERE id = :uom_id"
            ), {"uom_id": uom_id}).fetchone()

            if uom:
                conn.execute(text("""
                    INSERT INTO master_item_count_units
                    (master_item_id, uom_id, uom_name, uom_abbreviation, is_primary, conversion_to_primary)
                    VALUES (:item_id, :uom_id, :uom_name, :uom_abbr, true, 1.0)
                """), {"item_id": item_id, "uom_id": uom[0], "uom_name": uom[1], "uom_abbr": uom[2]})

        # Create location costs for each location
        for loc_id, loc_name in locations:
            existing_cost = conn.execute(text(
                "SELECT id FROM master_item_location_costs WHERE master_item_id = :item_id AND location_id = :loc_id"
            ), {"item_id": item_id, "loc_id": loc_id}).fetchone()

            if not existing_cost and current_cost:
                conn.execute(text("""
                    INSERT INTO master_item_location_costs
                    (master_item_id, location_id, current_weighted_avg_cost, total_qty_on_hand)
                    VALUES (:item_id, :loc_id, :cost, 0)
                """), {"item_id": item_id, "loc_id": loc_id, "cost": current_cost})
                migrated += 1

    conn.commit()
    print(f"  Created {migrated} location cost records")


def print_summary(hub_conn, inv_conn):
    """Print migration summary"""
    from sqlalchemy import text
    print("\n=== Migration Summary ===")

    # Hub stats
    hub_uom_count = hub_conn.execute(text("SELECT COUNT(*) FROM units_of_measure")).scalar()
    hub_vi_count = hub_conn.execute(text("SELECT COUNT(*) FROM hub_vendor_items")).scalar()

    # Check if location_id column exists before querying
    has_location = hub_conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'location_id'
    """)).fetchone()

    if has_location:
        hub_vi_with_location = hub_conn.execute(text(
            "SELECT COUNT(*) FROM hub_vendor_items WHERE location_id IS NOT NULL"
        )).scalar()
        hub_vi_with_status = hub_conn.execute(text(
            "SELECT COUNT(*) FROM hub_vendor_items WHERE status IS NOT NULL"
        )).scalar()
    else:
        hub_vi_with_location = 0
        hub_vi_with_status = 0

    print(f"\nHub:")
    print(f"  UOMs: {hub_uom_count}")
    print(f"  Vendor Items: {hub_vi_count}")
    print(f"    with location_id: {hub_vi_with_location}")
    print(f"    with status: {hub_vi_with_status}")

    # Inventory stats
    inv_item_count = inv_conn.execute(text("SELECT COUNT(*) FROM master_items WHERE is_active = true")).scalar()

    try:
        inv_cu_count = inv_conn.execute(text("SELECT COUNT(*) FROM master_item_count_units")).scalar()
    except:
        inv_cu_count = 0

    try:
        inv_lc_count = inv_conn.execute(text("SELECT COUNT(*) FROM master_item_location_costs")).scalar()
    except:
        inv_lc_count = 0

    print(f"\nInventory:")
    print(f"  Master Items: {inv_item_count}")
    print(f"  Count Units: {inv_cu_count}")
    print(f"  Location Costs: {inv_lc_count}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Migrate to Location-Aware Costing')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--default-location', type=int, default=1, help='Default location ID for vendor items')
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        print("=== DRY RUN MODE - No changes will be made ===")

    # Import after path setup
    from sqlalchemy import create_engine

    # Database connections - use correct credentials
    hub_engine = create_engine(os.environ.get('HUB_DATABASE_URL', 'postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db'))
    inv_engine = create_engine(os.environ.get('INVENTORY_DATABASE_URL', 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'))

    print(f"\nMigration started at {datetime.now()}")
    print(f"Default location ID: {args.default_location}")

    with hub_engine.connect() as hub_conn:
        with inv_engine.connect() as inv_conn:
            # Phase 1: Hub updates
            migrate_hub_uom(hub_conn, dry_run)
            migrate_hub_vendor_items(hub_conn, dry_run, args.default_location)

            # Phase 2: Inventory table creation
            create_inventory_tables(inv_conn, dry_run)

            # Phase 3: Data migration
            migrate_item_data(inv_conn, dry_run)

            # Summary
            print_summary(hub_conn, inv_conn)

    print(f"\nMigration completed at {datetime.now()}")


if __name__ == '__main__':
    main()
