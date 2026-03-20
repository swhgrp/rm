"""
Vendor Item Review Workflow Service

Handles the review workflow for vendor items:
1. New items are created with status='needs_review'
2. Items can be approved (status='active') or rejected (status='inactive')
3. Cross-location items can be cloned to new locations

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from integration_hub.models.hub_vendor_item import HubVendorItem, VendorItemStatus
from integration_hub.models.vendor import Vendor
logger = logging.getLogger(__name__)


def check_uom_completeness(item: HubVendorItem) -> Dict:
    """
    Check if a vendor item has complete UOM (Unit of Measure) data.

    Required fields for complete UOM:
    - size_quantity: > 0
    - size_unit_id: set (valid reference)
    - container_id: set (valid reference)
    - units_per_case: > 0

    Returns:
        Dict with:
        - is_complete: bool
        - missing_fields: list of field names that are missing/invalid
    """
    missing_fields = []

    if not item.size_quantity or float(item.size_quantity) <= 0:
        missing_fields.append('size_quantity')

    if not item.size_unit_id:
        missing_fields.append('size_unit_id')

    if not item.container_id:
        missing_fields.append('container_id')

    if not item.units_per_case or item.units_per_case <= 0:
        missing_fields.append('units_per_case')

    return {
        'is_complete': len(missing_fields) == 0,
        'missing_fields': missing_fields
    }


class VendorItemReviewService:
    """
    Service for managing vendor item review workflow.

    New items discovered during invoice processing are created with needs_review status.
    Users can then approve, reject, or modify items before they're used in costing.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_items_needing_review(
        self,
        vendor_id: int = None,
        location_id: int = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get all vendor items that need review.

        Args:
            vendor_id: Optional filter by vendor
            location_id: Optional filter by location
            limit: Maximum items to return

        Returns:
            List of vendor items needing review
        """
        query = self.db.query(HubVendorItem).filter(
            HubVendorItem.status == VendorItemStatus.needs_review
        )

        if vendor_id:
            query = query.filter(HubVendorItem.vendor_id == vendor_id)
        if location_id:
            query = query.filter(HubVendorItem.location_id == location_id)

        items = query.order_by(HubVendorItem.created_at.desc()).limit(limit).all()

        return [self._item_to_dict(item) for item in items]

    def get_review_stats(self) -> Dict:
        """
        Get statistics about items in review workflow.

        Returns:
            Dict with counts by status and location
        """
        from sqlalchemy import func

        # Count by status
        status_counts = self.db.query(
            HubVendorItem.status,
            func.count(HubVendorItem.id)
        ).group_by(HubVendorItem.status).all()

        # Count needs_review by location
        location_counts = self.db.query(
            HubVendorItem.location_id,
            func.count(HubVendorItem.id)
        ).filter(
            HubVendorItem.status == VendorItemStatus.needs_review
        ).group_by(HubVendorItem.location_id).all()

        # Count needs_review by vendor
        vendor_counts = self.db.query(
            HubVendorItem.vendor_id,
            Vendor.name,
            func.count(HubVendorItem.id)
        ).join(Vendor).filter(
            HubVendorItem.status == VendorItemStatus.needs_review
        ).group_by(HubVendorItem.vendor_id, Vendor.name).all()

        return {
            'by_status': {s.value if s else 'none': c for s, c in status_counts},
            'needs_review_by_location': {loc: c for loc, c in location_counts},
            'needs_review_by_vendor': [
                {'vendor_id': vid, 'vendor_name': vname, 'count': c}
                for vid, vname, c in vendor_counts
            ]
        }

    def approve_item(self, item_id: int, approved_by: str = None) -> Dict:
        """
        Approve a vendor item for use in costing.

        Changes status from needs_review to active.
        Requires complete UOM data (size_quantity, size_unit_id, container_id, units_per_case).

        Args:
            item_id: The vendor item ID
            approved_by: Username of person approving

        Returns:
            Updated item dict, or error dict if validation fails
        """
        item = self.db.query(HubVendorItem).filter(HubVendorItem.id == item_id).first()
        if not item:
            return {'error': 'Vendor item not found'}

        if item.status != VendorItemStatus.needs_review:
            return {'error': f'Item is not in needs_review status (current: {item.status.value})'}

        # Validate UOM completeness before approval
        uom_check = check_uom_completeness(item)
        if not uom_check['is_complete']:
            missing = ', '.join(uom_check['missing_fields'])
            return {
                'error': f'Cannot approve: Missing required UOM fields ({missing})',
                'missing_fields': uom_check['missing_fields'],
                'uom_incomplete': True
            }

        item.status = VendorItemStatus.active
        item.updated_at = get_now()
        if approved_by:
            item.notes = f"{item.notes or ''}\nApproved by {approved_by} at {get_now().isoformat()}".strip()

        self.db.commit()

        logger.info(f"Vendor item {item_id} approved by {approved_by}")
        return self._item_to_dict(item)

    def reject_item(self, item_id: int, reason: str = None, rejected_by: str = None) -> Dict:
        """
        Reject a vendor item, marking it inactive.

        Args:
            item_id: The vendor item ID
            reason: Optional rejection reason
            rejected_by: Username of person rejecting

        Returns:
            Updated item dict
        """
        item = self.db.query(HubVendorItem).filter(HubVendorItem.id == item_id).first()
        if not item:
            return {'error': 'Vendor item not found'}

        item.status = VendorItemStatus.inactive
        item.updated_at = get_now()
        note = f"Rejected by {rejected_by or 'unknown'} at {get_now().isoformat()}"
        if reason:
            note += f": {reason}"
        item.notes = f"{item.notes or ''}\n{note}".strip()

        self.db.commit()

        logger.info(f"Vendor item {item_id} rejected by {rejected_by}: {reason}")
        return self._item_to_dict(item)

    def bulk_approve(self, item_ids: List[int], approved_by: str = None) -> Dict:
        """
        Approve multiple vendor items at once.

        Args:
            item_ids: List of vendor item IDs
            approved_by: Username of person approving

        Returns:
            Dict with success/fail counts
        """
        approved = 0
        failed = 0
        errors = []

        for item_id in item_ids:
            result = self.approve_item(item_id, approved_by)
            if result.get('error'):
                failed += 1
                errors.append(f"Item {item_id}: {result['error']}")
            else:
                approved += 1

        return {
            'approved': approved,
            'failed': failed,
            'errors': errors
        }

    def clone_to_location(
        self,
        source_item_id: int,
        target_location_id: int,
        price: float = None
    ) -> Dict:
        """
        Clone a vendor item to a new location.

        Used when an item is discovered via cross-location matching.
        Creates a new vendor item at the target location with needs_review status.

        Args:
            source_item_id: Source vendor item to clone
            target_location_id: Target location ID
            price: Optional price for the new location (defaults to source price)

        Returns:
            New vendor item dict
        """
        source = self.db.query(HubVendorItem).filter(HubVendorItem.id == source_item_id).first()
        if not source:
            return {'error': 'Source vendor item not found'}

        # Check if already exists at target location
        existing = self.db.query(HubVendorItem).filter(
            and_(
                HubVendorItem.vendor_id == source.vendor_id,
                HubVendorItem.vendor_sku == source.vendor_sku,
                HubVendorItem.location_id == target_location_id
            )
        ).first()

        if existing:
            return {
                'error': 'Item already exists at target location',
                'existing_item_id': existing.id
            }

        # Clone the item
        new_item = HubVendorItem(
            vendor_id=source.vendor_id,
            location_id=target_location_id,
            inventory_master_item_id=source.inventory_master_item_id,
            inventory_master_item_name=source.inventory_master_item_name,
            vendor_sku=source.vendor_sku,
            vendor_product_name=source.vendor_product_name,
            vendor_description=source.vendor_description,
            purchase_unit_id=source.purchase_unit_id,
            purchase_unit_name=source.purchase_unit_name,
            purchase_unit_abbr=source.purchase_unit_abbr,
            pack_size=source.pack_size,
            pack_to_primary_factor=source.pack_to_primary_factor,
            category=source.category,
            gl_asset_account=source.gl_asset_account,
            gl_cogs_account=source.gl_cogs_account,
            gl_waste_account=source.gl_waste_account,
            status=VendorItemStatus.needs_review,
            last_purchase_price=price if price else source.last_purchase_price,
            notes=f"Cloned from item {source.id} (location {source.location_id})"
        )

        self.db.add(new_item)
        self.db.commit()

        logger.info(f"Cloned vendor item {source_item_id} to location {target_location_id} -> new item {new_item.id}")

        return self._item_to_dict(new_item)

    def create_from_invoice_item(
        self,
        vendor_id: int,
        location_id: int,
        item_code: str,
        item_description: str,
        unit_price: float = None
    ) -> Dict:
        """
        Create a new vendor item from an unmapped invoice item.

        Creates with needs_review status for later approval.

        Args:
            vendor_id: Hub vendor ID
            location_id: Location ID
            item_code: Vendor's item code/SKU
            item_description: Product description from invoice
            unit_price: Price from invoice

        Returns:
            New vendor item dict
        """
        # Check if already exists (same vendor + SKU, any location, any status)
        # Includes inactive items to prevent re-creating intentionally deactivated items
        existing = self.db.query(HubVendorItem).filter(
            and_(
                HubVendorItem.vendor_id == vendor_id,
                HubVendorItem.vendor_sku == item_code,
            )
        ).first()

        if existing:
            return {
                'exists': True,
                'item': self._item_to_dict(existing)
            }

        # Create new item
        new_item = HubVendorItem(
            vendor_id=vendor_id,
            location_id=location_id,
            vendor_sku=item_code,
            vendor_product_name=item_description,
            status=VendorItemStatus.needs_review,
            last_purchase_price=unit_price,
            case_cost=unit_price,  # Default: 1 unit = 1 case until configured
            units_per_case=1,
            pack_to_primary_factor=1.0,  # Default, needs review
            price_updated_at=get_now() if unit_price else None,
            notes="Auto-created from invoice. Needs master item mapping and unit configuration."
        )

        self.db.add(new_item)
        self.db.commit()

        logger.info(f"Created new vendor item from invoice: vendor={vendor_id}, location={location_id}, sku={item_code}")

        # Sync to Inventory (non-blocking — log but don't fail)
        try:
            vendor = self.db.query(Vendor).filter(Vendor.id == vendor_id).first()
            if vendor and vendor.inventory_vendor_id:
                import asyncio
                from integration_hub.api.vendor_items import sync_vendor_item_to_inventory
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(sync_vendor_item_to_inventory(new_item, vendor, action="sync"))
                else:
                    sync_result = asyncio.run(sync_vendor_item_to_inventory(new_item, vendor, action="sync"))
                    if sync_result:
                        new_item.synced_to_inventory = True
                        if sync_result.get("inventory_vendor_item_id"):
                            new_item.inventory_vendor_item_id = sync_result["inventory_vendor_item_id"]
                        self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync new vendor item {new_item.id} to Inventory: {e}")

        return {
            'created': True,
            'item': self._item_to_dict(new_item)
        }

    def _item_to_dict(self, item: HubVendorItem) -> Dict:
        """Convert vendor item to dict"""
        uom_check = check_uom_completeness(item)
        return {
            'id': item.id,
            'vendor_id': item.vendor_id,
            'vendor_name': item.vendor.name if item.vendor else None,
            'location_id': item.location_id,
            'vendor_sku': item.vendor_sku,
            'vendor_product_name': item.vendor_product_name,
            'inventory_master_item_id': item.inventory_master_item_id,
            'inventory_master_item_name': item.inventory_master_item_name,
            'category': item.category,
            'purchase_unit_name': item.purchase_unit_name,
            'pack_size': item.pack_size,
            'pack_to_primary_factor': float(item.pack_to_primary_factor) if item.pack_to_primary_factor else 1.0,
            'last_purchase_price': float(item.last_purchase_price) if item.last_purchase_price else None,
            'cost_per_primary_unit': item.cost_per_primary_unit,
            'status': item.status.value if item.status else 'active',
            'gl_asset_account': item.gl_asset_account,
            'gl_cogs_account': item.gl_cogs_account,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'updated_at': item.updated_at.isoformat() if item.updated_at else None,
            'notes': item.notes,
            # UOM completeness info
            'uom_complete': uom_check['is_complete'],
            'uom_missing_fields': uom_check['missing_fields']
        }


def get_vendor_item_review_service(db: Session) -> VendorItemReviewService:
    """Get vendor item review service instance"""
    return VendorItemReviewService(db)
