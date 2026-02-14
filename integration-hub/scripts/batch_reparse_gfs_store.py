#!/usr/bin/env python3
"""
Batch re-parse GFS Store invoices with updated vendor parsing rules.

GFS has two invoice formats:
1. Delivery invoices (903x 10-digit numbers) - already parsed correctly
2. Store invoices (864x, 945x, 955x numbers) - were parsed with wrong column mappings

This script re-parses all store-format invoices that haven't been sent yet.
"""
import sys
import os
import time
import logging

# Add the src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from integration_hub.db.database import SessionLocal
from integration_hub.models.invoice import HubInvoice, HubInvoiceItem
from integration_hub.services.invoice_parser import get_invoice_parser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# GFS vendor_id
GFS_VENDOR_ID = 5

# Delay between API calls (seconds) to avoid rate limiting
DELAY_BETWEEN_PARSES = 5


def get_store_invoice_ids(db):
    """Find all GFS store-format invoices that need re-parsing."""
    invoices = db.query(HubInvoice.id, HubInvoice.invoice_number, HubInvoice.vendor_name, HubInvoice.total_amount).filter(
        HubInvoice.vendor_id == GFS_VENDOR_ID,
        HubInvoice.status.notin_(['sent', 'statement', 'duplicate']),
        HubInvoice.pdf_path.isnot(None),
        # Store invoices: either labeled "Store" or have store-pattern invoice numbers
        (
            HubInvoice.vendor_name.ilike('%store%') |
            HubInvoice.invoice_number.op('~')('^864') |
            HubInvoice.invoice_number.op('~')('^945') |
            HubInvoice.invoice_number.op('~')('^955')
        )
    ).order_by(HubInvoice.id).all()
    return invoices


def main():
    db = SessionLocal()
    try:
        invoices = get_store_invoice_ids(db)
        logger.info(f"Found {len(invoices)} GFS store invoices to re-parse")

        if not invoices:
            logger.info("No invoices to re-parse. Exiting.")
            return

        # Show what we'll re-parse
        for inv in invoices:
            logger.info(f"  ID {inv.id}: #{inv.invoice_number} - {inv.vendor_name} - ${inv.total_amount}")

        print(f"\nAbout to re-parse {len(invoices)} invoices. Continue? [y/N] ", end='', flush=True)
        response = input().strip().lower()
        if response != 'y':
            logger.info("Aborted by user.")
            return

        parser = get_invoice_parser()
        success_count = 0
        error_count = 0

        for i, inv in enumerate(invoices, 1):
            logger.info(f"[{i}/{len(invoices)}] Re-parsing invoice {inv.id} (#{inv.invoice_number})...")

            try:
                result = parser.reparse_with_vendor_rules(inv.id, db)

                if result.get('success'):
                    item_count = result.get('items_count', '?')
                    logger.info(f"  SUCCESS - {item_count} items parsed")
                    success_count += 1
                else:
                    logger.error(f"  FAILED - {result.get('message', 'Unknown error')}")
                    error_count += 1
            except Exception as e:
                logger.error(f"  ERROR - {str(e)}")
                error_count += 1

            # Delay between parses to avoid rate limiting
            if i < len(invoices):
                time.sleep(DELAY_BETWEEN_PARSES)

        logger.info(f"\nDone! {success_count} succeeded, {error_count} failed out of {len(invoices)} total.")

    finally:
        db.close()


if __name__ == '__main__':
    main()
