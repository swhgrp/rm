#!/usr/bin/env python3
"""
Auto-Correct Exact Matches Script

This script automatically corrects unmapped invoice items that have exact
or near-exact matches (≥95% confidence) against existing vendor items.
"""

import os
import sys
import psycopg2
from collections import defaultdict
from difflib import SequenceMatcher

# Database connection settings
INVENTORY_DB = {
    'host': 'inventory-db',
    'database': 'inventory_db',
    'user': 'inventory_user',
    'password': 'inventory_pass'
}

HUB_DB = {
    'host': 'hub-db',
    'database': 'integration_hub_db',
    'user': 'hub_user',
    'password': 'hub_password'
}

def ocr_similarity_score(code1, code2):
    """Calculate similarity considering common OCR errors."""
    if not code1 or not code2:
        return 0.0

    ocr_similar = {
        '0': ['O', 'o', 'Q', 'D'],
        'O': ['0', 'o', 'Q', 'D'],
        '1': ['l', 'I', 'i', '|', '7'],
        'l': ['1', 'I', 'i', '|'],
        'I': ['1', 'l', 'i', '|'],
        '5': ['S', 's'],
        'S': ['5', 's'],
        '8': ['B', '3'],
        'B': ['8', '3'],
        '6': ['G', 'b'],
        'G': ['6', 'g'],
        '2': ['Z', 'z'],
        'Z': ['2', 'z'],
        '9': ['g', 'q'],
        'g': ['9', 'q'],
    }

    code1 = str(code1).strip()
    code2 = str(code2).strip()

    if code1 == code2:
        return 1.0

    if len(code1) != len(code2):
        if code1.endswith(code2) or code2.endswith(code1):
            return 0.85
        if code1.startswith(code2) or code2.startswith(code1):
            return 0.85
        return 0.0

    ocr_errors = 0
    other_errors = 0

    for c1, c2 in zip(code1, code2):
        if c1 == c2:
            continue
        if c2 in ocr_similar.get(c1, []):
            ocr_errors += 1
        else:
            other_errors += 1

    if other_errors == 0 and ocr_errors > 0:
        return max(0.5, 1.0 - (ocr_errors * 0.15))

    if other_errors <= 2 and ocr_errors + other_errors <= 3:
        return max(0.3, 1.0 - (ocr_errors * 0.15) - (other_errors * 0.25))

    return 0.0

def description_similarity(desc1, desc2):
    """Calculate description similarity."""
    if not desc1 or not desc2:
        return 0.0
    desc1 = desc1.lower().strip()
    desc2 = desc2.lower().strip()
    if desc1 == desc2:
        return 1.0
    return SequenceMatcher(None, desc1, desc2).ratio()

def normalize_vendor_name(name):
    """Normalize vendor name for matching."""
    if not name:
        return ""
    name = name.lower().strip()
    for suffix in [' inc.', ' inc', ' llc', ' corp', ' corp.', ' co.', ' co']:
        name = name.replace(suffix, '')
    return name.strip()

def get_unmapped_items(cursor):
    """Get all unmapped items from the hub database."""
    cursor.execute("""
        SELECT DISTINCT
            hii.item_code,
            hii.item_description,
            i.vendor_name,
            COUNT(*) as occurrences
        FROM hub_invoice_items hii
        JOIN hub_invoices i ON hii.invoice_id = i.id
        WHERE hii.is_mapped = FALSE
        GROUP BY hii.item_code, hii.item_description, i.vendor_name
        ORDER BY occurrences DESC
    """)
    return cursor.fetchall()

def get_vendor_items(cursor):
    """Get all vendor items from the inventory database."""
    cursor.execute("""
        SELECT
            vi.id,
            vi.vendor_sku,
            vi.vendor_product_name,
            v.name as vendor_name,
            v.id as vendor_id,
            vi.master_item_id
        FROM vendor_items vi
        JOIN vendors v ON vi.vendor_id = v.id
        WHERE vi.is_active = TRUE
        ORDER BY v.name, vi.vendor_sku
    """)
    return cursor.fetchall()

