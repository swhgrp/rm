"""
Auto-Mapper Service

Automatically maps invoice line items to inventory items and GL accounts
using fuzzy matching, vendor catalogs, and category mappings.
"""

import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.item_gl_mapping import ItemGLMapping, CategoryGLMapping

logger = logging.getLogger(__name__)


class AutoMapperService:
    """Service for automatically mapping invoice items"""

    def __init__(self, db: Session):
        self.db = db

    def fetch_inventory_items(self, vendor_id: Optional[int] = None) -> List[Dict]:
        """
        Fetch inventory items from Inventory API

        In a real implementation, this would call the Inventory API.
        For now, we'll use the local mapping tables.
        """
        # This would be an API call to inventory system
        # For now, return from mapping table
        mappings = self.db.query(ItemGLMapping).filter(
            ItemGLMapping.is_active == True
        )

        if vendor_id:
            mappings = mappings.filter(
                or_(
                    ItemGLMapping.vendor_id == vendor_id,
                    ItemGLMapping.vendor_id.is_(None)
                )
            )

        return [
            {
                'id': m.inventory_item_id,
                'name': m.inventory_item_name,
                'category': m.inventory_category,
                'vendor_id': m.vendor_id,
                'vendor_item_code': m.vendor_item_code,
                'gl_asset_account': m.gl_asset_account,
                'gl_cogs_account': m.gl_cogs_account,
                'gl_waste_account': m.gl_waste_account
            }
            for m in mappings.all()
        ]

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity score between two strings (0.0 to 1.0)

        Uses a simple approach:
        - Exact match = 1.0
        - Contains match = 0.8
        - Word overlap = 0.6
        """
        if not str1 or not str2:
            return 0.0

        str1_lower = str1.lower().strip()
        str2_lower = str2.lower().strip()

        # Exact match
        if str1_lower == str2_lower:
            return 1.0

        # One contains the other
        if str1_lower in str2_lower:
            return 0.85 * (len(str1_lower) / len(str2_lower))
        if str2_lower in str1_lower:
            return 0.85 * (len(str2_lower) / len(str1_lower))

        # Word overlap
        words1 = set(str1_lower.split())
        words2 = set(str2_lower.split())

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        if total > 0:
            return 0.6 * (overlap / total)

        return 0.0

    def match_by_vendor_item_code(
        self,
        item: HubInvoiceItem,
        vendor_id: Optional[int],
        inventory_items: List[Dict]
    ) -> Optional[Tuple[Dict, float]]:
        """Match by exact vendor item code"""
        if not item.item_code or not vendor_id:
            return None

        item_code_lower = item.item_code.lower().strip()

        for inv_item in inventory_items:
            if (inv_item.get('vendor_id') == vendor_id and
                inv_item.get('vendor_item_code') and
                inv_item['vendor_item_code'].lower().strip() == item_code_lower):
                return (inv_item, 1.0)  # Perfect match

        return None

    def match_by_description(
        self,
        item: HubInvoiceItem,
        inventory_items: List[Dict],
        min_confidence: float = 0.7
    ) -> Optional[Tuple[Dict, float]]:
        """Match by description fuzzy matching"""
        if not item.item_description:
            return None

        best_match = None
        best_score = 0.0

        for inv_item in inventory_items:
            if not inv_item.get('name'):
                continue

            score = self.calculate_similarity(
                item.item_description,
                inv_item['name']
            )

            if score > best_score and score >= min_confidence:
                best_score = score
                best_match = inv_item

        if best_match:
            return (best_match, best_score)

        return None

    def get_category_gl_accounts(self, category: str) -> Optional[Dict]:
        """Get GL accounts for a category"""
        mapping = self.db.query(CategoryGLMapping).filter(
            CategoryGLMapping.inventory_category == category,
            CategoryGLMapping.is_active == True
        ).first()

        if mapping:
            return {
                'gl_asset_account': mapping.gl_asset_account,
                'gl_cogs_account': mapping.gl_cogs_account,
                'gl_waste_account': mapping.gl_waste_account
            }

        return None

    def map_item(
        self,
        item: HubInvoiceItem,
        vendor_id: Optional[int] = None
    ) -> Dict:
        """
        Attempt to automatically map a single item

        Returns:
            Dict with mapping result: {
                'mapped': bool,
                'method': str,
                'confidence': float,
                'inventory_item_id': int,
                'inventory_item_name': str,
                'inventory_category': str,
                'gl_asset_account': int,
                'gl_cogs_account': int,
                'gl_waste_account': int
            }
        """
        # Fetch available inventory items
        inventory_items = self.fetch_inventory_items(vendor_id)

        if not inventory_items:
            logger.warning("No inventory items available for mapping")
            return {'mapped': False, 'reason': 'no_inventory_items'}

        # Try vendor item code match first (highest priority)
        match = self.match_by_vendor_item_code(item, vendor_id, inventory_items)
        if match:
            inv_item, confidence = match
            logger.info(f"Matched item {item.id} by vendor code: {inv_item['name']} (confidence: {confidence})")
            return {
                'mapped': True,
                'method': 'vendor_code',
                'confidence': confidence,
                'inventory_item_id': inv_item['id'],
                'inventory_item_name': inv_item['name'],
                'inventory_category': inv_item['category'],
                'gl_asset_account': inv_item['gl_asset_account'],
                'gl_cogs_account': inv_item['gl_cogs_account'],
                'gl_waste_account': inv_item.get('gl_waste_account')
            }

        # Try description fuzzy match (medium priority)
        match = self.match_by_description(item, inventory_items, min_confidence=0.8)
        if match:
            inv_item, confidence = match
            logger.info(f"Matched item {item.id} by description: {inv_item['name']} (confidence: {confidence})")
            return {
                'mapped': True,
                'method': 'fuzzy_description',
                'confidence': confidence,
                'inventory_item_id': inv_item['id'],
                'inventory_item_name': inv_item['name'],
                'inventory_category': inv_item['category'],
                'gl_asset_account': inv_item['gl_asset_account'],
                'gl_cogs_account': inv_item['gl_cogs_account'],
                'gl_waste_account': inv_item.get('gl_waste_account')
            }

        # No item-level match found
        logger.info(f"No item-level match for {item.id}: {item.item_description}")
        return {'mapped': False, 'reason': 'no_match'}

    def apply_mapping(self, item: HubInvoiceItem, mapping_result: Dict) -> bool:
        """
        Apply mapping result to item

        Returns True if item was mapped
        """
        if not mapping_result.get('mapped'):
            return False

        try:
            item.inventory_item_id = mapping_result['inventory_item_id']
            item.inventory_item_name = mapping_result['inventory_item_name']
            item.inventory_category = mapping_result['inventory_category']
            item.gl_asset_account = mapping_result['gl_asset_account']
            item.gl_cogs_account = mapping_result['gl_cogs_account']
            item.gl_waste_account = mapping_result.get('gl_waste_account')
            item.is_mapped = True
            item.mapping_method = mapping_result['method']
            item.mapping_confidence = mapping_result['confidence']

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error applying mapping to item {item.id}: {str(e)}")
            self.db.rollback()
            return False

    def map_invoice_items(self, invoice_id: int) -> Dict:
        """
        Auto-map all unmapped items for an invoice

        Returns:
            Dict with statistics: {
                'total_items': int,
                'mapped_count': int,
                'unmapped_count': int,
                'methods': {'vendor_code': int, 'fuzzy_description': int}
            }
        """
        from integration_hub.models.hub_invoice import HubInvoice

        # Get invoice and vendor
        invoice = self.db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {'error': 'Invoice not found'}

        # Get all unmapped items
        items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == False
        ).all()

        stats = {
            'total_items': len(items),
            'mapped_count': 0,
            'unmapped_count': 0,
            'methods': {}
        }

        for item in items:
            mapping_result = self.map_item(item, invoice.vendor_id)

            if self.apply_mapping(item, mapping_result):
                stats['mapped_count'] += 1
                method = mapping_result['method']
                stats['methods'][method] = stats['methods'].get(method, 0) + 1
            else:
                stats['unmapped_count'] += 1

        # Update invoice status
        total_items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id
        ).count()

        mapped_items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == True
        ).count()

        if mapped_items == total_items:
            invoice.status = 'ready'  # All items mapped
        elif mapped_items > 0:
            invoice.status = 'mapping'  # Partially mapped
        else:
            invoice.status = 'mapping'  # No items mapped

        self.db.commit()

        logger.info(f"Auto-mapping complete for invoice {invoice_id}: {stats}")
        return stats


def get_auto_mapper(db: Session) -> AutoMapperService:
    """Get auto-mapper service instance"""
    return AutoMapperService(db)
