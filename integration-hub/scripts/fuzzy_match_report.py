#!/usr/bin/env python3
"""
Fuzzy Match Report Generator

This script analyzes unmapped invoice items against existing vendor items
in the inventory system and generates a report of potential matches.
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

def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def ocr_similarity_score(code1, code2):
    """
    Calculate similarity considering common OCR errors.
    Returns a score between 0 and 1.
    """
    if not code1 or not code2:
        return 0.0

    # Common OCR confusions
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

    # Exact match
    if code1 == code2:
        return 1.0

    # Different lengths - can't be OCR error
    if len(code1) != len(code2):
        # Check if one is a prefix/suffix of other (barcode vs short code)
        if code1.endswith(code2) or code2.endswith(code1):
            return 0.85
        if code1.startswith(code2) or code2.startswith(code1):
            return 0.85
        return 0.0

    # Count OCR-explainable differences
    ocr_errors = 0
    other_errors = 0

    for c1, c2 in zip(code1, code2):
        if c1 == c2:
            continue
        if c2 in ocr_similar.get(c1, []):
            ocr_errors += 1
        else:
            other_errors += 1

    # If all differences are OCR-explainable
    if other_errors == 0 and ocr_errors > 0:
        # Score based on number of OCR errors
        return max(0.5, 1.0 - (ocr_errors * 0.15))

    # Some non-OCR differences
    if other_errors <= 2 and ocr_errors + other_errors <= 3:
        return max(0.3, 1.0 - (ocr_errors * 0.15) - (other_errors * 0.25))

    return 0.0

def description_similarity(desc1, desc2):
    """Calculate description similarity using sequence matching."""
    if not desc1 or not desc2:
        return 0.0

    desc1 = desc1.lower().strip()
    desc2 = desc2.lower().strip()

    # Exact match
    if desc1 == desc2:
        return 1.0

    # Use SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, desc1, desc2).ratio()

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
            v.id as vendor_id
        FROM vendor_items vi
        JOIN vendors v ON vi.vendor_id = v.id
        WHERE vi.is_active = TRUE
        ORDER BY v.name, vi.vendor_sku
    """)
    return cursor.fetchall()

