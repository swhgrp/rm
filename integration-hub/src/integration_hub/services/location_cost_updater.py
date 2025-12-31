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
from sqlalchemy import create_engine, text, or_
from sqlalchemy.orm import Session

from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.size_unit import SizeUnit

logger = logging.getLogger(__name__)


def calculate_unit_cost_from_vendor_item(vi: HubVendorItem) -> Optional[float]:
    """
    Calculate unit cost from a vendor item's pricing fields.

    For weight-based items (measure_type='weight'):
        unit_cost = case_cost / (units_per_case × size_quantity)
        Example: $138.13 case / (1 unit × 10 lb) = $13.81/lb

    For count/volume items:
        unit_cost = case_cost / units_per_case
        Example: $36 case / 12 bottles = $3.00/bottle

    Returns:
        float unit cost or None if pricing is unavailable
    """
    if not vi.case_cost:
        return float(vi.unit_cost) if vi.unit_cost else None

    units_per_case = float(vi.units_per_case or 1)
    if units_per_case == 0:
        return None

    # Check if this is a weight-based item
    is_weight_item = False
    if vi.size_unit and vi.size_unit.measure_type == 'weight':
        is_weight_item = True

    if is_weight_item and vi.size_quantity and float(vi.size_quantity) > 0:
        # Weight items: divide by total weight (units × size)
        # Example: Grouper 10lb case = $138.13 / (1 × 10) = $13.81/lb
        total_weight = units_per_case * float(vi.size_quantity)
        unit_cost = float(vi.case_cost) / total_weight
    else:
        # Count/volume items: divide by units per case
        # Example: Wine 12-bottle case = $36 / 12 = $3.00/bottle
        unit_cost = float(vi.case_cost) / units_per_case

    return unit_cost


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

        # Calculate cost per primary unit (lb for weight, bottle/each for count/volume)
        # Use units_per_case (Backbar-style) or fall back to deprecated pack_to_primary_factor
        units_per_case = float(vendor_item.units_per_case or vendor_item.pack_to_primary_factor or 1.0)
        unit_price = float(item.unit_price or 0)  # This is typically the CASE price from invoice

        if units_per_case == 0:
            return {'skipped': True, 'reason': 'zero_units_per_case'}

        # Check if this is a weight-based item
        is_weight_item = (vendor_item.size_unit and
                          vendor_item.size_unit.measure_type == 'weight' and
                          vendor_item.size_quantity and
                          float(vendor_item.size_quantity) > 0)

        if is_weight_item:
            # Weight items: divide by total weight (units × size)
            # Example: Grouper 10lb case @ $138.13 = $138.13 / (1 × 10) = $13.81/lb
            # Example: Cheese 4×5lb bags @ $47.54 = $47.54 / (4 × 5) = $2.38/lb
            total_weight = units_per_case * float(vendor_item.size_quantity)
            cost_per_primary = unit_price / total_weight
            qty_in_primary = float(item.quantity or 0) * total_weight
        else:
            # Count/volume items: divide by units per case
            # Example: Wine 12-bottle case @ $36 = $36 / 12 = $3.00/bottle
            cost_per_primary = unit_price / units_per_case
            qty_in_primary = float(item.quantity or 0) * units_per_case

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


    def seed_location_costs_from_vendor_items(self, master_item_id: Optional[int] = None) -> Dict:
        """
        Seed location costs from vendor item pricing for items that don't have invoice-based costs.

        This populates MasterItemLocationCost records using the vendor item's unit_cost
        (calculated from case_cost / units_per_case) as a default price for all locations.

        Args:
            master_item_id: Optional - seed for a specific master item only

        Returns:
            Dict with statistics about records created/updated
        """
        stats = {
            'master_items_processed': 0,
            'locations_seeded': 0,
            'locations_skipped_existing': 0,
            'errors': []
        }

        # Get all mapped vendor items with pricing
        query = self.db.query(HubVendorItem).filter(
            HubVendorItem.inventory_master_item_id.isnot(None),
            HubVendorItem.is_active == True
        )

        if master_item_id:
            query = query.filter(HubVendorItem.inventory_master_item_id == master_item_id)

        # Group by master_item_id to get best price per master item
        vendor_items = query.all()

        # Build map of master_item_id -> best unit_cost
        master_item_costs = {}
        for vi in vendor_items:
            # Calculate unit cost using helper that handles weight items correctly
            unit_cost = calculate_unit_cost_from_vendor_item(vi)
            if unit_cost is None:
                continue

            mid = vi.inventory_master_item_id
            # Keep the lowest cost (or first if not set)
            if mid not in master_item_costs or unit_cost < master_item_costs[mid]['cost']:
                master_item_costs[mid] = {
                    'cost': unit_cost,
                    'vendor_id': vi.vendor_id,
                    'vendor_item_id': vi.id
                }

        if not master_item_costs:
            return stats

        # Get all locations from Inventory
        engine = self._get_inventory_engine()
        with engine.connect() as conn:
            locations = conn.execute(
                text("SELECT id FROM locations WHERE is_active = true")
            ).fetchall()
            location_ids = [loc[0] for loc in locations]

            for master_item_id, cost_info in master_item_costs.items():
                stats['master_items_processed'] += 1
                unit_cost = cost_info['cost']
                vendor_id = cost_info['vendor_id']

                for location_id in location_ids:
                    try:
                        # Check if location cost already exists
                        existing = conn.execute(
                            text("""
                                SELECT id FROM master_item_location_costs
                                WHERE master_item_id = :master_item_id AND location_id = :location_id
                            """),
                            {"master_item_id": master_item_id, "location_id": location_id}
                        ).fetchone()

                        if existing:
                            stats['locations_skipped_existing'] += 1
                            continue

                        # Create new location cost record with vendor item pricing
                        conn.execute(
                            text("""
                                INSERT INTO master_item_location_costs
                                (master_item_id, location_id, current_weighted_avg_cost, total_qty_on_hand,
                                 last_vendor_id, created_at, last_updated)
                                VALUES (:master_item_id, :location_id, :cost, 0,
                                        :vendor_id, NOW(), NOW())
                            """),
                            {
                                "master_item_id": master_item_id,
                                "location_id": location_id,
                                "cost": unit_cost,
                                "vendor_id": vendor_id
                            }
                        )
                        stats['locations_seeded'] += 1

                    except Exception as e:
                        stats['errors'].append(f"Error seeding {master_item_id} at {location_id}: {str(e)}")

            conn.commit()

        logger.info(f"Seeded location costs: {stats['locations_seeded']} created, "
                   f"{stats['locations_skipped_existing']} skipped (existing)")

        return stats

    def fix_seeded_location_costs(self, master_item_id: Optional[int] = None) -> Dict:
        """
        Fix location costs that were seeded with incorrect values (case prices instead of unit prices).
        Only updates records that have no last_purchase_cost (meaning they were seeded, not from invoices).
        """
        stats = {
            'master_items_checked': 0,
            'locations_updated': 0,
            'locations_already_correct': 0,
            'items_fixed': [],
            'errors': []
        }

        # Get vendor items with master item mapping and pricing
        # Note: unit_cost is a property, so we filter on case_cost column only
        query = self.db.query(HubVendorItem).filter(
            HubVendorItem.inventory_master_item_id.isnot(None),
            HubVendorItem.case_cost.isnot(None)
        )

        if master_item_id:
            query = query.filter(HubVendorItem.inventory_master_item_id == master_item_id)

        vendor_items = query.all()

        # Build map of master_item_id -> correct unit_cost
        master_item_costs = {}
        for vi in vendor_items:
            if vi.inventory_master_item_id not in master_item_costs:
                # Calculate correct unit cost using helper that handles weight items
                unit_cost = calculate_unit_cost_from_vendor_item(vi)
                if unit_cost is None:
                    continue

                # For weight items, include size info in description
                size_info = ""
                if vi.size_unit and vi.size_unit.measure_type == 'weight' and vi.size_quantity:
                    size_info = f" ({vi.size_quantity}{vi.size_unit.symbol})"

                master_item_costs[vi.inventory_master_item_id] = {
                    'cost': round(unit_cost, 4),
                    'case_cost': float(vi.case_cost) if vi.case_cost else None,
                    'units_per_case': float(vi.units_per_case) if vi.units_per_case else None,
                    'size_quantity': float(vi.size_quantity) if vi.size_quantity else None,
                    'is_weight_item': vi.size_unit and vi.size_unit.measure_type == 'weight',
                    'description': (vi.vendor_product_name[:40] if vi.vendor_product_name else 'Unknown') + size_info
                }

        if not master_item_costs:
            logger.warning("No vendor items found with valid pricing for fixing location costs")
            return stats

        logger.info(f"Fixing location costs for {len(master_item_costs)} master items")

        # Connect to inventory database
        inventory_db_url = os.getenv(
            "INVENTORY_DATABASE_URL",
            "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
        )
        engine = create_engine(inventory_db_url)

        with engine.connect() as conn:
            for master_item_id, cost_info in master_item_costs.items():
                stats['master_items_checked'] += 1
                correct_cost = cost_info['cost']

                try:
                    # Update seeded location costs that have wrong values
                    # Only update records without last_purchase_cost (not from invoices)
                    result = conn.execute(
                        text("""
                            UPDATE master_item_location_costs
                            SET current_weighted_avg_cost = :correct_cost,
                                last_updated = NOW()
                            WHERE master_item_id = :master_item_id
                              AND last_purchase_cost IS NULL
                              AND ABS(current_weighted_avg_cost - :correct_cost) > 0.01
                        """),
                        {"master_item_id": master_item_id, "correct_cost": correct_cost}
                    )

                    if result.rowcount > 0:
                        stats['locations_updated'] += result.rowcount
                        stats['items_fixed'].append({
                            'master_item_id': master_item_id,
                            'description': cost_info['description'],
                            'case_cost': cost_info['case_cost'],
                            'units_per_case': cost_info['units_per_case'],
                            'correct_unit_cost': correct_cost,
                            'locations_fixed': result.rowcount
                        })
                    else:
                        # Check how many are already correct
                        existing = conn.execute(
                            text("""
                                SELECT COUNT(*) FROM master_item_location_costs
                                WHERE master_item_id = :master_item_id
                                  AND last_purchase_cost IS NULL
                            """),
                            {"master_item_id": master_item_id}
                        ).scalar()
                        if existing:
                            stats['locations_already_correct'] += existing

                except Exception as e:
                    stats['errors'].append(f"Error fixing {master_item_id}: {str(e)}")

            conn.commit()

        logger.info(f"Fixed location costs: {stats['locations_updated']} updated, "
                   f"{stats['locations_already_correct']} already correct")

        return stats


def get_location_cost_updater(db: Session) -> LocationCostUpdaterService:
    """Get location cost updater service instance"""
    return LocationCostUpdaterService(db)
