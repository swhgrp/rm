#!/usr/bin/env python3
"""
Restore Category Format to "Parent - Child"

This script restores categories to the hierarchical format (e.g., "Food - Grocery")
based on Hub's category parent-child relationships.

Run with: python3 scripts/restore_category_format.py [--dry-run]
"""

import sys
import os

# Mapping from short category name to full hierarchical format
# Based on Hub's categories table parent-child relationships
SHORT_TO_FULL_CATEGORY = {
    # Food subcategories
    "Bakery": "Food - Bakery",
    "Beef": "Food - Beef",
    "Dairy": "Food - Dairy",
    "Dry Goods": "Food - Dry Goods",
    "Grocery": "Food - Grocery",
    "Pork": "Food - Pork",
    "Poultry": "Food - Poultry",
    "Produce": "Food - Produce",
    "Seafood": "Food - Seafood",

    # Beer subcategories
    "Bottled": "Beer - Bottled",
    "Draft": "Beer - Draft",

    # Liquor subcategories
    "Bourbon/Whiskey/Scotch": "Liquor - Bourbon/Whiskey/Scotch",
    "Cordials": "Liquor - Cordials",
    "Gin": "Liquor - Gin",
    "RTB/Seltzers": "Liquor - RTB/Seltzers",
    "Rum": "Liquor - Rum",
    "Tequila": "Liquor - Tequila",
    "Vodka": "Liquor - Vodka",

    # Top-level categories (no change needed)
    # "NAB", "Wine", "Paper Products", "Cleaning & Chemical", "Food", "Beer", "Liquor"
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
    """Update Hub vendor_items to use full hierarchical category format"""
    from sqlalchemy import text

    conn = get_hub_connection()

    print("=" * 60)
    print("STEP 1: UPDATE HUB VENDOR ITEMS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    stats = {'updated': 0}

    for short_cat, full_cat in SHORT_TO_FULL_CATEGORY.items():
        # Count items with short category
        result = conn.execute(text("""
            SELECT COUNT(*) FROM hub_vendor_items WHERE category = :short_cat
        """), {"short_cat": short_cat}).fetchone()

        count = result[0]
        if count == 0:
            continue

        print(f"  '{short_cat}' -> '{full_cat}': {count} items")

        if not dry_run:
            conn.execute(text("""
                UPDATE hub_vendor_items
                SET category = :full_cat, updated_at = NOW()
                WHERE category = :short_cat
            """), {"short_cat": short_cat, "full_cat": full_cat})

        stats['updated'] += count

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print(f"Hub vendor items updated: {stats['updated']}")
    return stats


def update_inventory_master_items(dry_run=False):
    """Update Inventory master_items to use full hierarchical category format"""
    from sqlalchemy import text

    conn = get_inventory_connection()

    print()
    print("=" * 60)
    print("STEP 2: UPDATE INVENTORY MASTER ITEMS")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    stats = {'updated': 0}

    for short_cat, full_cat in SHORT_TO_FULL_CATEGORY.items():
        # Count items with short category
        result = conn.execute(text("""
            SELECT COUNT(*) FROM master_items WHERE category = :short_cat AND is_active = true
        """), {"short_cat": short_cat}).fetchone()

        count = result[0]
        if count == 0:
            continue

        print(f"  '{short_cat}' -> '{full_cat}': {count} items")

        if not dry_run:
            conn.execute(text("""
                UPDATE master_items
                SET category = :full_cat, updated_at = NOW()
                WHERE category = :short_cat
            """), {"short_cat": short_cat, "full_cat": full_cat})

        stats['updated'] += count

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print(f"Inventory master items updated: {stats['updated']}")
    return stats


def main():
    dry_run = '--dry-run' in sys.argv

    print()
    print("*" * 60)
    print("RESTORE CATEGORY FORMAT: Short -> 'Parent - Child'")
    print("*" * 60)
    print()

    # Step 1: Update Hub vendor items
    hub_stats = update_hub_vendor_items(dry_run=dry_run)

    # Step 2: Update Inventory master items
    inv_stats = update_inventory_master_items(dry_run=dry_run)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Hub vendor items updated: {hub_stats['updated']}")
    print(f"Inventory master items updated: {inv_stats['updated']}")
    print()

    if dry_run:
        print("This was a DRY RUN. No changes were made.")
        print("Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