def normalize_vendor_name(name):
    """Normalize vendor name for matching."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [' inc.', ' inc', ' llc', ' corp', ' corp.', ' co.', ' co']:
        name = name.replace(suffix, '')
    return name.strip()

def find_matches(unmapped_items, vendor_items):
    """Find potential matches between unmapped items and vendor items."""
    matches = []

    # Index vendor items by normalized vendor name
    vendor_items_by_vendor = defaultdict(list)
    for vi in vendor_items:
        norm_name = normalize_vendor_name(vi[3])
        vendor_items_by_vendor[norm_name].append(vi)

    for unmapped in unmapped_items:
        item_code, item_desc, vendor_name, occurrences = unmapped
        norm_vendor = normalize_vendor_name(vendor_name)

        best_match = None
        best_score = 0
        match_type = None

        # Get vendor items for this vendor (and similar names)
        candidate_items = []
        for v_name, v_items in vendor_items_by_vendor.items():
            # Check if vendor names match
            if v_name in norm_vendor or norm_vendor in v_name or \
               SequenceMatcher(None, v_name, norm_vendor).ratio() > 0.7:
                candidate_items.extend(v_items)

        # Also check all items if no vendor-specific matches
        if not candidate_items:
            candidate_items = vendor_items

        for vi in candidate_items:
            vi_id, vi_sku, vi_name, vi_vendor, vi_vendor_id = vi

            # Check code similarity
            code_score = ocr_similarity_score(item_code, vi_sku)

            # Check description similarity
            desc_score = description_similarity(item_desc, vi_name)

            # Calculate combined score
            if code_score >= 0.85 and desc_score >= 0.5:
                # High code match + reasonable description
                combined_score = code_score * 0.7 + desc_score * 0.3
                m_type = "code_match"
            elif code_score == 1.0:
                # Exact code match
                combined_score = 1.0
                m_type = "exact_code"
            elif code_score >= 0.7:
                # OCR-likely error in code
                combined_score = code_score * 0.6 + desc_score * 0.4
                m_type = "ocr_error"
            elif desc_score >= 0.8:
                # Strong description match
                combined_score = desc_score * 0.7 + code_score * 0.3
                m_type = "desc_match"
            else:
                combined_score = 0
                m_type = None

            if combined_score > best_score and combined_score >= 0.6:
                best_score = combined_score
                best_match = vi
                match_type = m_type

        matches.append({
            'unmapped_code': item_code,
            'unmapped_desc': item_desc,
            'unmapped_vendor': vendor_name,
            'occurrences': occurrences,
            'match': best_match,
            'score': best_score,
            'match_type': match_type
        })

    return matches

def generate_report(matches):
    """Generate a report of the matches."""
    print("\n" + "="*100)
    print("FUZZY MATCH REPORT - Unmapped Invoice Items vs Vendor Items")
    print("="*100)

    # Categorize matches
    exact_matches = [m for m in matches if m['score'] >= 0.95]
    high_confidence = [m for m in matches if 0.8 <= m['score'] < 0.95]
    medium_confidence = [m for m in matches if 0.6 <= m['score'] < 0.8]
    no_match = [m for m in matches if m['score'] < 0.6]

    print(f"\nSUMMARY:")
    print(f"  Total unmapped items: {len(matches)}")
    print(f"  Exact/Near-exact matches (≥95%): {len(exact_matches)}")
    print(f"  High confidence matches (80-95%): {len(high_confidence)}")
    print(f"  Medium confidence matches (60-80%): {len(medium_confidence)}")
    print(f"  No match found (<60%): {len(no_match)}")

    total_rows_fixable = sum(m['occurrences'] for m in exact_matches + high_confidence)
    total_rows = sum(m['occurrences'] for m in matches)
    print(f"\n  Invoice rows that can be auto-corrected: {total_rows_fixable} of {total_rows}")

    # Print exact matches
    if exact_matches:
        print("\n" + "-"*100)
        print("EXACT/NEAR-EXACT MATCHES (≥95% confidence) - Safe to auto-correct")
        print("-"*100)
        for m in sorted(exact_matches, key=lambda x: -x['occurrences']):
            vi = m['match']
            print(f"\n  Invoice: [{m['unmapped_code']}] {m['unmapped_desc'][:60]}")
            print(f"  Vendor:  [{vi[1]}] {vi[2][:60]}")
            print(f"  Score: {m['score']:.0%} ({m['match_type']}) | Occurrences: {m['occurrences']} | Vendor: {m['unmapped_vendor']}")

    # Print high confidence matches
    if high_confidence:
        print("\n" + "-"*100)
        print("HIGH CONFIDENCE MATCHES (80-95%) - Review recommended")
        print("-"*100)
        for m in sorted(high_confidence, key=lambda x: -x['occurrences']):
            vi = m['match']
            print(f"\n  Invoice: [{m['unmapped_code']}] {m['unmapped_desc'][:60]}")
            print(f"  Vendor:  [{vi[1]}] {vi[2][:60]}")
            print(f"  Score: {m['score']:.0%} ({m['match_type']}) | Occurrences: {m['occurrences']} | Vendor: {m['unmapped_vendor']}")

    # Print medium confidence matches
    if medium_confidence:
        print("\n" + "-"*100)
        print("MEDIUM CONFIDENCE MATCHES (60-80%) - Manual review required")
        print("-"*100)
        for m in sorted(medium_confidence, key=lambda x: -x['occurrences'])[:20]:
            vi = m['match']
            print(f"\n  Invoice: [{m['unmapped_code']}] {m['unmapped_desc'][:60]}")
            print(f"  Vendor:  [{vi[1]}] {vi[2][:60]}")
            print(f"  Score: {m['score']:.0%} ({m['match_type']}) | Occurrences: {m['occurrences']} | Vendor: {m['unmapped_vendor']}")
        if len(medium_confidence) > 20:
            print(f"\n  ... and {len(medium_confidence) - 20} more medium confidence matches")

    # Print no matches
    if no_match:
        print("\n" + "-"*100)
        print("NO MATCH FOUND - These may be new items or need manual entry")
        print("-"*100)
        for m in sorted(no_match, key=lambda x: -x['occurrences'])[:30]:
            print(f"\n  [{m['unmapped_code']}] {m['unmapped_desc'][:70]}")
            print(f"  Vendor: {m['unmapped_vendor']} | Occurrences: {m['occurrences']}")
        if len(no_match) > 30:
            print(f"\n  ... and {len(no_match) - 30} more items with no match")

    return {
        'exact': exact_matches,
        'high': high_confidence,
        'medium': medium_confidence,
        'none': no_match
    }

def main():
    print("Connecting to databases...")

    # Connect to both databases
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

        print("Analyzing matches...")
        matches = find_matches(unmapped_items, vendor_items)

        results = generate_report(matches)

        return results

    finally:
        inv_conn.close()
        hub_conn.close()

if __name__ == "__main__":
    main()
