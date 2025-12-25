#!/usr/bin/env python3
"""
Auto-Import Unmapped Items to Inventory

This script analyzes unmapped invoice items and automatically creates
vendor items in inventory for items that appear multiple times.

It learns from invoice patterns and reduces manual mapping work.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from difflib import SequenceMatcher
import re
import argparse

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
    'Southern Glazer': 6,
    'Breakthru Beverage': 7,
    'Double Eagle Distributing': 5,
    'Southern Eagle Distributing': 8,
    'Republic National Distributing': 10,
    'BJs': 2,
    'Sam\'s': 3,
}

# Category guessing based on item description patterns
CATEGORY_PATTERNS = [
    (r'\b(vodka|gin|rum|tequila|whiskey|bourbon|brandy|cognac|liqueur|scotch|mezcal)\b', 'Liquor'),
    (r'\b(wine|prosecco|champagne|merlot|cabernet|chardonnay|pinot|sauvignon|grigio|cktl)\b', 'Wine'),
    (r'\b(beer|lager|ale|ipa|stout|pilsner|bud light|corona|modelo|michelob|yuengling|heineken|coors|lite)\b', 'Bottled'),
    (r'\b(bacon|ham|pork|sausage)\b', 'Pork'),
    (r'\b(chicken|poultry|chix|chik)\b', 'Chicken'),
    (r'\b(beef|steak|burger|patty)\b', 'Beef'),
    (r'\b(fish|shrimp|lobster|crab|salmon|grouper|tuna|seafood)\b', 'Seafood'),
    (r'\b(cheese|dairy|milk|cream|butter)\b', 'Dairy'),
    (r'\b(lettuce|tomato|onion|pepper|vegetable|produce)\b', 'Produce'),
    (r'\b(soda|cola|sprite|powerade|gatorade|juice|tea|lemonade)\b', 'Beverages - Non Alcoholic'),
    (r'\b(bag|container|wrap|foil|cup|napkin|straw|utensil)\b', 'Supplies - Disposable'),
    (r'\b(towel|apron|mat|linen|uniform|mop|wetmop)\b', 'Supplies - Linen'),
    (r'\b(sauce|dressing|mayo|ketchup|mustard|relish|alfredo)\b', 'Condiments'),
    (r'\b(oil|olive)\b', 'Oils'),
    (r'\b(fries|potato)\b', 'Frozen'),
    (r'\b(ice cream|gelato)\b', 'Frozen'),
    (r'\b(propane|gas|fuel)\b', 'Expense - Utilities'),
    (r'\b(cleaner|degreaser|sanitizer|soap)\b', 'Supplies - Cleaning'),
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

    if best_match and score > 0.7:
        print(f"    Found master item: {best_match['name']} (score: {score:.2f})")
        return best_match['id']

    # Create new master item
    name = description[:200]  # Truncate if too long

    inv_cursor.execute("""
        INSERT INTO master_items (name, category, unit_of_measure_id, unit_of_measure, is_active)
        VALUES (%s, %s, 14, 'Each', true)
        RETURNING id
    """, (name, category))
    new_id = inv_cursor.fetchone()['id']
    inv_conn.commit()
    print(f"    Created master item: {name} (category: {category})")
    return new_id


def map_vendor_name(vendor_name):
    """Map invoice vendor name to inventory vendor_id"""
    for name_pattern, vid in VENDOR_MAPPING.items():
        if name_pattern.lower() in vendor_name.lower() or vendor_name.lower() in name_pattern.lower():
            return vid
    return None


def main():
    parser = argparse.ArgumentParser(description='Auto-import unmapped items to inventory')
    parser.add_argument('--min-occurrences', type=int, default=2,
                       help='Minimum occurrences to auto-import (default: 2)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be imported without making changes')
    parser.add_argument('--vendor', type=str, default=None,
                       help='Only process items from this vendor (partial match)')
    args = parser.parse_args()

    print("=" * 60)
    print("Auto-Import Unmapped Items")
    print("=" * 60)
    if args.dry_run:
        print("*** DRY RUN - No changes will be made ***")
    print(f"Minimum occurrences: {args.min_occurrences}")
    if args.vendor:
        print(f"Vendor filter: {args.vendor}")
    print()

    # Connect to databases
    hub_conn = psycopg2.connect(**HUB_DB)
    inv_conn = psycopg2.connect(**INVENTORY_DB)
    hub_cursor = hub_conn.cursor(cursor_factory=RealDictCursor)
    inv_cursor = inv_conn.cursor(cursor_factory=RealDictCursor)

    # Find unmapped items with multiple occurrences
    query = """
        SELECT
            hii.item_code,
            hii.item_description,
            hi.vendor_name,
            COUNT(*) as occurrences
        FROM hub_invoice_items hii
        JOIN hub_invoices hi ON hi.id = hii.invoice_id
        WHERE hii.is_mapped = false
          AND hii.item_code IS NOT NULL
          AND hii.item_code != ''
          AND LENGTH(hii.item_code) <= 10
    """

    if args.vendor:
        query += f" AND hi.vendor_name ILIKE '%{args.vendor}%'"

    query += """
        GROUP BY hii.item_code, hii.item_description, hi.vendor_name
        HAVING COUNT(*) >= %s
        ORDER BY COUNT(*) DESC, hi.vendor_name
    """

    hub_cursor.execute(query, (args.min_occurrences,))
    unmapped_items = hub_cursor.fetchall()

    print(f"Found {len(unmapped_items)} unmapped items with >= {args.min_occurrences} occurrences\n")

    # Track stats
    stats = {
        'imported': 0,
        'skipped_no_vendor': 0,
        'skipped_exists': 0,
        'skipped_expense': 0,
        'errors': 0
    }

    # Expense items to skip
    expense_keywords = ['propane', 'deliv chg', 'cord', 'empty keg', 'labor', 'service', 'repair']

    for item in unmapped_items:
        item_code = item['item_code']
        description = item['item_description']
        vendor_name = item['vendor_name']
        occurrences = item['occurrences']

        print(f"\nProcessing: {description} [{item_code}] ({occurrences}x)")
        print(f"  Vendor: {vendor_name}")

        # Skip expense items
        if any(exp.lower() in description.lower() for exp in expense_keywords):
            print(f"  SKIPPED: Expense item")
            stats['skipped_expense'] += 1
            continue

        # Map vendor
        vendor_id = map_vendor_name(vendor_name)
        if not vendor_id:
            print(f"  SKIPPED: Unknown vendor '{vendor_name}'")
            stats['skipped_no_vendor'] += 1
            continue

        # Check if vendor item already exists
        inv_cursor.execute("""
            SELECT id FROM vendor_items
            WHERE vendor_sku = %s AND vendor_id = %s
        """, (item_code, vendor_id))

        if inv_cursor.fetchone():
            print(f"  SKIPPED: Vendor item already exists")
            stats['skipped_exists'] += 1
            continue

        # Also check with leading zeros (for Southern Glaziers)
        inv_cursor.execute("""
            SELECT id FROM vendor_items
            WHERE vendor_sku = %s AND vendor_id = %s
        """, (item_code.lstrip('0'), vendor_id))

        if inv_cursor.fetchone():
            print(f"  SKIPPED: Vendor item already exists (without leading zeros)")
            stats['skipped_exists'] += 1
            continue

        if args.dry_run:
            category = guess_category(description)
            print(f"  WOULD CREATE: category={category}")
            stats['imported'] += 1
            continue

        try:
            # Guess category
            category = guess_category(description)
            print(f"  Category: {category}")

            # Get or create master item
            master_item_id = get_or_create_master_item(inv_cursor, inv_conn, description, category)

            # Create vendor item
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
    print(f"  {'Would import' if args.dry_run else 'Imported'}:  {stats['imported']}")
    print(f"  Skipped (expense): {stats['skipped_expense']}")
    print(f"  Skipped (vendor):  {stats['skipped_no_vendor']}")
    print(f"  Skipped (exists):  {stats['skipped_exists']}")
    print(f"  Errors:            {stats['errors']}")
    print("=" * 60)

    hub_cursor.close()
    inv_cursor.close()
    hub_conn.close()
    inv_conn.close()

    return stats['imported']


if __name__ == '__main__':
    main()
