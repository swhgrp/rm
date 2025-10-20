#!/usr/bin/env python3
"""
Sync locations from inventory database to accounting areas table.
This creates the location/area structure needed for multi-location accounting.
"""
import psycopg2
from datetime import datetime

# Database connection strings
INVENTORY_DB = "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
ACCOUNTING_DB = "postgresql://accounting_user:Acc0unt1ng_Pr0d_2024!@accounting-db:5432/accounting_db"

def sync_locations():
    """Sync locations from inventory to accounting areas"""

    # Connect to inventory database
    inv_conn = psycopg2.connect(INVENTORY_DB)
    inv_cur = inv_conn.cursor()

    # Connect to accounting database
    acc_conn = psycopg2.connect(ACCOUNTING_DB)
    acc_cur = acc_conn.cursor()

    try:
        # Get all active locations from inventory
        inv_cur.execute("""
            SELECT id, name, city, state, is_active
            FROM locations
            WHERE is_active = true
            ORDER BY id
        """)

        locations = inv_cur.fetchall()

        print(f"Found {len(locations)} active locations in inventory system:")
        print("-" * 80)

        for loc in locations:
            loc_id, name, city, state, is_active = loc

            # Create location code (e.g., "LOC001", "LOC002")
            code = f"LOC{loc_id:03d}"

            # Create description
            location_parts = [name]
            if city:
                location_parts.append(city)
            if state:
                location_parts.append(state)
            description = ", ".join(location_parts)

            print(f"  {code}: {name} ({city}, {state})")

            # Check if area already exists
            acc_cur.execute("""
                SELECT id FROM areas WHERE code = %s
            """, (code,))

            existing = acc_cur.fetchone()

            if existing:
                # Update existing area
                acc_cur.execute("""
                    UPDATE areas
                    SET name = %s,
                        description = %s,
                        is_active = %s,
                        updated_at = %s
                    WHERE code = %s
                """, (name, description, is_active, datetime.now(), code))
                print(f"    → Updated existing area (ID: {existing[0]})")
            else:
                # Insert new area
                acc_cur.execute("""
                    INSERT INTO areas (name, code, description, is_active, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (name, code, description, is_active, datetime.now()))

                new_id = acc_cur.fetchone()[0]
                print(f"    → Created new area (ID: {new_id})")

        # Commit changes
        acc_conn.commit()

        print("-" * 80)
        print(f"✓ Successfully synced {len(locations)} locations to accounting areas")

        # Show final areas table
        print("\nAccounting Areas Table:")
        print("-" * 80)
        acc_cur.execute("""
            SELECT id, code, name, description, is_active
            FROM areas
            ORDER BY code
        """)

        areas = acc_cur.fetchall()
        for area in areas:
            area_id, code, name, description, is_active = area
            status = "✓ Active" if is_active else "✗ Inactive"
            print(f"  {code} | {name:20s} | {description:30s} | {status}")

        print("-" * 80)
        print(f"Total areas: {len(areas)}")

    except Exception as e:
        print(f"✗ Error: {e}")
        acc_conn.rollback()
        raise

    finally:
        inv_cur.close()
        inv_conn.close()
        acc_cur.close()
        acc_conn.close()

if __name__ == "__main__":
    print("=" * 80)
    print("LOCATION SYNC: Inventory → Accounting")
    print("=" * 80)
    print()
    sync_locations()
    print()
    print("=" * 80)
    print("SYNC COMPLETE")
    print("=" * 80)
