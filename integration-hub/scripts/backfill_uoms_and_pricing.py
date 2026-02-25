#!/usr/bin/env python3
"""
Backfill default UOMs and pricing for vendor items.

1. Creates default EA UOM (cf=1) for items missing any vendor_item_uoms records
2. Populates case_cost/last_purchase_price from the most recent invoice line item
3. Sets matched_uom_id on invoice items mapped to items that now have UOMs

Usage:
    docker compose exec integration-hub python scripts/backfill_uoms_and_pricing.py [--dry-run]
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import text
from integration_hub.db.database import SessionLocal


def backfill(dry_run=False):
    db = SessionLocal()
    try:
        # --- Step 1: Create default EA UOM for items missing any UOM records ---
        items_without_uom = db.execute(text("""
            SELECT vi.id, vi.vendor_product_name, vi.purchase_unit_abbr
            FROM hub_vendor_items vi
            WHERE vi.is_active = true
              AND vi.id NOT IN (SELECT DISTINCT vendor_item_id FROM vendor_item_uoms)
            ORDER BY vi.id
        """)).fetchall()

        # Resolve EA UOM ID
        ea_row = db.execute(text(
            "SELECT id FROM units_of_measure WHERE abbreviation = 'ea' LIMIT 1"
        )).fetchone()
        ea_uom_id = ea_row[0] if ea_row else 1

        uom_created = 0
        for row in items_without_uom:
            item_id, name, purchase_abbr = row
            # Use purchase_unit_abbr to pick the right UOM if not EA
            uom_id = ea_uom_id
            cf = 1.0
            if purchase_abbr:
                abbr_upper = purchase_abbr.strip().upper()
                if abbr_upper in ('CS', 'CASE'):
                    # For case items, look up CS UOM
                    cs_row = db.execute(text(
                        "SELECT id FROM units_of_measure WHERE abbreviation = 'cs' LIMIT 1"
                    )).fetchone()
                    if cs_row:
                        uom_id = cs_row[0]
                elif abbr_upper in ('LB', 'POUND'):
                    lb_row = db.execute(text(
                        "SELECT id FROM units_of_measure WHERE abbreviation = 'lb' LIMIT 1"
                    )).fetchone()
                    if lb_row:
                        uom_id = lb_row[0]

            if dry_run:
                print(f"  [DRY RUN] Would create UOM for item {item_id} ({name}): uom_id={uom_id}, cf={cf}")
            else:
                db.execute(text("""
                    INSERT INTO vendor_item_uoms (vendor_item_id, uom_id, conversion_factor, is_default, is_active)
                    VALUES (:vid, :uom_id, :cf, true, true)
                    ON CONFLICT (vendor_item_id, uom_id) DO NOTHING
                """), {"vid": item_id, "uom_id": uom_id, "cf": cf})
                uom_created += 1

        print(f"\nStep 1 — Default UOMs: {uom_created} created ({len(items_without_uom)} items had none)")

        # --- Step 2: Populate pricing from most recent invoice data ---
        items_no_price = db.execute(text("""
            SELECT vi.id, vi.vendor_product_name, vi.units_per_case
            FROM hub_vendor_items vi
            WHERE vi.is_active = true
              AND vi.case_cost IS NULL
            ORDER BY vi.id
        """)).fetchall()

        pricing_updated = 0
        pricing_no_invoice = 0
        for row in items_no_price:
            item_id, name, units_per_case = row
            upc = float(units_per_case) if units_per_case else 1.0

            # Get most recent invoice item for this vendor item
            latest = db.execute(text("""
                SELECT hii.unit_price, hii.unit_of_measure, hi.invoice_date, hii.id as item_id
                FROM hub_invoice_items hii
                JOIN hub_invoices hi ON hi.id = hii.invoice_id
                WHERE hii.inventory_item_id = :vid
                  AND hii.unit_price IS NOT NULL
                ORDER BY hi.invoice_date DESC
                LIMIT 1
            """), {"vid": item_id}).fetchone()

            if not latest:
                pricing_no_invoice += 1
                continue

            unit_price = float(latest[0])
            invoice_uom = (latest[1] or '').strip().upper()
            invoice_date = latest[2]

            # case_cost = invoice unit_price (the price paid per purchase unit on the invoice)
            # The UOM conversion factor handles per-unit cost calculation separately
            case_cost = round(unit_price, 4)

            if dry_run:
                print(f"  [DRY RUN] Would update item {item_id} ({name}): case_cost={case_cost}, last_purchase_price={unit_price}")
            else:
                db.execute(text("""
                    UPDATE hub_vendor_items
                    SET case_cost = :case_cost,
                        last_purchase_price = :lpp,
                        price_updated_at = :pua
                    WHERE id = :vid
                """), {"case_cost": case_cost, "lpp": unit_price, "pua": invoice_date, "vid": item_id})

                # Also update the default UOM's last_cost
                db.execute(text("""
                    UPDATE vendor_item_uoms
                    SET last_cost = :cost, last_cost_date = :dt
                    WHERE vendor_item_id = :vid AND is_default = true
                """), {"cost": unit_price, "dt": invoice_date, "vid": item_id})

                pricing_updated += 1

        print(f"Step 2 — Pricing: {pricing_updated} updated from invoices, {pricing_no_invoice} had no invoice data ({len(items_no_price)} total missing)")

        # --- Step 3: Set matched_uom_id on invoice items that are mapped but have no matched_uom_id ---
        unmatched_invoice_items = db.execute(text("""
            SELECT hii.id, hii.inventory_item_id, hii.unit_of_measure
            FROM hub_invoice_items hii
            WHERE hii.inventory_item_id IS NOT NULL
              AND hii.matched_uom_id IS NULL
              AND hii.is_mapped = true
            ORDER BY hii.id
        """)).fetchall()

        uom_matched = 0
        for row in unmatched_invoice_items:
            hii_id, vendor_item_id, invoice_uom = row

            # Find the default UOM for this vendor item
            default_uom = db.execute(text("""
                SELECT viuom.id
                FROM vendor_item_uoms viuom
                WHERE viuom.vendor_item_id = :vid AND viuom.is_default = true AND viuom.is_active = true
                LIMIT 1
            """), {"vid": vendor_item_id}).fetchone()

            if not default_uom:
                continue

            if dry_run:
                print(f"  [DRY RUN] Would set matched_uom_id={default_uom[0]} on invoice item {hii_id}")
            else:
                db.execute(text("""
                    UPDATE hub_invoice_items SET matched_uom_id = :uom_id WHERE id = :hii_id
                """), {"uom_id": default_uom[0], "hii_id": hii_id})
                uom_matched += 1

        print(f"Step 3 — Invoice UOM matching: {uom_matched} invoice items got matched_uom_id ({len(unmatched_invoice_items)} were unmatched)")

        if not dry_run:
            db.commit()
            print("\nAll changes committed.")
        else:
            db.rollback()
            print("\n[DRY RUN] No changes made.")

    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN MODE ===\n")
    backfill(dry_run=dry_run)
