#!/usr/bin/env python3
"""
Sync Categories to Hub Format

This script updates categories from the old format (e.g., "Food - Grocery")
to the new Hub format (e.g., "Grocery").

Hub's categories table is the source of truth. This script:
1. Updates Hub vendor_items to use Hub category names
2. Syncs those categories to Inventory master_items

Run with: python3 scripts/sync_categories_to_hub_format.py [--dry-run]
"""

import sys
import os

# Mapping from old category format to new Hub category name
# Old format: "Parent - Child" or "Parent - Child"
# New format: Just the category name from Hub's categories table
OLD_TO_NEW_CATEGORY = {
    # Food categories
    "Food - Bakery": "Bakery",
    "Food - Beef": "Beef",
    "Food - Dairy": "Dairy",
    "Food - Dry Goods": "Dry Goods",
    "Food - Grocery": "Grocery",
    "Food - Pork": "Pork",
    "Food - Poultry": "Poultry",
    "Food - Produce": "Produce",
    "Food - Seafood": "Seafood",

    # Beer categories
    "Beer - Bottled": "Bottled",
    "Beer - Draft": "Draft",

    # Liquor categories
    "Liquor - Bourbon/Whiskey/Scotch": "Bourbon/Whiskey/Scotch",
    "Liquor - Cordials": "Cordials",
    "Liquor - Gin": "Gin",
    "Liquor - RTB/Seltzers": "RTB/Seltzers",
    "Liquor - Rum": "Rum",
    "Liquor - Tequila": "Tequila",
    "Liquor - Vodka": "Vodka",

    # These are already correct (no parent prefix)
    "NAB": "NAB",
    "Wine": "Wine",
    "Paper Products": "Paper Products",
    "Cleaning & Chemical": "Cleaning & Chemical",
}


def get_hub_connection():
    """Get connection to Hub database"""
    from sqlalchemy import create_engine
    db_url = os.getenv(
        'HUB_DATABASE_URL',
        'postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db'
    )
    engine = create_engine(db_url)
    return engine.connect()


def get_inventory_connection():
    """Get connection to Inventory database"""
    from sqlalchemy import create_engine
    db_url = os.getenv(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )
    engine = create_engine(db_url)
    return engine.connect()


def update_hub_vendor_items(dry_run=False):
    """Update Hub vendor_items to use new category format"""
    from sqlalchemy import text

    conn = get_hub_connection()

    print("=" * 60)
    print("STEP 1: UPDATE HUB VENDOR ITEMS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    stats = {'updated': 0, 'skipped': 0}

    for old_cat, new_cat in OLD_TO_NEW_CATEGORY.items():
        if old_cat == new_cat:
            # Already correct format
            continue

        # Count items with old category
        result = conn.execute(text("""
            SELECT COUNT(*) FROM hub_vendor_items WHERE category = :old_cat
        """), {"old_cat": old_cat}).fetchone()

        count = result[0]
        if count == 0:
            continue

        print(f"  '{old_cat}' -> '{new_cat}': {count} items")

        if not dry_run:
            conn.execute(text("""
                UPDATE hub_vendor_items
                SET category = :new_cat, updated_at = NOW()
                WHERE category = :old_cat
            """), {"old_cat": old_cat, "new_cat": new_cat})

        stats['updated'] += count

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print(f"Hub vendor items updated: {stats['updated']}")
    return stats


def sync_categories_to_inventory(dry_run=False):
    """Sync categories from Hub vendor items to Inventory master items"""
    from sqlalchemy import text

    hub_conn = get_hub_connection()
    inv_conn = get_inventory_connection()

    print()
    print("=" * 60)
    print("STEP 2: SYNC TO INVENTORY MASTER ITEMS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    # Get all mapped vendor items with their categories
    # Use DISTINCT ON to get one category per master item (in case of multiple vendor items)
    mapped_items = hub_conn.execute(text("""
        SELECT DISTINCT ON (inventory_master_item_id)
            inventory_master_item_id,
            category,
            inventory_master_item_name
        FROM hub_vendor_items
        WHERE inventory_master_item_id IS NOT NULL
          AND category IS NOT NULL
        ORDER BY inventory_master_item_id, updated_at DESC
    """)).fetchall()

    print(f"Found {len(mapped_items)} mapped master items in Hub")
    print()

    stats = {'updated': 0, 'already_correct': 0, 'not_found': 0}

    for row in mapped_items:
        master_item_id = row[0]
        hub_category = row[1]
        item_name = row[2]

        # Get current category from Inventory
        inv_result = inv_conn.execute(text("""
            SELECT category FROM master_items WHERE id = :id
        """), {"id": master_item_id}).fetchone()

        if not inv_result:
            stats['not_found'] += 1
            print(f"  NOT FOUND: Master item {master_item_id} ({item_name})")
            continue

        current_category = inv_result[0]

        if current_category == hub_category:
            stats['already_correct'] += 1
            continue

        print(f"  UPDATE: {master_item_id} ({item_name}): '{current_category}' -> '{hub_category}'")

        if not dry_run:
            inv_conn.execute(text("""
                UPDATE master_items
                SET category = :category, updated_at = NOW()
                WHERE id = :id
            """), {"id": master_item_id, "category": hub_category})

        stats['updated'] += 1

    if not dry_run:
        inv_conn.commit()

    hub_conn.close()
    inv_conn.close()

    print()
    print(f"Master items updated: {stats['updated']}")
    print(f"Already correct: {stats['already_correct']}")
    print(f"Not found in Inventory: {stats['not_found']}")

    return stats


def update_unmapped_inventory_items(dry_run=False):
    """Update Inventory master items that aren't mapped to Hub vendor items"""
    from sqlalchemy import text

    inv_conn = get_inventory_connection()

    print()
    print("=" * 60)
    print("STEP 3: UPDATE UNMAPPED INVENTORY ITEMS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    stats = {'updated': 0}

    for old_cat, new_cat in OLD_TO_NEW_CATEGORY.items():
        if old_cat == new_cat:
            continue

        # Count items with old category
        result = inv_conn.execute(text("""
            SELECT COUNT(*) FROM master_items WHERE category = :old_cat AND is_active = true
        """), {"old_cat": old_cat}).fetchone()

        count = result[0]
        if count == 0:
            continue

        print(f"  '{old_cat}' -> '{new_cat}': {count} items")

        if not dry_run:
            inv_conn.execute(text("""
                UPDATE master_items
                SET category = :new_cat, updated_at = NOW()
                WHERE category = :old_cat
            """), {"old_cat": old_cat, "new_cat": new_cat})

        stats['updated'] += count

    if not dry_run:
        inv_conn.commit()

    inv_conn.close()

    print()
    print(f"Unmapped inventory items updated: {stats['updated']}")
    return stats


def main():
    dry_run = '--dry-run' in sys.argv

    print()
    print("*" * 60)
    print("CATEGORY SYNC: OLD FORMAT -> HUB FORMAT")
    print("*" * 60)
    print()

    # Step 1: Update Hub vendor items
    hub_stats = update_hub_vendor_items(dry_run=dry_run)

    # Step 2: Sync mapped items to Inventory
    sync_stats = sync_categories_to_inventory(dry_run=dry_run)

    # Step 3: Update any remaining unmapped Inventory items
    inv_stats = update_unmapped_inventory_items(dry_run=dry_run)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Hub vendor items updated: {hub_stats['updated']}")
    print(f"Inventory items synced from Hub: {sync_stats['updated']}")
    print(f"Inventory items updated (unmapped): {inv_stats['updated']}")
    print()

    if dry_run:
        print("This was a DRY RUN. No changes were made.")
        print("Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
