#!/usr/bin/env python3
"""
Import missing vendor items from Hub's item_code_mapping_deprecated to Inventory.

This script:
1. Finds verified item codes in Hub that don't exist in Inventory
2. Determines vendor from invoice history
3. Fuzzy matches to existing master items or creates new ones
4. Creates vendor items in Inventory
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from difflib import SequenceMatcher
import re

# Database connections
HUB_DB = {
    'host': 'hub-db',
    'database': 'integration_hub_db',
    'user': 'hub_user',
    'password': 'hub_password'
}

INVENTORY_DB = {
    'host': 'inventory-db',
    'database': 'inventory_db',
    'user': 'inventory_user',
    'password': 'inventory_pass'
}

# Vendor name mapping (invoice vendor name -> inventory vendor_id)
VENDOR_MAPPING = {
    'Gordon Food Service': 1,
    'Gordon Food Service Inc.': 1,
    'Gordon Food Service, Inc.': 1,
    'Gordon Food Service Store': 1,
    'Gold Coast Linen': 11,
    'Gold Coast Linen Service': 11,
    'Gold Coast Beverage': 9,
    'Gold Coast Beverage LLC': 9,
    'Southern Glazer\'s of FL': 6,
    'Southern Glaziers': 6,
    'Breakthru Beverage': 7,
    'Double Eagle Distributing': 5,
    'Southern Eagle Distributing': 8,
    'Republic National Distributing': 10,
    'BJs': 2,
    'Sam\'s': 3,
}

# Category guessing based on item description patterns
CATEGORY_PATTERNS = [
    (r'\b(vodka|gin|rum|tequila|whiskey|bourbon|brandy|cognac|liqueur|scotch)\b', 'Liquor'),
    (r'\b(wine|prosecco|champagne|merlot|cabernet|chardonnay|pinot|sauvignon)\b', 'Wine'),
    (r'\b(beer|lager|ale|ipa|stout|pilsner|bud light|corona|modelo|michelob|yuengling)\b', 'Bottled'),
    (r'\b(bacon|ham|pork|sausage)\b', 'Pork'),
    (r'\b(chicken|poultry)\b', 'Chicken'),
    (r'\b(beef|steak|burger|patty)\b', 'Beef'),
    (r'\b(fish|shrimp|lobster|crab|salmon|grouper|tuna)\b', 'Seafood'),
    (r'\b(cheese|dairy|milk|cream|butter)\b', 'Dairy'),
    (r'\b(lettuce|tomato|onion|pepper|vegetable|produce)\b', 'Produce'),
    (r'\b(soda|cola|sprite|powerade|gatorade|drink)\b', 'Beverages - Non Alcoholic'),
    (r'\b(bag|container|wrap|foil|cup|napkin|straw|utensil)\b', 'Supplies - Disposable'),
    (r'\b(towel|apron|mat|linen|uniform)\b', 'Supplies - Linen'),
    (r'\b(sauce|dressing|mayo|ketchup|mustard|relish)\b', 'Condiments'),
    (r'\b(propane|gas|fuel)\b', 'Expense - Utilities'),
]


def guess_category(description):
    """Guess category based on item description"""
    desc_lower = description.lower()
    for pattern, category in CATEGORY_PATTERNS:
        if re.search(pattern, desc_lower, re.IGNORECASE):
            return category
    return 'Uncategorized'


def similarity(a, b):
    """Calculate string similarity ratio"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_best_master_item(inv_cursor, description, category):
    """Find best matching master item or return None"""
    # First try exact category match
    inv_cursor.execute("""
        SELECT id, name, category FROM master_items
        WHERE category = %s AND is_active = true
    """, (category,))
    candidates = inv_cursor.fetchall()

    # If no candidates in category, try all
    if not candidates:
        inv_cursor.execute("""
            SELECT id, name, category FROM master_items
            WHERE is_active = true
        """)
        candidates = inv_cursor.fetchall()

    best_match = None
    best_score = 0.0

    for item in candidates:
        score = similarity(description, item['name'])
        if score > best_score and score > 0.5:  # Minimum 50% similarity
            best_score = score
            best_match = item

    return best_match, best_score


def get_or_create_master_item(inv_cursor, inv_conn, description, category):
    """Get existing or create new master item"""
    # Try to find existing
    best_match, score = find_best_master_item(inv_cursor, description, category)

    if best_match and score > 0.6:
        print(f"  Found master item: {best_match['name']} (score: {score:.2f})")
        return best_match['id']

    # Create new master item
    # Clean up description for name
    name = description[:200]  # Truncate if too long

    # unit_of_measure_id = 14 is "Each"
    inv_cursor.execute("""
        INSERT INTO master_items (name, category, unit_of_measure_id, unit_of_measure, is_active)
        VALUES (%s, %s, 14, 'Each', true)
        RETURNING id
    """, (name, category))
    new_id = inv_cursor.fetchone()['id']
    inv_conn.commit()
    print(f"  Created master item: {name} (category: {category})")
    return new_id


