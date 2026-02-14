#!/usr/bin/env python3
"""
Fix GFS UOM mismatches: invoice items parsed as CS but matched to EA UOM.

For each affected vendor item:
1. Add a CS UOM (using units_per_case as conversion_factor)
2. Re-match invoice items to use the new CS UOM

Usage:
    # Dry run (report only)
    docker compose exec integration-hub python scripts/fix_gfs_uom_mismatch.py

    # Apply fixes
    docker compose exec integration-hub python scripts/fix_gfs_uom_mismatch.py --apply
"""
import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text
from integration_hub.db.database import SessionLocal

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# UOM ID for "cs" (Case) in units_of_measure table
CS_UOM_ID = 3
EA_UOM_ID = 1
GFS_VENDOR_ID = 5


def find_mismatches(db):
    """Find GFS invoice items where parsed UOM=CS but matched to EA."""
    result = db.execute(text("""
        SELECT
            hvi.id as vendor_item_id,
            hvi.vendor_sku,
            hvi.vendor_product_name,
            hvi.units_per_case,
            viu_ea.id as ea_uom_id,
            COUNT(hii.id) as item_count,
            ROUND(AVG(hii.unit_price::numeric), 2) as avg_price
        FROM hub_invoice_items hii
        JOIN hub_invoices hi ON hi.id = hii.invoice_id
        JOIN hub_vendor_items hvi ON hvi.id = hii.inventory_item_id
        JOIN vendor_item_uoms viu_ea ON viu_ea.id = hii.matched_uom_id
        JOIN units_of_measure uom ON uom.id = viu_ea.uom_id
        WHERE hi.vendor_id = :vendor_id
          AND hii.is_mapped = true
          AND UPPER(hii.unit_of_measure) = 'CS'
          AND UPPER(uom.abbreviation) = 'EA'
        GROUP BY hvi.id, hvi.vendor_sku, hvi.vendor_product_name, hvi.units_per_case, viu_ea.id
        ORDER BY item_count DESC
    """), {"vendor_id": GFS_VENDOR_ID})

    return [dict(row._mapping) for row in result]


def find_all_uom_mismatches(db):
    """Find ALL UOM mismatches (not just CS→EA), for the report."""
    result = db.execute(text("""
        SELECT
            hii.unit_of_measure as parsed_uom,
            uom.abbreviation as matched_uom,
            COUNT(*) as item_count,
            COUNT(DISTINCT hii.inventory_item_id) as vendor_items
        FROM hub_invoice_items hii
        JOIN hub_invoices hi ON hi.id = hii.invoice_id
        JOIN vendor_item_uoms viu ON viu.id = hii.matched_uom_id
        JOIN units_of_measure uom ON uom.id = viu.uom_id
        WHERE hi.vendor_id = :vendor_id
          AND hii.is_mapped = true
          AND UPPER(hii.unit_of_measure) != UPPER(uom.abbreviation)
        GROUP BY hii.unit_of_measure, uom.abbreviation
        ORDER BY item_count DESC
    """), {"vendor_id": GFS_VENDOR_ID})
    return [dict(row._mapping) for row in result]


def check_existing_cs_uom(db, vendor_item_id, desired_cf=None):
    """Check if vendor item already has a CS UOM. Update cf if needed."""
    result = db.execute(text("""
        SELECT id, conversion_factor, is_active FROM vendor_item_uoms
        WHERE vendor_item_id = :vi_id AND uom_id = :cs_id
    """), {"vi_id": vendor_item_id, "cs_id": CS_UOM_ID})
    row = result.fetchone()
    if not row:
        return None
    uom_id, current_cf, is_active = row
    # Activate if inactive
    if not is_active:
        db.execute(text("UPDATE vendor_item_uoms SET is_active = true WHERE id = :id"),
                   {"id": uom_id})
    # Update conversion factor if different
    if desired_cf and float(current_cf) != desired_cf:
        db.execute(text("UPDATE vendor_item_uoms SET conversion_factor = :cf WHERE id = :id"),
                   {"cf": desired_cf, "id": uom_id})
        logger.info(f"Updated CS UOM (id={uom_id}) cf: {current_cf} → {desired_cf}")
    return uom_id


