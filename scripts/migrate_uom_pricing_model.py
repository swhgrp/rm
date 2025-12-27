#!/usr/bin/env python3
"""
Migration script for new UOM + Pricing model.

This script:
1. Adds new columns to units_of_measure (dimension, to_base_factor, is_base_unit)
2. Adds new columns to master_items (stock_uom_id, stock_content_qty, stock_content_uom_id)
3. Adds new columns to hub_vendor_items (purchase_uom_id, stock_units_per_purchase_unit, last_purchase_price)
4. Populates dimension and to_base_factor from existing reference-based conversions
5. Migrates existing data to new fields

Run with:
    python scripts/migrate_uom_pricing_model.py

Options:
    --dry-run    Show what would be done without making changes
    --inventory  Only run Inventory DB migrations
    --hub        Only run Hub DB migrations
"""

import argparse
import sys
from decimal import Decimal

# Database connection details
INVENTORY_DB_CONFIG = {
    'host': 'inventory-db',
    'port': 5432,
    'database': 'inventory_db',
    'user': 'inventory_user',
    'password': 'inventory_pass'
}

HUB_DB_CONFIG = {
    'host': 'hub-db',
    'port': 5432,
    'database': 'integration_hub_db',
    'user': 'hub_user',
    'password': 'hub_password'
}

# Dimension mappings based on category names
CATEGORY_TO_DIMENSION = {
    'Weight': 'weight',
    'Volume - Liquid': 'volume',
    'Volume': 'volume',
    'Count': 'count',
    'Length': 'length'
}

# Base units for each dimension (these get to_base_factor = 1.0)
BASE_UNITS = {
    'weight': ['oz', 'ounce'],  # Base: ounce
    'volume': ['fl oz', 'fluid ounce', 'fl_oz'],  # Base: fluid ounce
    'count': ['ea', 'each'],  # Base: each
    'length': ['in', 'inch']  # Base: inch
}

# Conversion factors to base unit (for common units)
CONVERSION_FACTORS = {
    # Weight (base: ounce)
    'weight': {
        'oz': 1.0,
        'ounce': 1.0,
        'lb': 16.0,
        'pound': 16.0,
        'kg': 35.274,
        'kilogram': 35.274,
        'g': 0.03527396,
        'gram': 0.03527396,
    },
    # Volume (base: fluid ounce)
    'volume': {
        'fl oz': 1.0,
        'fl_oz': 1.0,
        'fluid ounce': 1.0,
        'gal': 128.0,
        'gallon': 128.0,
        'qt': 32.0,
        'quart': 32.0,
        'pt': 16.0,
        'pint': 16.0,
        'c': 8.0,
        'cup': 8.0,
        'tbsp': 0.5,
        'tablespoon': 0.5,
        'tsp': 0.166667,
        'teaspoon': 0.166667,
        'l': 33.814,
        'liter': 33.814,
        'ml': 0.033814,
        'milliliter': 0.033814,
    },
    # Count (base: each)
    'count': {
        'ea': 1.0,
        'each': 1.0,
        'dz': 12.0,
        'dozen': 12.0,
        'cs': None,  # Case is variable, depends on contents
        'case': None,
    },
    # Length (base: inch)
    'length': {
        'in': 1.0,
        'inch': 1.0,
        'ft': 12.0,
        'foot': 12.0,
        'cm': 0.393701,
        'centimeter': 0.393701,
    }
}


def get_db_connection(config):
    """Get database connection using psycopg2."""
    import psycopg2
    return psycopg2.connect(**config)