def main():
    print("=" * 60)
    print("Import Missing Vendor Items")
    print("=" * 60)

    # Connect to databases
    hub_conn = psycopg2.connect(**HUB_DB)
    inv_conn = psycopg2.connect(**INVENTORY_DB)
    hub_cursor = hub_conn.cursor(cursor_factory=RealDictCursor)
    inv_cursor = inv_conn.cursor(cursor_factory=RealDictCursor)

    # Get missing item codes with vendor info
    hub_cursor.execute("""
        WITH missing_codes AS (
            SELECT icm.item_code, icm.canonical_description
            FROM item_code_mapping_deprecated icm
            WHERE icm.is_verified = true
            AND icm.item_code NOT IN (
                SELECT vendor_sku FROM dblink(
                    'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                    'SELECT vendor_sku FROM vendor_items WHERE vendor_sku IS NOT NULL'
                ) AS t(vendor_sku VARCHAR)
            )
        ),
        vendor_matches AS (
            SELECT
                mc.item_code,
                mc.canonical_description,
                hi.vendor_name,
                COUNT(*) as occurrences,
                ROW_NUMBER() OVER (PARTITION BY mc.item_code ORDER BY COUNT(*) DESC) as rn
            FROM missing_codes mc
            JOIN hub_invoice_items hii ON hii.item_code = mc.item_code
            JOIN hub_invoices hi ON hi.id = hii.invoice_id
            GROUP BY mc.item_code, mc.canonical_description, hi.vendor_name
        )
        SELECT item_code, canonical_description, vendor_name, occurrences
        FROM vendor_matches
        WHERE rn = 1
        ORDER BY vendor_name, canonical_description
    """)

    missing_items = hub_cursor.fetchall()
    print(f"\nFound {len(missing_items)} missing items to import\n")

    # Track stats
    stats = {
        'imported': 0,
        'skipped_no_vendor': 0,
        'skipped_expense': 0,
        'errors': 0
    }

    # Expense items to skip (will be handled separately)
    expense_items = ['Propane', 'Deliv Chg', '50\' Tt Cord', 'Empty Keg']

    for item in missing_items:
        item_code = item['item_code']
        description = item['canonical_description']
        vendor_name = item['vendor_name']

        print(f"\nProcessing: {description} [{item_code}]")
        print(f"  Vendor: {vendor_name}")

        # Skip expense items
        if any(exp.lower() in description.lower() for exp in expense_items):
            print(f"  SKIPPED: Expense item")
            stats['skipped_expense'] += 1
            continue

        # Map vendor name to ID
        vendor_id = None
        for name_pattern, vid in VENDOR_MAPPING.items():
            if name_pattern.lower() in vendor_name.lower() or vendor_name.lower() in name_pattern.lower():
                vendor_id = vid
                break

        if not vendor_id:
            print(f"  SKIPPED: Unknown vendor '{vendor_name}'")
            stats['skipped_no_vendor'] += 1
            continue

        try:
            # Guess category
            category = guess_category(description)
            print(f"  Category guess: {category}")

            # Get or create master item
            master_item_id = get_or_create_master_item(inv_cursor, inv_conn, description, category)

            # Check if vendor item already exists
            inv_cursor.execute("""
                SELECT id FROM vendor_items
                WHERE vendor_sku = %s AND vendor_id = %s
            """, (item_code, vendor_id))

            if inv_cursor.fetchone():
                print(f"  SKIPPED: Vendor item already exists")
                continue

            # Create vendor item
            # purchase_unit_id = 14 (Each), conversion_factor = 1.0
            inv_cursor.execute("""
                INSERT INTO vendor_items
                (vendor_id, master_item_id, vendor_sku, vendor_product_name,
                 purchase_unit_id, conversion_factor, is_active, is_preferred)
                VALUES (%s, %s, %s, %s, 14, 1.0, true, false)
                RETURNING id
            """, (vendor_id, master_item_id, item_code, description[:200]))

            new_vi_id = inv_cursor.fetchone()['id']
            inv_conn.commit()

            print(f"  CREATED: vendor_item id={new_vi_id}")
            stats['imported'] += 1

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            inv_conn.rollback()
            stats['errors'] += 1

    # Print summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Imported:          {stats['imported']}")
    print(f"  Skipped (expense): {stats['skipped_expense']}")
    print(f"  Skipped (vendor):  {stats['skipped_no_vendor']}")
    print(f"  Errors:            {stats['errors']}")
    print("=" * 60)

    hub_cursor.close()
    inv_cursor.close()
    hub_conn.close()
    inv_conn.close()


if __name__ == '__main__':
    main()
