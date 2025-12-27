"""
Location Cost Updater Service

Updates the Inventory system's MasterItemLocationCost table when invoices are processed.
Implements weighted average costing per location.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs

Cost Update Flow:
1. Invoice is mapped and approved
2. For each mapped item with a master_item_id:
   a. Get the vendor item's pack_to_primary_factor
   b. Calculate cost per primary unit
   c. Update MasterItemLocationCost with weighted average
   d. Record history entry
"""

import logging
import os
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)


class LocationCostUpdaterService:
    """
    Service for updating location-specific costs in Inventory system.

    Calculates weighted average costs and updates the MasterItemLocationCost table.
    """

    def __init__(self, db: Session):
        self.db = db
        self.inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )

    def _get_inventory_engine(self):
        """Get SQLAlchemy engine for Inventory database"""
        return create_engine(self.inventory_db_url)

    def update_costs_from_invoice(self, invoice_id: int) -> Dict:
        """
        Update location costs for all mapped inventory items in an invoice.

        Args:
            invoice_id: The Hub invoice ID

        Returns:
            Dict with statistics:
            - items_processed: Number of items with master_item_id
            - costs_updated: Number of location costs updated
            - costs_created: Number of new location cost records created
            - errors: List of any errors encountered
        """
        # Get invoice with location info
        invoice = self.db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {'error': 'Invoice not found'}

        location_id = invoice.location_id
        if not location_id:
            logger.warning(f"Invoice {invoice_id} has no location_id - cannot update location costs")
            return {'error': 'Invoice has no location_id', 'items_processed': 0}

        # Get all mapped items with inventory references
        items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == True,
            HubInvoiceItem.inventory_item_id.isnot(None)  # Has vendor item link
        ).all()

        stats = {
            'invoice_id': invoice_id,
            'location_id': location_id,
            'items_processed': 0,
            'costs_updated': 0,
            'costs_created': 0,
            'skipped_no_master_item': 0,
            'errors': []
        }

        for item in items:
            try:
                result = self._update_item_cost(item, invoice, location_id)
                if result.get('skipped'):
                    stats['skipped_no_master_item'] += 1
                elif result.get('created'):
                    stats['costs_created'] += 1
                    stats['items_processed'] += 1
                elif result.get('updated'):
                    stats['costs_updated'] += 1
                    stats['items_processed'] += 1
            except Exception as e:
                error_msg = f"Error updating cost for item {item.id}: {str(e)}"
                logger.error(error_msg)
                stats['errors'].append(error_msg)

        logger.info(f"Location cost update for invoice {invoice_id}: "
                   f"{stats['costs_updated']} updated, {stats['costs_created']} created, "
                   f"{stats['skipped_no_master_item']} skipped")

        return stats

    def _update_item_cost(
        self,
        item: HubInvoiceItem,
        invoice: HubInvoice,
        location_id: int
    ) -> Dict:
        """
        Update cost for a single invoice item.

        Calculates cost per primary unit and updates location cost using weighted average.

        Returns:
            Dict with 'updated', 'created', or 'skipped' flag
        """
        # Get the vendor item to find master_item_id and pack_to_primary_factor
        vendor_item = self.db.query(HubVendorItem).filter(
            HubVendorItem.id == item.inventory_item_id
        ).first()

        if not vendor_item:
            return {'skipped': True, 'reason': 'vendor_item_not_found'}

        master_item_id = vendor_item.inventory_master_item_id
        if not master_item_id:
            return {'skipped': True, 'reason': 'no_master_item_id'}

        # Calculate cost per primary unit
        pack_to_primary_factor = float(vendor_item.pack_to_primary_factor or 1.0)
        unit_price = float(item.unit_price or 0)

        if pack_to_primary_factor == 0:
            return {'skipped': True, 'reason': 'zero_pack_factor'}

        cost_per_primary = unit_price / pack_to_primary_factor

        # Calculate quantity in primary units
        quantity = float(item.quantity or 0)
        qty_in_primary = quantity * pack_to_primary_factor

        if qty_in_primary == 0:
            return {'skipped': True, 'reason': 'zero_quantity'}

        # Update location cost in Inventory database
        engine = self._get_inventory_engine()
        with engine.connect() as conn:
            # Check if location cost record exists
            existing = conn.execute(
                text("""
                    SELECT id, current_weighted_avg_cost, total_qty_on_hand
                    FROM master_item_location_costs
                    WHERE master_item_id = :master_item_id AND location_id = :location_id
                """),
                {"master_item_id": master_item_id, "location_id": location_id}
            ).fetchone()

            if existing:
                # Update with weighted average
                location_cost_id, old_cost, old_qty = existing
                old_cost = float(old_cost or 0)
                old_qty = float(old_qty or 0)

                # Weighted average formula
                old_value = old_cost * old_qty
                new_value = cost_per_primary * qty_in_primary
                total_qty = old_qty + qty_in_primary

                if total_qty > 0:
                    new_cost = (old_value + new_value) / total_qty
                else:
                    new_cost = cost_per_primary

                # Update the record
                conn.execute(
                    text("""
                        UPDATE master_item_location_costs
                        SET current_weighted_avg_cost = :new_cost,
                            total_qty_on_hand = :total_qty,
                            last_purchase_cost = :purchase_cost,
                            last_purchase_qty = :purchase_qty,
                            last_purchase_date = :purchase_date,
                            last_vendor_id = :vendor_id,
                            last_updated = NOW()
                        WHERE id = :id
                    """),
                    {
                        "id": location_cost_id,
                        "new_cost": new_cost,
                        "total_qty": total_qty,
                        "purchase_cost": cost_per_primary,
                        "purchase_qty": qty_in_primary,
                        "purchase_date": invoice.invoice_date,
                        "vendor_id": vendor_item.vendor_id
                    }
                )

                # Record history
                conn.execute(
                    text("""
                        INSERT INTO master_item_location_cost_history
                        (location_cost_id, master_item_id, location_id, event_type,
                         old_cost, old_qty, change_qty, change_cost_per_unit,
                         new_cost, new_qty, vendor_id, invoice_id, notes, created_at)
                        VALUES (:location_cost_id, :master_item_id, :location_id, 'purchase',
                                :old_cost, :old_qty, :change_qty, :change_cost,
                                :new_cost, :new_qty, :vendor_id, :invoice_id, :notes, NOW())
                    """),
                    {
                        "location_cost_id": location_cost_id,
                        "master_item_id": master_item_id,
                        "location_id": location_id,
                        "old_cost": old_cost,
                        "old_qty": old_qty,
                        "change_qty": qty_in_primary,
                        "change_cost": cost_per_primary,
                        "new_cost": new_cost,
                        "new_qty": total_qty,
                        "vendor_id": vendor_item.vendor_id,
                        "invoice_id": invoice.id,
                        "notes": f"Invoice {invoice.invoice_number}"
                    }
                )

                conn.commit()

                logger.debug(f"Updated location cost for item {master_item_id} at location {location_id}: "
                            f"${old_cost:.4f} → ${new_cost:.4f}")

                return {'updated': True, 'old_cost': old_cost, 'new_cost': new_cost}

            else:
                # Create new location cost record
                result = conn.execute(
                    text("""
                        INSERT INTO master_item_location_costs
                        (master_item_id, location_id, current_weighted_avg_cost, total_qty_on_hand,
                         last_purchase_cost, last_purchase_qty, last_purchase_date, last_vendor_id,
                         created_at, last_updated)
                        VALUES (:master_item_id, :location_id, :cost, :qty,
                                :cost, :qty, :purchase_date, :vendor_id,
                                NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        "master_item_id": master_item_id,
                        "location_id": location_id,
                        "cost": cost_per_primary,
                        "qty": qty_in_primary,
                        "purchase_date": invoice.invoice_date,
                        "vendor_id": vendor_item.vendor_id
                    }
                )
                location_cost_id = result.fetchone()[0]

                # Record initial history
                conn.execute(
                    text("""
                        INSERT INTO master_item_location_cost_history
                        (location_cost_id, master_item_id, location_id, event_type,
                         old_cost, old_qty, change_qty, change_cost_per_unit,
                         new_cost, new_qty, vendor_id, invoice_id, notes, created_at)
                        VALUES (:location_cost_id, :master_item_id, :location_id, 'initial',
                                NULL, NULL, :qty, :cost,
                                :cost, :qty, :vendor_id, :invoice_id, :notes, NOW())
                    """),
                    {
                        "location_cost_id": location_cost_id,
                        "master_item_id": master_item_id,
                        "location_id": location_id,
                        "qty": qty_in_primary,
                        "cost": cost_per_primary,
                        "vendor_id": vendor_item.vendor_id,
                        "invoice_id": invoice.id,
                        "notes": f"Initial from invoice {invoice.invoice_number}"
                    }
                )

                conn.commit()

                logger.debug(f"Created location cost for item {master_item_id} at location {location_id}: "
                            f"${cost_per_primary:.4f}")

                return {'created': True, 'new_cost': cost_per_primary}

    def get_location_cost(self, master_item_id: int, location_id: int) -> Optional[Dict]:
        """
        Get current cost for a master item at a specific location.

        Returns:
            Dict with cost info or None if not found
        """
        engine = self._get_inventory_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, current_weighted_avg_cost, total_qty_on_hand,
                           last_purchase_cost, last_purchase_date
                    FROM master_item_location_costs
                    WHERE master_item_id = :master_item_id AND location_id = :location_id
                """),
                {"master_item_id": master_item_id, "location_id": location_id}
            ).fetchone()

            if result:
                return {
                    'id': result[0],
                    'current_cost': float(result[1]) if result[1] else None,
                    'qty_on_hand': float(result[2]) if result[2] else 0,
                    'last_purchase_cost': float(result[3]) if result[3] else None,
                    'last_purchase_date': result[4].isoformat() if result[4] else None
                }

        return None

    def get_cost_history(
        self,
        master_item_id: int,
        location_id: int,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get cost change history for a master item at a location.

        Returns:
            List of history records
        """
        engine = self._get_inventory_engine()
        with engine.connect() as conn:
            results = conn.execute(
                text("""
                    SELECT event_type, old_cost, new_cost, change_qty, change_cost_per_unit,
                           invoice_id, notes, created_at
                    FROM master_item_location_cost_history
                    WHERE master_item_id = :master_item_id AND location_id = :location_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"master_item_id": master_item_id, "location_id": location_id, "limit": limit}
            ).fetchall()

            return [
                {
                    'event_type': r[0],
                    'old_cost': float(r[1]) if r[1] else None,
                    'new_cost': float(r[2]) if r[2] else None,
                    'change_qty': float(r[3]) if r[3] else None,
                    'change_cost_per_unit': float(r[4]) if r[4] else None,
                    'invoice_id': r[5],
                    'notes': r[6],
                    'created_at': r[7].isoformat() if r[7] else None
                }
                for r in results
            ]


def get_location_cost_updater(db: Session) -> LocationCostUpdaterService:
    """Get location cost updater service instance"""
    return LocationCostUpdaterService(db)