def migrate_inventory_uom(conn, dry_run=False):
    """
    Add new columns to units_of_measure and populate dimension/to_base_factor.
    """
    print("\n=== Migrating Inventory UOM table ===")
    cur = conn.cursor()

    # Check if columns already exist
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'units_of_measure' AND column_name = 'dimension';
    """)
    if cur.fetchone():
        print("  dimension column already exists")
    else:
        print("  Adding dimension column...")
        if not dry_run:
            cur.execute("""
                ALTER TABLE units_of_measure
                ADD COLUMN dimension VARCHAR(20);
            """)

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'units_of_measure' AND column_name = 'to_base_factor';
    """)
    if cur.fetchone():
        print("  to_base_factor column already exists")
    else:
        print("  Adding to_base_factor column...")
        if not dry_run:
            cur.execute("""
                ALTER TABLE units_of_measure
                ADD COLUMN to_base_factor NUMERIC(20, 10);
            """)

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'units_of_measure' AND column_name = 'is_base_unit';
    """)
    if cur.fetchone():
        print("  is_base_unit column already exists")
    else:
        print("  Adding is_base_unit column...")
        if not dry_run:
            cur.execute("""
                ALTER TABLE units_of_measure
                ADD COLUMN is_base_unit BOOLEAN DEFAULT FALSE;
            """)

    # Get all UOMs with their categories
    cur.execute("""
        SELECT uom.id, uom.name, uom.abbreviation, uc.name as category_name
        FROM units_of_measure uom
        JOIN unit_categories uc ON uom.category_id = uc.id
        ORDER BY uom.id;
    """)
    uoms = cur.fetchall()

    print(f"\n  Processing {len(uoms)} units of measure...")

    for uom_id, name, abbr, category_name in uoms:
        dimension = CATEGORY_TO_DIMENSION.get(category_name)
        if not dimension:
            print(f"    [{uom_id}] {name} ({abbr}) - Unknown category: {category_name}")
            continue

        # Check if this is a base unit
        is_base = abbr.lower() in BASE_UNITS.get(dimension, [])

        # Try to find conversion factor
        to_base = None
        dim_conversions = CONVERSION_FACTORS.get(dimension, {})

        # Try abbreviation first, then name
        to_base = dim_conversions.get(abbr.lower()) or dim_conversions.get(name.lower())

        if to_base is None and is_base:
            to_base = 1.0

        if to_base is not None:
            print(f"    [{uom_id}] {name} ({abbr}): dimension={dimension}, to_base_factor={to_base}, is_base={is_base}")
            if not dry_run:
                cur.execute("""
                    UPDATE units_of_measure
                    SET dimension = %s, to_base_factor = %s, is_base_unit = %s
                    WHERE id = %s;
                """, (dimension, to_base, is_base, uom_id))
        else:
            # Try to calculate from reference chain
            cur.execute("""
                WITH RECURSIVE chain AS (
                    SELECT id, reference_unit_id, contains_quantity::numeric, 1 as depth
                    FROM units_of_measure WHERE id = %s
                    UNION ALL
                    SELECT u.id, u.reference_unit_id, (c.contains_quantity * u.contains_quantity)::numeric, c.depth + 1
                    FROM units_of_measure u
                    JOIN chain c ON u.id = c.reference_unit_id
                    WHERE c.depth < 10
                )
                SELECT contains_quantity FROM chain WHERE reference_unit_id IS NULL OR depth = 10;
            """, (uom_id,))
            result = cur.fetchone()

            if result and result[0]:
                chain_factor = float(result[0])
                print(f"    [{uom_id}] {name} ({abbr}): dimension={dimension}, to_base_factor={chain_factor} (from chain), is_base={is_base}")
                if not dry_run:
                    cur.execute("""
                        UPDATE units_of_measure
                        SET dimension = %s, to_base_factor = %s, is_base_unit = %s
                        WHERE id = %s;
                    """, (dimension, chain_factor, is_base, uom_id))
            else:
                print(f"    [{uom_id}] {name} ({abbr}): dimension={dimension}, to_base_factor=NULL (no conversion found)")
                if not dry_run:
                    cur.execute("""
                        UPDATE units_of_measure
                        SET dimension = %s, is_base_unit = %s
                        WHERE id = %s;
                    """, (dimension, is_base, uom_id))

    if not dry_run:
        conn.commit()
    print("  Done.")


def migrate_inventory_items(conn, dry_run=False):
    """
    Add new columns to master_items and migrate existing data.
    """
    print("\n=== Migrating Inventory master_items table ===")
    cur = conn.cursor()

    # Check/add new columns
    new_columns = [
        ('stock_uom_id', 'INTEGER REFERENCES units_of_measure(id)'),
        ('stock_content_qty', 'NUMERIC(10, 4)'),
        ('stock_content_uom_id', 'INTEGER REFERENCES units_of_measure(id)'),
    ]

    for col_name, col_type in new_columns:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'master_items' AND column_name = %s;
        """, (col_name,))
        if cur.fetchone():
            print(f"  {col_name} column already exists")
        else:
            print(f"  Adding {col_name} column...")
            if not dry_run:
                cur.execute(f"""
                    ALTER TABLE master_items
                    ADD COLUMN {col_name} {col_type};
                """)

    # Migrate existing data: copy unit_of_measure_id to stock_uom_id
    print("\n  Migrating existing data...")

    # Check if columns exist before querying
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'master_items' AND column_name = 'stock_uom_id';
    """)
    stock_uom_exists = cur.fetchone() is not None

    if stock_uom_exists or not dry_run:
        cur.execute("""
            SELECT COUNT(*) FROM master_items
            WHERE unit_of_measure_id IS NOT NULL AND stock_uom_id IS NULL;
        """)
        to_migrate = cur.fetchone()[0]
    else:
        cur.execute("""
            SELECT COUNT(*) FROM master_items
            WHERE unit_of_measure_id IS NOT NULL;
        """)
        to_migrate = cur.fetchone()[0]
    print(f"    {to_migrate} items to migrate unit_of_measure_id -> stock_uom_id")

    if not dry_run and to_migrate > 0:
        cur.execute("""
            UPDATE master_items
            SET stock_uom_id = unit_of_measure_id
            WHERE unit_of_measure_id IS NOT NULL AND stock_uom_id IS NULL;
        """)

    # Migrate unit_size/unit_size_uom to stock_content_qty/stock_content_uom_id
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'master_items' AND column_name = 'stock_content_qty';
    """)
    stock_content_exists = cur.fetchone() is not None

    if stock_content_exists or not dry_run:
        cur.execute("""
            SELECT COUNT(*) FROM master_items
            WHERE unit_size IS NOT NULL AND stock_content_qty IS NULL;
        """)
        to_migrate = cur.fetchone()[0]
    else:
        cur.execute("""
            SELECT COUNT(*) FROM master_items
            WHERE unit_size IS NOT NULL;
        """)
        to_migrate = cur.fetchone()[0]
    print(f"    {to_migrate} items to migrate unit_size -> stock_content_qty")

    if not dry_run and to_migrate > 0:
        cur.execute("""
            UPDATE master_items
            SET stock_content_qty = unit_size
            WHERE unit_size IS NOT NULL AND stock_content_qty IS NULL;
        """)

        # Try to map unit_size_uom string to stock_content_uom_id
        cur.execute("""
            UPDATE master_items mi
            SET stock_content_uom_id = uom.id
            FROM units_of_measure uom
            WHERE mi.unit_size_uom IS NOT NULL
              AND mi.stock_content_uom_id IS NULL
              AND (LOWER(uom.abbreviation) = LOWER(mi.unit_size_uom)
                   OR LOWER(uom.name) = LOWER(mi.unit_size_uom));
        """)

    if not dry_run:
        conn.commit()
    print("  Done.")


