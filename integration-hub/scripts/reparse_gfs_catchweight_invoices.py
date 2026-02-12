"""
Re-parse all GFS invoices that contain catch-weight items parsed incorrectly.

These invoices have items mapped to vendor items with purchase_unit_abbr='lb'
but were parsed with unit_of_measure='CS'. The updated parsing rules now
detect catch-weight items via the "WEIGHT:" pattern on GFS invoices.

This script:
1. Finds all affected GFS invoices
2. Re-parses each one using vendor-specific rules (with catch-weight detection)
3. Auto-mapper runs automatically after each parse
4. Reports results
"""
import sys
import time
import logging

sys.path.insert(0, "/app/src")

from integration_hub.db.database import SessionLocal
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.services.invoice_parser import get_invoice_parser
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def get_affected_invoice_ids(db):
    """Find GFS invoices with catch-weight items parsed as CS."""
    results = db.execute(text("""
        SELECT DISTINCT i.id, i.invoice_number, i.invoice_date, i.status
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        JOIN hub_vendor_items vi ON ii.inventory_item_id = vi.id
        WHERE i.vendor_id = 5
        AND vi.purchase_unit_abbr = 'lb'
        AND ii.unit_of_measure IN ('CS', 'cs', 'Case')
        ORDER BY i.invoice_date ASC
    """)).fetchall()
    return results


def main():
    db = SessionLocal()
    try:
        invoices = get_affected_invoice_ids(db)
        total = len(invoices)
        print(f"\n{'='*70}")
        print(f"GFS Catch-Weight Invoice Re-Parse")
        print(f"Found {total} invoices to re-parse")
        print(f"{'='*70}\n")

        parser = get_invoice_parser()

        success_count = 0
        error_count = 0
        catchweight_found = 0

        for i, inv in enumerate(invoices, 1):
            inv_id, inv_num, inv_date, status = inv
            print(f"[{i}/{total}] Invoice #{inv_num} ({inv_date}) status={status} ...")

            try:
                # Use reparse_with_vendor_rules which includes the updated catch-weight rules
                result = parser.reparse_with_vendor_rules(inv_id, db)

                if result.get("success"):
                    # Check if any items were parsed as LB (catch-weight detected)
                    lb_items = db.execute(text("""
                        SELECT COUNT(*) FROM hub_invoice_items
                        WHERE invoice_id = :inv_id AND unit_of_measure IN ('LB', 'lb')
                    """), {"inv_id": inv_id}).scalar()

                    total_items = result.get("items_parsed", 0)
                    mapped = result.get("items_mapped", 0)

                    status_str = f"OK: {total_items} items, {mapped} mapped"
                    if lb_items > 0:
                        status_str += f", {lb_items} catch-weight (LB)"
                        catchweight_found += lb_items
                    print(f"  -> {status_str}")
                    success_count += 1
                else:
                    print(f"  -> FAILED: {result.get('message', 'Unknown error')}")
                    error_count += 1

            except Exception as e:
                print(f"  -> ERROR: {str(e)}")
                error_count += 1
                # Continue with next invoice
                db.rollback()

            # Small delay to avoid overwhelming the OpenAI API
            if i < total:
                time.sleep(2)

        print(f"\n{'='*70}")
        print(f"COMPLETE")
        print(f"  Success: {success_count}/{total}")
        print(f"  Errors:  {error_count}/{total}")
        print(f"  Catch-weight items found: {catchweight_found}")
        print(f"{'='*70}\n")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
