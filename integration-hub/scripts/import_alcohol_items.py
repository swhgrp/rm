#!/usr/bin/env python3
"""
Import Alcohol Vendor Items from CSV

This script imports vendor items from the product catalog CSV into the inventory system.
"""

import csv
import psycopg2
from collections import defaultdict

INVENTORY_DB = {
    'host': 'inventory-db',
    'database': 'inventory_db',
    'user': 'inventory_user',
    'password': 'inventory_pass'
}

# Map distributor names from CSV to vendor IDs in database
VENDOR_MAPPING = {
    'Gold Coast Beverage, LLC': 9,  # Gold Coast Beverage
    'Southern Eagle Distributing, Inc.': 8,  # Southern Eagle Distributing
    "Southern Glazer's Wine & Spirits of FL": 6,  # Southern Glaziers
    'Premier Beverage Co.dba Breakthru Beverage Florida': 7,  # Breakthru Beverage
    'Republic National Dist - Deerfield Bch.': 10,  # Republic National Distributing
    'Western Beverage DBA Double Eagle Distributing': 5,  # Double Eagle Distributing
}

# Default unit of measure ID (Each)
DEFAULT_UNIT_ID = 14  # Each

def parse_csv(filepath):
    """Parse the CSV file and return items grouped by vendor."""
    items_by_vendor = defaultdict(list)

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            distributor = row['Distributor Name'].strip()
            item_number = row['Distributor Item Number'].strip()
            description = row['Product Description'].strip()

            # Skip empty or invalid items
            if not item_number or item_number == '00000' or item_number == '99999999':
                continue
            if not description or 'refund' in description.lower() or 'freight' in description.lower():
                continue
            if 'delivery charge' in description.lower() or 'thank you' in description.lower():
                continue
            if 'empty' in description.lower() and 'keg' in description.lower():
                continue

            items_by_vendor[distributor].append({
                'sku': item_number,
                'description': description
            })

    return items_by_vendor

def get_existing_items(cursor, vendor_id):
    """Get existing vendor items for a vendor."""
    cursor.execute("""
        SELECT vendor_sku FROM vendor_items WHERE vendor_id = %s
    """, (vendor_id,))
    return set(row[0] for row in cursor.fetchall())

def import_items(cursor, vendor_id, items, existing_skus, dry_run=False):
    """Import items for a vendor."""
    added = 0
    skipped = 0

    for item in items:
        sku = item['sku']

        # Skip if already exists
        if sku in existing_skus:
            skipped += 1
            continue

        if not dry_run:
            cursor.execute("""
                INSERT INTO vendor_items (
                    vendor_id, vendor_sku, vendor_product_name,
                    purchase_unit_id, conversion_factor, is_active, is_preferred
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                vendor_id,
                sku,
                item['description'],
                DEFAULT_UNIT_ID,  # Each
                1.0,  # conversion factor
                True,  # is_active
                False  # is_preferred
            ))

        added += 1
        existing_skus.add(sku)  # Prevent duplicates within same import

    return added, skipped

def main():
    import sys
    dry_run = '--dry-run' in sys.argv

    print("="*80)
    print("IMPORT ALCOHOL VENDOR ITEMS")
    print("="*80)

    if dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")

    # Parse CSV
    print("Parsing CSV file...")
    items_by_vendor = parse_csv('/tmp/product_catalog.csv')

    print(f"\nFound items for {len(items_by_vendor)} distributors:")
    for vendor, items in items_by_vendor.items():
        print(f"  {vendor}: {len(items)} items")

    # Connect to database
    print("\nConnecting to inventory database...")
    conn = psycopg2.connect(**INVENTORY_DB)
    cursor = conn.cursor()

    try:
        total_added = 0
        total_skipped = 0

        for distributor_name, items in items_by_vendor.items():
            vendor_id = VENDOR_MAPPING.get(distributor_name)

            if not vendor_id:
                print(f"\n  WARNING: No vendor mapping for '{distributor_name}' - skipping {len(items)} items")
                continue

            # Get vendor name from DB
            cursor.execute("SELECT name FROM vendors WHERE id = %s", (vendor_id,))
            result = cursor.fetchone()
            vendor_name = result[0] if result else distributor_name

            # Get existing items
            existing_skus = get_existing_items(cursor, vendor_id)

            # Import items
            added, skipped = import_items(cursor, vendor_id, items, existing_skus, dry_run)

            print(f"\n  {vendor_name} (ID: {vendor_id}):")
            print(f"    Added: {added} items")
            print(f"    Skipped (already exist): {skipped} items")

            total_added += added
            total_skipped += skipped

        if not dry_run:
            conn.commit()
            print("\n  Changes committed to database.")

        print("\n" + "="*80)
        print(f"TOTAL: Added {total_added} items, Skipped {total_skipped} duplicates")
        print("="*80)

        if dry_run:
            print("\nRun without --dry-run to apply changes.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
