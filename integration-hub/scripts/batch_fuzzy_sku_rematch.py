#!/usr/bin/env python3
"""
Batch fuzzy-SKU rematch for unmapped invoice items.

Uses combined SKU distance + description similarity to find confident matches.
The auto-mapper's match_by_near_sku() handles the logic:
- Distance 1, single match → accept (no description needed)
- Distance 1, multiple matches → description picks the winner
- Distance 2 → requires description confirmation (rejects false positives)

Usage:
    # Dry run — report only (default, distance 2 with desc matching)
    docker compose exec integration-hub python scripts/batch_fuzzy_sku_rematch.py

    # Apply matches
    docker compose exec integration-hub python scripts/batch_fuzzy_sku_rematch.py --apply

    # Custom vendor filter
    docker compose exec integration-hub python scripts/batch_fuzzy_sku_rematch.py --vendor gordon

    # Stricter distance
    docker compose exec integration-hub python scripts/batch_fuzzy_sku_rematch.py --max-distance 1
"""
import sys
import os
import argparse
import logging
from collections import defaultdict

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import distinct
from integration_hub.db.database import SessionLocal
from integration_hub.models import HubInvoice, HubInvoiceItem
from integration_hub.services.auto_mapper import AutoMapperService, calculate_similarity

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def find_near_sku_matches(db, vendor_filter: str, max_distance: int):
    """
    Use the auto-mapper's match_by_near_sku (with description) to find matches.

    Returns:
        (matches, no_match)
        - matches: [(item, vendor_item_dict, desc_score), ...]
        - no_match: [item, ...]
    """
    # Get all vendor IDs matching the filter
    vendor_ids = [row[0] for row in db.query(distinct(HubInvoice.vendor_id)).filter(
        HubInvoice.vendor_name.ilike(f'%{vendor_filter}%'),
        HubInvoice.vendor_id.isnot(None)
    ).all()]

    if not vendor_ids:
        logger.error(f"No vendors found matching '{vendor_filter}'")
        return [], []

    logger.info(f"Vendor IDs matching '{vendor_filter}': {vendor_ids}")

    mapper = AutoMapperService(db)
    # Pre-load vendor items cache
    mapper.fetch_vendor_items()

    # Get all unmapped items with item codes from matching vendors
    unmapped_items = db.query(HubInvoiceItem).join(HubInvoice).filter(
        HubInvoiceItem.is_mapped == False,
        HubInvoice.vendor_id.in_(vendor_ids),
        HubInvoiceItem.item_code.isnot(None),
        HubInvoiceItem.item_code != ''
    ).all()

    logger.info(f"Found {len(unmapped_items)} unmapped items with item codes")

    # Cache invoice vendor_id lookups
    invoice_cache = {}

    matches = []
    no_match = []

    for item in unmapped_items:
        # Get invoice info
        if item.invoice_id not in invoice_cache:
            inv = db.query(HubInvoice).filter(HubInvoice.id == item.invoice_id).first()
            invoice_cache[item.invoice_id] = inv
        invoice = invoice_cache[item.invoice_id]
        if not invoice:
            continue

        vendor_id = invoice.vendor_id
        location_id = invoice.location_id

        # First check exact SKU (skip these — already handled by normal auto-mapper)
        exact = mapper.match_by_sku(item.item_code, vendor_id, location_id)
        if exact:
            continue

        # Try near-SKU with description matching
        vi = mapper.match_by_near_sku(
            item.item_code,
            vendor_id=vendor_id,
            location_id=location_id,
            max_distance=max_distance,
            item_description=item.item_description
        )

        if vi:
            desc_score = 0.0
            if item.item_description and vi.get('vendor_product_name'):
                desc_score = calculate_similarity(item.item_description, vi['vendor_product_name'])
            matches.append((item, vi, desc_score))
        else:
            no_match.append(item)

    return matches, no_match


