"""
Price Tracker Service

Tracks price changes for vendor items when invoices are processed.
Updates vendor item prices and records history.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, List
from datetime import datetime
from sqlalchemy.orm import Session

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.price_history import PriceHistory

logger = logging.getLogger(__name__)


class PriceTrackerService:
    """Service for tracking vendor item price changes"""

    def __init__(self, db: Session):
        self.db = db

    def update_price_from_invoice_item(
        self,
        vendor_item: HubVendorItem,
        invoice_item: HubInvoiceItem,
        invoice: HubInvoice
    ) -> Optional[PriceHistory]:
        """
        Update vendor item price if different from invoice price.
        Records price history if there's a change.

        Args:
            vendor_item: The Hub vendor item to update
            invoice_item: The invoice line item with the new price
            invoice: The parent invoice

        Returns:
            PriceHistory record if price changed, None otherwise
        """
        if not invoice_item.unit_price:
            return None

        new_price = Decimal(str(invoice_item.unit_price))
        old_price = vendor_item.unit_price

        # Skip if no change (or first time setting price)
        if old_price is not None and old_price == new_price:
            return None

        # Calculate change
        price_change = None
        price_change_pct = None
        if old_price is not None and old_price != 0:
            price_change = new_price - old_price
            price_change_pct = (price_change / old_price) * 100

        # Create history record
        history = PriceHistory(
            vendor_item_id=vendor_item.id,
            old_price=old_price,
            new_price=new_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            quantity=invoice_item.quantity
        )
        self.db.add(history)

        # Update vendor item
        vendor_item.last_price = old_price
        vendor_item.unit_price = new_price
        vendor_item.price_updated_at = get_now()

        logger.info(
            f"Price updated for vendor item {vendor_item.id}: "
            f"${old_price or 0:.2f} -> ${new_price:.2f} "
            f"(invoice {invoice.invoice_number})"
        )

        return history

    def process_invoice_prices(self, invoice_id: int) -> Dict:
        """
        Process all mapped items in an invoice and update prices.

        Args:
            invoice_id: The invoice ID to process

        Returns:
            Dict with statistics
        """
        invoice = self.db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {'error': 'Invoice not found'}

        # Get all mapped items with vendor item links
        items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == True,
            HubInvoiceItem.inventory_item_id.isnot(None)
        ).all()

        stats = {
            'total_items': len(items),
            'prices_updated': 0,
            'prices_unchanged': 0,
            'no_price': 0,
            'changes': []
        }

        for item in items:
            if not item.unit_price:
                stats['no_price'] += 1
                continue

            # Get the vendor item
            vendor_item = self.db.query(HubVendorItem).filter(
                HubVendorItem.id == item.inventory_item_id
            ).first()

            if not vendor_item:
                continue

            history = self.update_price_from_invoice_item(vendor_item, item, invoice)

            if history:
                stats['prices_updated'] += 1
                stats['changes'].append({
                    'vendor_item_id': vendor_item.id,
                    'product_name': vendor_item.vendor_product_name[:50],
                    'old_price': float(history.old_price) if history.old_price else None,
                    'new_price': float(history.new_price),
                    'change_pct': float(history.price_change_pct) if history.price_change_pct else None
                })
            else:
                stats['prices_unchanged'] += 1

        self.db.commit()

        logger.info(f"Price tracking for invoice {invoice_id}: {stats['prices_updated']} updated")
        return stats

    def get_price_history(
        self,
        vendor_item_id: int,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get price history for a vendor item.

        Args:
            vendor_item_id: The vendor item ID
            limit: Maximum records to return

        Returns:
            List of price history records
        """
        history = self.db.query(PriceHistory).filter(
            PriceHistory.vendor_item_id == vendor_item_id
        ).order_by(
            PriceHistory.recorded_at.desc()
        ).limit(limit).all()

        return [
            {
                'id': h.id,
                'old_price': float(h.old_price) if h.old_price else None,
                'new_price': float(h.new_price),
                'change': float(h.price_change) if h.price_change else None,
                'change_pct': float(h.price_change_pct) if h.price_change_pct else None,
                'invoice_number': h.invoice_number,
                'invoice_date': h.invoice_date.isoformat() if h.invoice_date else None,
                'recorded_at': h.recorded_at.isoformat() if h.recorded_at else None
            }
            for h in history
        ]

    def get_significant_price_changes(
        self,
        min_change_pct: float = 5.0,
        days: int = 30,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get significant price changes across all vendor items.

        Args:
            min_change_pct: Minimum percentage change to include
            days: Look back period in days
            limit: Maximum records to return

        Returns:
            List of significant price changes with vendor item details
        """
        from datetime import timedelta
        from sqlalchemy import func, and_

        cutoff = get_now() - timedelta(days=days)

        history = self.db.query(PriceHistory).join(
            HubVendorItem
        ).filter(
            and_(
                PriceHistory.recorded_at >= cutoff,
                func.abs(PriceHistory.price_change_pct) >= min_change_pct
            )
        ).order_by(
            func.abs(PriceHistory.price_change_pct).desc()
        ).limit(limit).all()

        return [
            {
                'vendor_item_id': h.vendor_item_id,
                'product_name': h.vendor_item.vendor_product_name if h.vendor_item else None,
                'vendor_name': h.vendor_item.vendor.name if h.vendor_item and h.vendor_item.vendor else None,
                'old_price': float(h.old_price) if h.old_price else None,
                'new_price': float(h.new_price),
                'change': float(h.price_change) if h.price_change else None,
                'change_pct': float(h.price_change_pct) if h.price_change_pct else None,
                'invoice_number': h.invoice_number,
                'recorded_at': h.recorded_at.isoformat() if h.recorded_at else None
            }
            for h in history
        ]


def get_price_tracker(db: Session) -> PriceTrackerService:
    """Get price tracker service instance"""
    return PriceTrackerService(db)