def apply_fixes(db, mismatches):
    """Add CS UOMs and re-match invoice items."""
    created_uoms = 0
    rematched_items = 0
    skipped_existing = 0

    for m in mismatches:
        vi_id = m['vendor_item_id']
        cf = float(m['units_per_case'] or 1)

        # Check if CS UOM already exists
        existing_cs = check_existing_cs_uom(db, vi_id, desired_cf=cf)
        if existing_cs:
            cs_uom_id = existing_cs
            skipped_existing += 1
        else:
            # Create CS UOM
            result = db.execute(text("""
                INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
                VALUES (:vi_id, :uom_id, :cf, false, true)
                RETURNING id
            """), {"vi_id": vi_id, "uom_id": CS_UOM_ID, "cf": cf})
            cs_uom_id = result.fetchone()[0]
            created_uoms += 1
            logger.info(f"Created CS UOM (id={cs_uom_id}) for vendor item {vi_id} "
                       f"({m['vendor_sku']}) cf={cf}")

        # Re-match invoice items: update matched_uom_id from EA to CS
        result = db.execute(text("""
            UPDATE hub_invoice_items hii
            SET matched_uom_id = :cs_uom_id
            FROM hub_invoices hi
            WHERE hi.id = hii.invoice_id
              AND hi.vendor_id = :vendor_id
              AND hii.inventory_item_id = :vi_id
              AND hii.is_mapped = true
              AND UPPER(hii.unit_of_measure) = 'CS'
              AND hii.matched_uom_id = :ea_uom_id
        """), {
            "cs_uom_id": cs_uom_id,
            "vendor_id": GFS_VENDOR_ID,
            "vi_id": vi_id,
            "ea_uom_id": m['ea_uom_id'],
        })
        count = result.rowcount
        rematched_items += count
        if count > 0:
            logger.info(f"  → Re-matched {count} invoice items to CS UOM")

    db.commit()
    return created_uoms, rematched_items, skipped_existing


def print_report(mismatches, all_mismatches, apply_mode):
    """Print detailed report."""
    total_items = sum(m['item_count'] for m in mismatches)

    print(f"\n{'='*95}")
    print(f"GFS UOM MISMATCH FIX REPORT")
    print(f"{'='*95}")
    print(f"  Vendor items with CS→EA mismatch: {len(mismatches)}")
    print(f"  Total invoice items affected:      {total_items}")
    print(f"{'='*95}")

    if mismatches:
        print(f"\n{'WILL FIX' if apply_mode else 'DRY RUN — use --apply to fix'}:")
        print(f"{'SKU':<10} {'Product':<45} {'UPC':>3} {'CF':>5} {'Items':>5} {'Avg Price':>10} {'Cost Impact'}")
        print(f"{'-'*10} {'-'*45} {'-'*3:>3} {'-'*5:>5} {'-'*5:>5} {'-'*10:>10} {'-'*20}")
        for m in mismatches:
            cf = float(m['units_per_case'] or 1)
            avg_price = float(m['avg_price'] or 0)
            product = (m['vendor_product_name'] or '')[:45]
            # Show cost impact: old cost/ea vs new cost/ea
            old_cost = avg_price  # / 1 (EA cf=1)
            new_cost = avg_price / cf if cf > 0 else avg_price
            if cf > 1:
                impact = f"${old_cost:.2f}→${new_cost:.2f}/ea (÷{cf:.0f})"
            else:
                impact = f"label only (cf=1)"
            print(f"{m['vendor_sku']:<10} {product:<45} {cf:>3.0f} {cf:>5.0f} {m['item_count']:>5} {avg_price:>10.2f} {impact}")

    # Show items with cf > 1 separately (these have real cost impact)
    cost_impact = [m for m in mismatches if float(m['units_per_case'] or 1) > 1]
    label_only = [m for m in mismatches if float(m['units_per_case'] or 1) <= 1]

    print(f"\n  COST IMPACT items (cf > 1):  {len(cost_impact)} vendor items, "
          f"{sum(m['item_count'] for m in cost_impact)} invoice items")
    print(f"  LABEL ONLY items (cf = 1):   {len(label_only)} vendor items, "
          f"{sum(m['item_count'] for m in label_only)} invoice items")

    if all_mismatches:
        other = [m for m in all_mismatches if m['parsed_uom'] != 'CS' or m['matched_uom'] != 'ea']
        if other:
            print(f"\n  OTHER UOM MISMATCHES (not fixed by this script):")
            for m in other:
                print(f"    {m['parsed_uom']:>8} → {m['matched_uom']:<6} "
                      f"{m['item_count']:>4} items across {m['vendor_items']} vendor items")


def main():
    parser = argparse.ArgumentParser(description='Fix GFS UOM mismatches')
    parser.add_argument('--apply', action='store_true', help='Apply fixes (default: dry run)')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        mismatches = find_mismatches(db)
        all_mismatches = find_all_uom_mismatches(db)

        print_report(mismatches, all_mismatches, args.apply)

        if args.apply and mismatches:
            confirm = input(f"\nApply fixes to {len(mismatches)} vendor items? [y/N]: ").strip().lower()
            if confirm == 'y':
                created, rematched, skipped = apply_fixes(db, mismatches)
                print(f"\nRESULTS:")
                print(f"  CS UOMs created:     {created}")
                print(f"  Already had CS UOM:  {skipped}")
                print(f"  Items re-matched:    {rematched}")
            else:
                print("Aborted.")
        elif args.apply and not mismatches:
            print("No mismatches to fix.")
    finally:
        db.close()


if __name__ == '__main__':
    main()