def print_report(matches, no_match, apply_mode):
    """Print a detailed report of findings."""
    total = len(matches) + len(no_match)
    print(f"\n{'='*90}")
    print(f"FUZZY SKU + DESCRIPTION REMATCH REPORT")
    print(f"{'='*90}")
    print(f"  Total unmapped items checked:       {total}")
    print(f"  Matched (SKU near + desc confirm):  {len(matches)}")
    print(f"  No match:                           {len(no_match)}")
    print(f"{'='*90}")

    if matches:
        print(f"\nMATCHES ({'WILL APPLY' if apply_mode else 'DRY RUN — use --apply to map'}):")
        print(f"{'Invoice Code':<12} {'→':^3} {'Vendor SKU':<12} {'Invoice Description':<30} {'Vendor Product Name':<30} {'Desc%':>5}")
        print(f"{'-'*12:<12} {'':^3} {'-'*12:<12} {'-'*30:<30} {'-'*30:<30} {'-'*5:>5}")
        for item, vi, desc_score in sorted(matches, key=lambda x: -x[2]):
            inv_desc = (item.item_description or '')[:30]
            vend_name = vi.get('vendor_product_name', '')[:30]
            pct = f"{desc_score*100:.0f}%"
            print(f"{item.item_code:<12} {'→':^3} {vi.get('vendor_sku', ''):<12} {inv_desc:<30} {vend_name:<30} {pct:>5}")
        print()

    if no_match:
        print(f"\nNO MATCH ({len(no_match)} items):")
        code_counts = defaultdict(int)
        code_descs = {}
        for item in no_match:
            code_counts[item.item_code] += 1
            code_descs[item.item_code] = item.item_description
        for code, count in sorted(code_counts.items(), key=lambda x: -x[1])[:20]:
            desc = code_descs[code][:40]
            print(f"  {code:<15} {desc:<40} ({count}x)")
        if len(code_counts) > 20:
            print(f"  ... and {len(code_counts) - 20} more unique codes")
        print()


def apply_matches(db, matches):
    """Apply the matches using the auto-mapper pipeline."""
    mapper = AutoMapperService(db)
    applied = 0
    skipped_gl = 0
    errors = 0

    for item, vi, desc_score in matches:
        try:
            confidence = min(0.95, 0.7 + desc_score * 0.3)  # 0.7-0.95 based on desc match
            result = mapper._build_mapping_result(vi, 'near_sku_match', confidence=confidence)
            result['matched_location_id'] = vi.get('location_id')
            result['is_cross_location'] = False

            if mapper.apply_mapping(item, result):
                applied += 1
            else:
                skipped_gl += 1
        except Exception as e:
            logger.error(f"Error applying match for item {item.id} (code={item.item_code}): {e}")
            errors += 1

    db.commit()

    # Update invoice statuses
    invoice_ids = set(item.invoice_id for item, _, _ in matches)
    try:
        from integration_hub.services.invoice_status import update_invoice_status
        for inv_id in invoice_ids:
            invoice = db.query(HubInvoice).filter(HubInvoice.id == inv_id).first()
            if invoice:
                update_invoice_status(invoice, db)
        db.commit()
    except ImportError:
        pass

    # Save learned mappings for future invoices
    learned = 0
    for item, vi, _ in matches:
        try:
            invoice = db.query(HubInvoice).filter(HubInvoice.id == item.invoice_id).first()
            if invoice and invoice.vendor_id:
                mapper.save_learned_mapping(
                    vendor_id=invoice.vendor_id,
                    item_code=item.item_code,
                    item_description=item.item_description,
                    vendor_item_id=vi['id']
                )
                learned += 1
        except Exception as e:
            logger.debug(f"Could not save learned mapping: {e}")

    print(f"\nAPPLY RESULTS:")
    print(f"  Fully mapped (with GL):    {applied}")
    print(f"  Linked but no GL:          {skipped_gl}")
    print(f"  Errors:                    {errors}")
    print(f"  Learned mappings saved:    {learned}")


def main():
    parser = argparse.ArgumentParser(
        description='Batch fuzzy-SKU rematch with description confirmation'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='Apply matches (default is dry-run report only)'
    )
    parser.add_argument(
        '--max-distance', type=int, default=2,
        help='Max Levenshtein distance for SKU matching (default: 2)'
    )
    parser.add_argument(
        '--vendor', type=str, default='gordon',
        help='Vendor name filter, case-insensitive (default: gordon)'
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        matches, no_match = find_near_sku_matches(
            db, args.vendor, args.max_distance
        )

        print_report(matches, no_match, args.apply)

        if args.apply and matches:
            confirm = input(f"\nApply {len(matches)} matches? [y/N]: ").strip().lower()
            if confirm == 'y':
                apply_matches(db, matches)
            else:
                print("Aborted.")
        elif args.apply and not matches:
            print("No matches to apply.")
    finally:
        db.close()


if __name__ == '__main__':
    main()
