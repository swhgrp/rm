#!/usr/bin/env python3
"""
Migration script to update Inventory locations to match Accounting

This adds the new columns (code, legal_name, ein) and updates the data
to match the Accounting system's Area table.

Inventory becomes the source of truth for locations.

Usage:
    python3 scripts/migrate_inventory_locations.py --dry-run  # Preview changes
    python3 scripts/migrate_inventory_locations.py            # Apply changes
"""

import argparse
import os
import sys
from sqlalchemy import create_engine, text

# Location data from Accounting system
LOCATION_DATA = {
    # id: (code, name, legal_name, city, state, ein)
    1: ("400", "Seaside Grill", "SW Hospitality Group (Vero), LLC", "Vero Beach", "FL", None),
    2: ("300", "The Nest Eatery", "Osprey Point Restaurant Management, LLC.", None, None, None),
    3: ("500", "SW Grill", "SW Hospitality Group (Boca), LLC.", None, None, None),
    4: ("200", "Okee Grill", "GC Ventures FL, LLC.", None, None, None),
    5: ("700", "Park Bistro", "SW Hospitality Group (Parks), LLC.", "Lake Worth", "FL", None),
    6: ("600", "Links Grill", "SW Hospitality Group (Boynton), LLC", "Boynton Beach", "FL", None),
}

# SW Hospitality Group is a separate entity (code 100) - not a location
# It's the parent company and shouldn't be in the locations table


def get_inventory_db_url():
    """Get Inventory database URL from environment or default"""
    return os.getenv(
        "INVENTORY_DATABASE_URL",
        "postgresql://inventory_user:inventory_pass@localhost:5433/inventory_db"
    )


def add_columns_if_needed(engine, dry_run=False):
    """Add new columns to locations table if they don't exist"""
    with engine.connect() as conn:
        # Check if columns exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'locations'
        """)).fetchall()
        existing_columns = {row[0] for row in result}

        columns_to_add = []
        if 'code' not in existing_columns:
            columns_to_add.append(("code", "VARCHAR(20)"))
        if 'legal_name' not in existing_columns:
            columns_to_add.append(("legal_name", "VARCHAR(200)"))
        if 'ein' not in existing_columns:
            columns_to_add.append(("ein", "VARCHAR(20)"))

        if not columns_to_add:
            print("All columns already exist")
            return

        for col_name, col_type in columns_to_add:
            sql = f"ALTER TABLE locations ADD COLUMN {col_name} {col_type}"
            print(f"Adding column: {col_name} ({col_type})")
            if not dry_run:
                conn.execute(text(sql))

        if not dry_run:
            conn.commit()
            print("Columns added successfully")


def update_location_data(engine, dry_run=False):
    """Update location data to match Accounting"""
    with engine.connect() as conn:
        # First, check current state
        result = conn.execute(text("""
            SELECT id, code, name, legal_name, city, state
            FROM locations
            ORDER BY id
        """)).fetchall()

        print("\nCurrent locations:")
        for row in result:
            print(f"  ID {row[0]}: code={row[1]}, name={row[2]}, legal={row[3]}, city={row[4]}, state={row[5]}")

        print("\nUpdating locations...")
        for loc_id, (code, name, legal_name, city, state, ein) in LOCATION_DATA.items():
            sql = text("""
                UPDATE locations
                SET code = :code,
                    name = :name,
                    legal_name = :legal_name,
                    city = COALESCE(:city, city),
                    state = COALESCE(:state, state),
                    ein = :ein
                WHERE id = :id
            """)
            print(f"  Updating ID {loc_id}: code={code}, name={name}, legal={legal_name}")
            if not dry_run:
                conn.execute(sql, {
                    "id": loc_id,
                    "code": code,
                    "name": name,
                    "legal_name": legal_name,
                    "city": city,
                    "state": state,
                    "ein": ein
                })

        if not dry_run:
            conn.commit()
            print("\nData updated successfully")

        # Show final state
        if not dry_run:
            result = conn.execute(text("""
                SELECT id, code, name, legal_name, city, state
                FROM locations
                ORDER BY code
            """)).fetchall()

            print("\nFinal locations:")
            for row in result:
                print(f"  {row[1]}: {row[2]} - {row[3]} ({row[4]}, {row[5]})")


def create_unique_index(engine, dry_run=False):
    """Create unique index on code column"""
    with engine.connect() as conn:
        # Check if index exists
        result = conn.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'locations' AND indexname = 'ix_locations_code'
        """)).fetchall()

        if result:
            print("Index ix_locations_code already exists")
            return

        sql = "CREATE UNIQUE INDEX ix_locations_code ON locations(code) WHERE code IS NOT NULL"
        print(f"Creating unique index on code column")
        if not dry_run:
            conn.execute(text(sql))
            conn.commit()
            print("Index created successfully")


def main():
    parser = argparse.ArgumentParser(description="Migrate Inventory locations")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        print("=" * 50)
        print("DRY RUN - No changes will be made")
        print("=" * 50)

    db_url = get_inventory_db_url()
    print(f"\nConnecting to: {db_url.split('@')[1] if '@' in db_url else db_url}")

    engine = create_engine(db_url)

    try:
        # Step 1: Add new columns
        print("\n--- Step 1: Add new columns ---")
        add_columns_if_needed(engine, dry_run)

        # Step 2: Update location data
        print("\n--- Step 2: Update location data ---")
        update_location_data(engine, dry_run)

        # Step 3: Create unique index
        print("\n--- Step 3: Create unique index ---")
        create_unique_index(engine, dry_run)

        print("\n" + "=" * 50)
        if dry_run:
            print("DRY RUN COMPLETE - Run without --dry-run to apply changes")
        else:
            print("MIGRATION COMPLETE")
        print("=" * 50)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