def migrate_hub_vendor_items(conn, dry_run=False):
    """
    Add new columns to hub_vendor_items and migrate existing data.
    """
    print("\n=== Migrating Hub hub_vendor_items table ===")
    cur = conn.cursor()

    # Check/add new columns
    new_columns = [
        ('purchase_uom_id', 'INTEGER'),
        ('stock_units_per_purchase_unit', 'NUMERIC(20, 10)'),
        ('last_purchase_price', 'NUMERIC(10, 2)'),
    ]

    for col_name, col_type in new_columns:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hub_vendor_items' AND column_name = %s;
        """, (col_name,))
        if cur.fetchone():
            print(f"  {col_name} column already exists")
        else:
            print(f"  Adding {col_name} column...")
            if not dry_run:
                cur.execute(f"""
                    ALTER TABLE hub_vendor_items
                    ADD COLUMN {col_name} {col_type};
                """)

    # Migrate existing data
    print("\n  Migrating existing data...")

    # Check if new columns exist
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'purchase_uom_id';
    """)
    purchase_uom_exists = cur.fetchone() is not None

    # purchase_unit_id -> purchase_uom_id
    if purchase_uom_exists or not dry_run:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE purchase_unit_id IS NOT NULL AND purchase_uom_id IS NULL;
        """)
        to_migrate = cur.fetchone()[0]
    else:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE purchase_unit_id IS NOT NULL;
        """)
        to_migrate = cur.fetchone()[0]
    print(f"    {to_migrate} items to migrate purchase_unit_id -> purchase_uom_id")

    if not dry_run and to_migrate > 0:
        cur.execute("""
            UPDATE hub_vendor_items
            SET purchase_uom_id = purchase_unit_id
            WHERE purchase_unit_id IS NOT NULL AND purchase_uom_id IS NULL;
        """)

    # units_per_case -> stock_units_per_purchase_unit
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'stock_units_per_purchase_unit';
    """)
    stock_units_exists = cur.fetchone() is not None

    if stock_units_exists or not dry_run:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE units_per_case IS NOT NULL AND stock_units_per_purchase_unit IS NULL;
        """)
        to_migrate = cur.fetchone()[0]
    else:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE units_per_case IS NOT NULL;
        """)
        to_migrate = cur.fetchone()[0]
    print(f"    {to_migrate} items to migrate units_per_case -> stock_units_per_purchase_unit")

    if not dry_run and to_migrate > 0:
        cur.execute("""
            UPDATE hub_vendor_items
            SET stock_units_per_purchase_unit = units_per_case
            WHERE units_per_case IS NOT NULL AND stock_units_per_purchase_unit IS NULL;
        """)

    # case_cost -> last_purchase_price
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hub_vendor_items' AND column_name = 'last_purchase_price';
    """)
    last_price_exists = cur.fetchone() is not None

    if last_price_exists or not dry_run:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE case_cost IS NOT NULL AND last_purchase_price IS NULL;
        """)
        to_migrate = cur.fetchone()[0]
    else:
        cur.execute("""
            SELECT COUNT(*) FROM hub_vendor_items
            WHERE case_cost IS NOT NULL;
        """)
        to_migrate = cur.fetchone()[0]
    print(f"    {to_migrate} items to migrate case_cost -> last_purchase_price")

    if not dry_run and to_migrate > 0:
        cur.execute("""
            UPDATE hub_vendor_items
            SET last_purchase_price = case_cost
            WHERE case_cost IS NOT NULL AND last_purchase_price IS NULL;
        """)

    if not dry_run:
        conn.commit()
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description='Migrate to new UOM + Pricing model')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--inventory', action='store_true', help='Only run Inventory DB migrations')
    parser.add_argument('--hub', action='store_true', help='Only run Hub DB migrations')
    args = parser.parse_args()

    # If neither specified, run both
    run_inventory = args.inventory or (not args.inventory and not args.hub)
    run_hub = args.hub or (not args.inventory and not args.hub)

    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===")

    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    # Run Inventory migrations
    if run_inventory:
        print("\n" + "=" * 60)
        print("INVENTORY DATABASE MIGRATION")
        print("=" * 60)
        try:
            conn = get_db_connection(INVENTORY_DB_CONFIG)
            migrate_inventory_uom(conn, args.dry_run)
            migrate_inventory_items(conn, args.dry_run)
            conn.close()
        except Exception as e:
            print(f"Error migrating Inventory DB: {e}")
            sys.exit(1)

    # Run Hub migrations
    if run_hub:
        print("\n" + "=" * 60)
        print("HUB DATABASE MIGRATION")
        print("=" * 60)
        try:
            conn = get_db_connection(HUB_DB_CONFIG)
            migrate_hub_vendor_items(conn, args.dry_run)
            conn.close()
        except Exception as e:
            print(f"Error migrating Hub DB: {e}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)

    if args.dry_run:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
