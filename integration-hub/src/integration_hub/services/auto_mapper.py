"""
Auto-Mapper Service (Hub-Based)

Automatically maps invoice line items to Hub's vendor items table.
Hub is now the source of truth for vendor items.

Mapping Logic (Location-Aware):
1. Match by SKU + location: item_code → hub_vendor_items.vendor_sku (same vendor + location)
2. Match by SKU globally: item_code → hub_vendor_items.vendor_sku (same vendor, any location)
3. Match by fuzzy product name (same vendor, high similarity)
4. Match by expense mapping: item_description → invoice_item_mapping_deprecated table
   (case-insensitive matching for expense items not tracked in inventory)
5. No match: Item goes to unmapped queue

New items are automatically marked as `needs_review` in the vendor items table.

Architecture (Location-Aware Costing):
- Hub owns: UOM (global), Categories (global), Vendor Items (per location)
- Inventory owns: Master Items, Count Units, Location Costs
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_vendor_item import HubVendorItem, VendorItemStatus

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for comparison - lowercase, remove extra spaces/punctuation"""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove common noise words
    noise_words = ['the', 'a', 'an', 'of', 'for', 'with', 'and', '&']
    for word in noise_words:
        text = re.sub(rf'\b{word}\b', '', text)
    # Remove punctuation except alphanumeric and spaces
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_keywords(text: str) -> set:
    """Extract meaningful keywords from product text"""
    normalized = normalize_text(text)
    # Split into words and filter short ones
    words = set(w for w in normalized.split() if len(w) >= 3)
    return words


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two product descriptions.
    Returns value between 0.0 (no match) and 1.0 (perfect match).
    Uses keyword overlap with length normalization.
    """
    if not text1 or not text2:
        return 0.0

    keywords1 = extract_keywords(text1)
    keywords2 = extract_keywords(text2)

    if not keywords1 or not keywords2:
        return 0.0

    # Calculate Jaccard-like similarity with overlap bonus
    intersection = keywords1 & keywords2
    union = keywords1 | keywords2

    if not union:
        return 0.0

    # Base Jaccard similarity
    jaccard = len(intersection) / len(union)

    # Bonus for having most of the smaller set matched
    min_set_size = min(len(keywords1), len(keywords2))
    if min_set_size > 0:
        coverage = len(intersection) / min_set_size
    else:
        coverage = 0

    # Weighted average favoring coverage
    similarity = (jaccard * 0.4) + (coverage * 0.6)

    return similarity


class AutoMapperService:
    """Service for automatically mapping invoice items to Hub vendor items"""

    def __init__(self, db: Session):
        self.db = db
        self._vendor_items_cache = None

    def fetch_vendor_items(self, include_inactive: bool = False) -> List[Dict]:
        """
        Fetch vendor items from Hub's local table.
        Returns list of vendor items with SKU, name, category, location, status, etc.

        Args:
            include_inactive: If True, include inactive items (for admin views)
        """
        if self._vendor_items_cache is not None:
            return self._vendor_items_cache

        try:
            # Query Hub's local vendor items table
            # Filter by status (active or needs_review) unless include_inactive
            query = self.db.query(HubVendorItem)
            if not include_inactive:
                query = query.filter(
                    HubVendorItem.status.in_([VendorItemStatus.active, VendorItemStatus.needs_review])
                )
            items = query.all()

            self._vendor_items_cache = []
            for vi in items:
                self._vendor_items_cache.append({
                    'id': vi.id,
                    'vendor_id': vi.vendor_id,
                    'location_id': vi.location_id,  # Location-aware
                    'vendor_sku': vi.vendor_sku,
                    'vendor_product_name': vi.vendor_product_name,
                    'inventory_master_item_id': vi.inventory_master_item_id,
                    'inventory_master_item_name': vi.inventory_master_item_name,
                    'category': vi.category,
                    'purchase_unit_id': vi.purchase_unit_id,
                    'purchase_unit_name': vi.purchase_unit_name,
                    'purchase_unit_abbr': vi.purchase_unit_abbr,
                    'pack_size': vi.pack_size,
                    'pack_to_primary_factor': float(vi.pack_to_primary_factor) if vi.pack_to_primary_factor else 1.0,
                    'status': vi.status.value if vi.status else 'active',
                    'gl_asset_account': vi.gl_asset_account,
                    'gl_cogs_account': vi.gl_cogs_account,
                    'gl_waste_account': vi.gl_waste_account,
                    'inventory_vendor_item_id': vi.inventory_vendor_item_id,
                    'last_purchase_price': float(vi.last_purchase_price) if vi.last_purchase_price else None
                })

            logger.info(f"Loaded {len(self._vendor_items_cache)} vendor items from Hub database")
            return self._vendor_items_cache

        except Exception as e:
            logger.error(f"Error loading vendor items from Hub: {str(e)}")
            return []

    def match_by_sku(
        self,
        item_code: str,
        vendor_id: int = None,
        location_id: int = None
    ) -> Optional[Dict]:
        """
        Match item code against Hub vendor_items.vendor_sku
        Returns vendor item dict if found, None otherwise

        Location-aware matching strategy:
        1. First try exact match with vendor + location + SKU
        2. If not found, try vendor + SKU (any location) - allows cross-location matching

        Handles leading zeros: invoice may have '390982' while inventory has '000390982'

        Args:
            item_code: The item code/SKU to match
            vendor_id: Optional vendor ID to scope the search (Hub vendor ID)
            location_id: Optional location ID for location-specific matching
        """
        if not item_code:
            return None

        item_code_clean = str(item_code).strip()
        # Also create a normalized version without leading zeros
        item_code_normalized = item_code_clean.lstrip('0') or '0'

        vendor_items = self.fetch_vendor_items()

        # Pass 1: Location-specific match (if location provided)
        if location_id:
            for vi in vendor_items:
                # Match by vendor + location
                if vendor_id and vi.get('vendor_id') != vendor_id:
                    continue
                if vi.get('location_id') != location_id:
                    continue

                vendor_sku = vi.get('vendor_sku')
                if not vendor_sku:
                    continue

                vendor_sku_clean = str(vendor_sku).strip()
                vendor_sku_normalized = vendor_sku_clean.lstrip('0') or '0'

                # Try exact match first
                if vendor_sku_clean == item_code_clean:
                    logger.debug(f"SKU match (location-specific): {item_code} → vendor item {vi['id']} at location {location_id}")
                    return vi

                # Try normalized match (handles leading zeros difference)
                if vendor_sku_normalized == item_code_normalized:
                    logger.debug(f"SKU match (location-specific, normalized): {item_code} → vendor item {vi['id']} at location {location_id}")
                    return vi

        # Pass 2: Vendor-only match (any location) - for cross-location item discovery
        for vi in vendor_items:
            # If vendor_id specified, only match within that vendor
            if vendor_id and vi.get('vendor_id') != vendor_id:
                continue

            vendor_sku = vi.get('vendor_sku')
            if not vendor_sku:
                continue

            vendor_sku_clean = str(vendor_sku).strip()
            vendor_sku_normalized = vendor_sku_clean.lstrip('0') or '0'

            # Try exact match first
            if vendor_sku_clean == item_code_clean:
                logger.debug(f"SKU match (cross-location): {item_code} → vendor item {vi['id']} from location {vi.get('location_id')}")
                return vi

            # Try normalized match (handles leading zeros difference)
            if vendor_sku_normalized == item_code_normalized:
                logger.debug(f"SKU match (cross-location, normalized): {item_code} → vendor item {vi['id']} from location {vi.get('location_id')}")
                return vi

        return None

    def match_by_fuzzy_name(
        self,
        item_description: str,
        vendor_id: int,
        location_id: int = None,
        min_similarity: float = 0.7
    ) -> Optional[Tuple[Dict, float]]:
        """
        Match item description against vendor items using fuzzy matching.
        Searches within the specified vendor's items, preferring location-specific matches.

        Location-aware matching strategy:
        1. First search for matches at the specific location
        2. If no good match, search across all locations for that vendor

        Args:
            item_description: The invoice item description
            vendor_id: Hub vendor ID to scope the search
            location_id: Optional location ID for location-specific matching
            min_similarity: Minimum similarity threshold (0.0-1.0)

        Returns:
            Tuple of (vendor_item_dict, similarity_score) or None
        """
        if not item_description or not vendor_id:
            return None

        vendor_items = self.fetch_vendor_items()

        # Pass 1: Location-specific match (if location provided)
        if location_id:
            best_match = None
            best_score = 0.0

            for vi in vendor_items:
                # Only match within the same vendor AND location
                if vi.get('vendor_id') != vendor_id:
                    continue
                if vi.get('location_id') != location_id:
                    continue

                vendor_product_name = vi.get('vendor_product_name')
                if not vendor_product_name:
                    continue

                score = calculate_similarity(item_description, vendor_product_name)

                if score > best_score and score >= min_similarity:
                    best_score = score
                    best_match = vi

            if best_match:
                logger.debug(f"Fuzzy match (location-specific): '{item_description[:30]}' → vendor item {best_match['id']} (score: {best_score:.2f})")
                return (best_match, best_score)

        # Pass 2: Vendor-only match (any location)
        best_match = None
        best_score = 0.0

        for vi in vendor_items:
            # Only match within the same vendor
            if vi.get('vendor_id') != vendor_id:
                continue

            vendor_product_name = vi.get('vendor_product_name')
            if not vendor_product_name:
                continue

            score = calculate_similarity(item_description, vendor_product_name)

            if score > best_score and score >= min_similarity:
                best_score = score
                best_match = vi

        if best_match:
            logger.debug(f"Fuzzy match (cross-location): '{item_description[:30]}' → vendor item {best_match['id']} (score: {best_score:.2f})")
            return (best_match, best_score)

        return None

    def match_by_expense_mapping(self, item_description: str) -> Optional[Dict]:
        """
        Check if this item description is mapped as an expense item.
        Uses invoice_item_mapping_deprecated table (source of truth for expense items)
        with case-insensitive matching.

        Returns expense mapping dict if found, None otherwise
        """
        if not item_description:
            return None

        # Query invoice_item_mapping_deprecated with case-insensitive matching
        # Expense items have inventory_item_id IS NULL (not linked to inventory)
        result = self.db.execute(
            sql_text("""
                SELECT id, gl_cogs_account, gl_asset_account, gl_waste_account,
                       inventory_category, item_description
                FROM invoice_item_mapping_deprecated
                WHERE LOWER(item_description) = LOWER(:desc)
                AND is_active = true
                AND inventory_item_id IS NULL
                LIMIT 1
            """),
            {"desc": item_description}
        ).fetchone()

        if result:
            logger.debug(f"Expense mapping found: '{item_description[:30]}' → GL {result[1]} (mapping id: {result[0]})")
            return {
                'is_expense': True,
                'mapping_id': result[0],
                'gl_cogs_account': result[1],
                'gl_asset_account': result[2],
                'gl_waste_account': result[3],
                'inventory_category': result[4],
                # Keep gl_expense_account as alias for backward compatibility
                'gl_expense_account': result[1]
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

    def _build_mapping_result(
        self,
        vendor_item: Dict,
        method: str,
        confidence: float = 1.0
    ) -> Dict:
        """Build a mapping result dict from a vendor item match"""
        category = vendor_item.get('category')

        # First check if vendor item has GL accounts directly
        gl_accounts = None
        if vendor_item.get('gl_cogs_account'):
            gl_accounts = {
                'gl_asset_account': vendor_item.get('gl_asset_account'),
                'gl_cogs_account': vendor_item.get('gl_cogs_account'),
                'gl_waste_account': vendor_item.get('gl_waste_account')
            }
        # Otherwise look up by category
        elif category:
            gl_accounts = self.get_gl_accounts_for_category(category)

        # Only consider "mapped" if we have the required GL accounts
        has_required_gl = gl_accounts and gl_accounts.get('gl_cogs_account')

        return {
            'mapped': has_required_gl,
            'method': method,
            'confidence': confidence,
            'vendor_item_id': vendor_item['id'],  # Hub vendor item ID
            'inventory_vendor_item_id': vendor_item.get('inventory_vendor_item_id'),
            'vendor_item_name': vendor_item.get('vendor_product_name'),
            'master_item_id': vendor_item.get('inventory_master_item_id'),
            'master_item_name': vendor_item.get('inventory_master_item_name'),
            'category': category,
            'gl_asset_account': gl_accounts['gl_asset_account'] if gl_accounts else None,
            'gl_cogs_account': gl_accounts['gl_cogs_account'] if gl_accounts else None,
            'gl_waste_account': gl_accounts.get('gl_waste_account') if gl_accounts else None,
            'is_expense': False,
            'reason': None if has_required_gl else 'no_category_gl_mapping'
        }

    def map_item(self, item: HubInvoiceItem, vendor_id: int = None, location_id: int = None) -> Dict:
        """
        Attempt to automatically map a single item

        Location-aware matching strategy:
        1. First try SKU match with vendor + location
        2. Then try SKU match with vendor only (cross-location)
        3. Then try fuzzy name match (location-aware)
        4. Finally try expense mapping

        Args:
            item: The invoice item to map
            vendor_id: Hub vendor ID for the invoice (for vendor-scoped matching)
            location_id: Location ID from invoice (for location-specific matching)

        Returns:
            Dict with mapping result including location info
        """
        # 1. Try SKU match against Hub vendor items (location-aware)
        if item.item_code:
            vendor_item = self.match_by_sku(item.item_code, vendor_id, location_id)
            if vendor_item:
                result = self._build_mapping_result(vendor_item, 'sku_match', confidence=1.0)
                # Track if this was a cross-location match
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 2. Try fuzzy name match (location-aware)
        if vendor_id and item.item_description:
            fuzzy_result = self.match_by_fuzzy_name(item.item_description, vendor_id, location_id, min_similarity=0.65)
            if fuzzy_result:
                vendor_item, score = fuzzy_result
                result = self._build_mapping_result(vendor_item, 'fuzzy_name_match', confidence=score)
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 3. Try expense mapping (from invoice_item_mapping_deprecated table)
        expense = self.match_by_expense_mapping(item.item_description)
        if expense:
            return {
                'mapped': True,
                'method': 'expense_mapping',
                'confidence': 1.0,
                'vendor_item_id': None,
                'inventory_vendor_item_id': None,
                'vendor_item_name': None,
                'master_item_id': None,
                'master_item_name': None,
                'category': expense.get('inventory_category', 'Uncategorized'),
                'gl_asset_account': expense.get('gl_asset_account'),
                'gl_cogs_account': expense.get('gl_cogs_account') or expense.get('gl_expense_account'),
                'gl_waste_account': expense.get('gl_waste_account'),
                'is_expense': True,
                'expense_mapping_id': expense.get('mapping_id'),
                'matched_location_id': None,
                'is_cross_location': False
            }

        # 4. No match found
        return {
            'mapped': False,
            'reason': 'no_match',
            'matched_location_id': None,
            'is_cross_location': False
        }

    def apply_mapping(self, item: HubInvoiceItem, mapping_result: Dict) -> bool:
        """
        Apply mapping result to item
        Returns True if item was fully mapped (has GL accounts)

        Note: Even partial matches (SKU match but no category/GL) will store
        the inventory_item_id for reference, but is_mapped stays False.
        """
        try:
            # Store vendor item ID if we found a match
            # inventory_item_id in HubInvoiceItem stores the Hub vendor item ID
            if mapping_result.get('vendor_item_id'):
                item.inventory_item_id = mapping_result.get('vendor_item_id')
                item.mapping_method = mapping_result.get('method')

            # Store master item info if available
            if mapping_result.get('inventory_vendor_item_id'):
                # Store for reference when sending to Inventory
                item.inventory_item_name = mapping_result.get('master_item_name')

            # Only fully map if we have required GL accounts
            if not mapping_result.get('mapped'):
                return False

            item.inventory_category = mapping_result.get('category')
            item.gl_asset_account = mapping_result.get('gl_asset_account')
            item.gl_cogs_account = mapping_result.get('gl_cogs_account')
            item.gl_waste_account = mapping_result.get('gl_waste_account')
            item.is_mapped = True
            # Store confidence - 1.0 for exact SKU match, lower for fuzzy matches
            item.mapping_confidence = mapping_result.get('confidence', 1.0)

            return True

        except Exception as e:
            logger.error(f"Error applying mapping to item {item.id}: {str(e)}")
            return False

    def map_invoice_items(self, invoice_id: int) -> Dict:
        """
        Auto-map all unmapped items for an invoice using location-aware matching.

        Location-aware matching:
        1. Uses invoice.location_id for location-specific vendor item lookup
        2. Falls back to cross-location matching if no local match found
        3. Tracks cross-location matches for potential vendor item creation

        Returns:
            Dict with statistics including cross-location matches
        """
        # Get invoice
        invoice = self.db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {'error': 'Invoice not found'}

        # Get vendor_id and location_id for location-aware matching
        vendor_id = invoice.vendor_id
        location_id = invoice.location_id

        logger.info(f"Auto-mapping invoice {invoice_id}: vendor={vendor_id}, location={location_id}")

        # Get all unmapped items
        items = self.db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == False
        ).all()

        stats = {
            'total_items': len(items),
            'mapped_count': 0,
            'unmapped_count': 0,
            'cross_location_count': 0,  # Items matched from different location
            'methods': {},
            'cross_location_items': []  # Track for potential vendor item creation
        }

        for item in items:
            # Pass vendor_id AND location_id for location-aware matching
            mapping_result = self.map_item(item, vendor_id=vendor_id, location_id=location_id)

            if self.apply_mapping(item, mapping_result):
                stats['mapped_count'] += 1
                method = mapping_result.get('method', 'unknown')
                stats['methods'][method] = stats['methods'].get(method, 0) + 1

                # Track cross-location matches (for potential vendor item creation at this location)
                if mapping_result.get('is_cross_location'):
                    stats['cross_location_count'] += 1
                    stats['cross_location_items'].append({
                        'item_description': item.item_description,
                        'item_code': item.item_code,
                        'vendor_item_id': mapping_result.get('vendor_item_id'),
                        'matched_location_id': mapping_result.get('matched_location_id'),
                        'invoice_location_id': location_id
                    })
            else:
                stats['unmapped_count'] += 1

        # Commit all changes
        self.db.commit()

        # Update invoice status if function exists
        try:
            from integration_hub.services.invoice_status import update_invoice_status
            new_status = update_invoice_status(invoice, self.db)
            self.db.commit()
            logger.info(f"Auto-mapping complete for invoice {invoice_id}: {stats['mapped_count']} mapped, {stats['unmapped_count']} unmapped, {stats['cross_location_count']} cross-location, status: {new_status}")
        except ImportError:
            logger.info(f"Auto-mapping complete for invoice {invoice_id}: {stats['mapped_count']} mapped, {stats['unmapped_count']} unmapped, {stats['cross_location_count']} cross-location")

        return stats


def get_auto_mapper(db: Session) -> AutoMapperService:
    """Get auto-mapper service instance"""
    return AutoMapperService(db)
