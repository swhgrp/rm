"""
Auto-Mapper Service (Simplified)

Automatically maps invoice line items to inventory vendor items by SKU lookup.
All vendor item data lives in the Inventory system - hub just matches against it.

Mapping Logic:
1. Match by SKU: item_code → inventory vendor_items.vendor_sku
2. Match by expense mapping: item_description → expense_mappings table
3. No match: Item goes to unmapped queue
"""

import logging
import httpx
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_invoice import HubInvoice

logger = logging.getLogger(__name__)

# Inventory API URL
INVENTORY_API_URL = "http://inventory-app:8000/api"


class AutoMapperService:
    """Service for automatically mapping invoice items to inventory vendor items"""

    def __init__(self, db: Session):
        self.db = db
        self._vendor_items_cache = None

    def fetch_vendor_items_from_inventory(self) -> List[Dict]:
        """
        Fetch all active vendor items from Inventory API
        Returns list of vendor items with SKU, name, category, etc.
        """
        if self._vendor_items_cache is not None:
            return self._vendor_items_cache

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{INVENTORY_API_URL}/vendor-items/_hub/sync",
                    params={"is_active": True, "limit": 10000}
                )
                if response.status_code == 200:
                    self._vendor_items_cache = response.json()
                    logger.info(f"Fetched {len(self._vendor_items_cache)} vendor items from inventory")
                    return self._vendor_items_cache
                else:
                    logger.error(f"Failed to fetch vendor items: {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching vendor items from inventory: {str(e)}")
            return []

    def match_by_sku(self, item_code: str) -> Optional[Dict]:
        """
        Match item code against inventory vendor_items.vendor_sku
        Returns vendor item dict if found, None otherwise

        Handles leading zeros: invoice may have '390982' while inventory has '000390982'
        """
        if not item_code:
            return None

        item_code_clean = str(item_code).strip()
        # Also create a normalized version without leading zeros
        item_code_normalized = item_code_clean.lstrip('0') or '0'

        vendor_items = self.fetch_vendor_items_from_inventory()

        for vi in vendor_items:
            vendor_sku = vi.get('vendor_sku')
            if not vendor_sku:
                continue

            vendor_sku_clean = str(vendor_sku).strip()
            vendor_sku_normalized = vendor_sku_clean.lstrip('0') or '0'

            # Try exact match first
            if vendor_sku_clean == item_code_clean:
                return vi

            # Try normalized match (handles leading zeros difference)
            if vendor_sku_normalized == item_code_normalized:
                return vi

        return None

    def match_by_expense_mapping(self, item_description: str) -> Optional[Dict]:
        """
        Check if this item description is mapped as an expense item
        Returns expense mapping dict if found, None otherwise
        """
        if not item_description:
            return None

        result = self.db.execute(
            sql_text("""
                SELECT gl_expense_account, gl_account_name
                FROM expense_mappings
                WHERE item_description = :desc
            """),
            {"desc": item_description}
        ).fetchone()

        if result:
            return {
                'is_expense': True,
                'gl_expense_account': result[0],
                'gl_account_name': result[1]
            }

        return None

    def get_gl_accounts_for_category(self, category: str) -> Optional[Dict]:
        """
        Look up GL accounts for an inventory category
        """
        if not category:
            return None

        result = self.db.execute(
            sql_text("""
                SELECT gl_asset_account, gl_cogs_account, gl_waste_account
                FROM category_gl_mapping
                WHERE inventory_category = :category
                AND is_active = true
            """),
            {"category": category}
        ).fetchone()

        if result:
            return {
                'gl_asset_account': result[0],
                'gl_cogs_account': result[1],
                'gl_waste_account': result[2]
            }

        return None

    def map_item(self, item: HubInvoiceItem) -> Dict:
        """
        Attempt to automatically map a single item

        Returns:
            Dict with mapping result
        """
        # 1. Try SKU match against inventory
        if item.item_code:
            vendor_item = self.match_by_sku(item.item_code)
            if vendor_item:
                # Get category from vendor item (comes from master_item)
                category = vendor_item.get('master_item_category')

                # Get GL accounts from category mapping
                gl_accounts = self.get_gl_accounts_for_category(category) if category else None

                # Only consider "mapped" if we have the required GL accounts
                # An item without GL accounts cannot be sent to accounting
                has_required_gl = gl_accounts and gl_accounts.get('gl_cogs_account')

                return {
                    'mapped': has_required_gl,  # Only mapped if we have GL accounts
                    'method': 'sku_match',
                    'vendor_item_id': vendor_item['id'],
                    'vendor_item_name': vendor_item.get('vendor_product_name'),
                    'vendor_name': vendor_item.get('vendor_name'),
                    'category': category,
                    'gl_asset_account': gl_accounts['gl_asset_account'] if gl_accounts else None,
                    'gl_cogs_account': gl_accounts['gl_cogs_account'] if gl_accounts else None,
                    'gl_waste_account': gl_accounts.get('gl_waste_account') if gl_accounts else None,
                    'is_expense': False,
                    'reason': None if has_required_gl else 'no_category_gl_mapping'
                }

        # 2. Try expense mapping
        expense = self.match_by_expense_mapping(item.item_description)
        if expense:
            return {
                'mapped': True,
                'method': 'expense_mapping',
                'vendor_item_id': None,
                'vendor_item_name': None,
                'vendor_name': None,
                'category': 'Uncategorized',
                'gl_asset_account': None,
                'gl_cogs_account': expense['gl_expense_account'],
                'gl_waste_account': None,
                'is_expense': True
            }

        # 3. No match found
        return {
            'mapped': False,
            'reason': 'no_sku_match'
        }

    def apply_mapping(self, item: HubInvoiceItem, mapping_result: Dict) -> bool:
        """
        Apply mapping result to item
        Returns True if item was fully mapped (has GL accounts)

        Note: Even partial matches (SKU match but no category/GL) will store
        the inventory_item_id for reference, but is_mapped stays False.
        """
        try:
            # Always store inventory item ID if we found a match
            # This allows showing "partial match" status in the UI
            if mapping_result.get('vendor_item_id'):
                item.inventory_item_id = mapping_result.get('vendor_item_id')
                item.mapping_method = mapping_result.get('method')

            # Only fully map if we have required GL accounts
            if not mapping_result.get('mapped'):
                return False

            item.inventory_category = mapping_result.get('category')
            item.gl_asset_account = mapping_result.get('gl_asset_account')
            item.gl_cogs_account = mapping_result.get('gl_cogs_account')
            item.gl_waste_account = mapping_result.get('gl_waste_account')
            item.is_mapped = True
            item.mapping_confidence = 1.0  # SKU match is exact

            return True

        except Exception as e:
            logger.error(f"Error applying mapping to item {item.id}: {str(e)}")
            return False

    def map_invoice_items(self, invoice_id: int) -> Dict:
        """
        Auto-map all unmapped items for an invoice

        Returns:
            Dict with statistics
        """
        # Get invoice
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
            mapping_result = self.map_item(item)

            if self.apply_mapping(item, mapping_result):
                stats['mapped_count'] += 1
                method = mapping_result.get('method', 'unknown')
                stats['methods'][method] = stats['methods'].get(method, 0) + 1
            else:
                stats['unmapped_count'] += 1

        # Commit all changes
        self.db.commit()

        # Update invoice status using proper validation
        # Import here to avoid circular imports
        from integration_hub.main import update_invoice_status

        new_status = update_invoice_status(invoice, self.db)
        self.db.commit()

        logger.info(f"Auto-mapping complete for invoice {invoice_id}: {stats}, status: {new_status}")
        return stats


def get_auto_mapper(db: Session) -> AutoMapperService:
    """Get auto-mapper service instance"""
    return AutoMapperService(db)