def find_exact_matches(unmapped_items, vendor_items):
    """Find exact/near-exact matches (≥95% confidence)."""
    matches = []

    vendor_items_by_vendor = defaultdict(list)
    for vi in vendor_items:
        norm_name = normalize_vendor_name(vi[3])
        vendor_items_by_vendor[norm_name].append(vi)

    for unmapped in unmapped_items:
        item_code, item_desc, vendor_name, occurrences = unmapped
        norm_vendor = normalize_vendor_name(vendor_name)

        best_match = None
        best_score = 0

        # Get vendor items for this vendor
        candidate_items = []
        for v_name, v_items in vendor_items_by_vendor.items():
            if v_name in norm_vendor or norm_vendor in v_name or \
               SequenceMatcher(None, v_name, norm_vendor).ratio() > 0.7:
                candidate_items.extend(v_items)

        for vi in candidate_items:
            vi_id, vi_sku, vi_name, vi_vendor, vi_vendor_id, master_item_id = vi

            code_score = ocr_similarity_score(item_code, vi_sku)
            desc_score = description_similarity(item_desc, vi_name)

            if code_score >= 0.85 and desc_score >= 0.5:
                combined_score = code_score * 0.7 + desc_score * 0.3
            elif code_score == 1.0:
                combined_score = 1.0
            else:
                combined_score = 0

            if combined_score >= 0.95 and combined_score > best_score:
                best_score = combined_score
                best_match = vi

        if best_match and best_score >= 0.95:
            matches.append({
                'unmapped_code': item_code,
                'unmapped_desc': item_desc,
                'unmapped_vendor': vendor_name,
                'occurrences': occurrences,
                'match': best_match,
                'score': best_score
            })

    return matches

def apply_corrections(hub_cursor, hub_conn, matches, dry_run=False):
    """Apply corrections to the hub database."""
    print(f"\n{'DRY RUN - ' if dry_run else ''}Applying {len(matches)} corrections...")

    total_rows_updated = 0

    for m in matches:
        vi = m['match']
        vi_id, vi_sku, vi_name, vi_vendor, vi_vendor_id, master_item_id = vi

        # Update all matching unmapped items
        if dry_run:
            hub_cursor.execute("""
                SELECT COUNT(*) FROM hub_invoice_items
                WHERE item_code = %s AND item_description = %s AND is_mapped = FALSE
            """, (m['unmapped_code'], m['unmapped_desc']))
            count = hub_cursor.fetchone()[0]
        else:
            hub_cursor.execute("""
                UPDATE hub_invoice_items
                SET
                    inventory_item_id = %s,
                    inventory_item_name = %s,
                    is_mapped = TRUE,
                    mapping_method = 'fuzzy_match_autocorrect',
                    mapping_confidence = %s,
                    mapped_at = NOW()
                WHERE item_code = %s AND item_description = %s AND is_mapped = FALSE
                RETURNING id
            """, (master_item_id, vi_name, m['score'], m['unmapped_code'], m['unmapped_desc']))
            count = hub_cursor.rowcount

        total_rows_updated += count

        print(f"  [{m['unmapped_code']}] → [{vi_sku}] {vi_name[:50]}... ({count} rows)")

    if not dry_run:
        hub_conn.commit()

    return total_rows_updated

def main():
    dry_run = '--dry-run' in sys.argv

    print("="*80)
    print("AUTO-CORRECT EXACT MATCHES")
    print("="*80)

    if dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")

    print("Connecting to databases...")

    inv_conn = psycopg2.connect(**INVENTORY_DB)
    hub_conn = psycopg2.connect(**HUB_DB)

    try:
        inv_cursor = inv_conn.cursor()
        hub_cursor = hub_conn.cursor()

        print("Fetching vendor items from inventory...")
        vendor_items = get_vendor_items(inv_cursor)
        print(f"  Found {len(vendor_items)} vendor items")

        print("Fetching unmapped items from hub...")
        unmapped_items = get_unmapped_items(hub_cursor)
        print(f"  Found {len(unmapped_items)} unique unmapped items")

        print("Finding exact matches (≥95% confidence)...")
        matches = find_exact_matches(unmapped_items, vendor_items)
        print(f"  Found {len(matches)} exact/near-exact matches")

        if not matches:
            print("\nNo exact matches to correct.")
            return

        # Show what will be corrected
        print("\n" + "-"*80)
        print("MATCHES TO BE CORRECTED:")
        print("-"*80)

        for m in matches:
            vi = m['match']
            print(f"\n  Invoice: [{m['unmapped_code']}] {m['unmapped_desc'][:60]}")
            print(f"  Vendor:  [{vi[1]}] {vi[2][:60]}")
            print(f"  Score: {m['score']:.0%} | Rows: {m['occurrences']}")

        # Apply corrections
        total_rows = apply_corrections(hub_cursor, hub_conn, matches, dry_run)

        print("\n" + "="*80)
        print(f"{'WOULD UPDATE' if dry_run else 'UPDATED'}: {total_rows} invoice rows across {len(matches)} unique items")
        print("="*80)

        if dry_run:
            print("\nRun without --dry-run to apply changes.")

    finally:
        inv_conn.close()
        hub_conn.close()

if __name__ == "__main__":
    main()
