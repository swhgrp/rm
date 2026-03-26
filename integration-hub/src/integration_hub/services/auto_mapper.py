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
from integration_hub.services.uom_normalizer import normalize_uom_string, resolve_uom_id

logger = logging.getLogger(__name__)

# Individual unit abbreviations (invoice UOM strings that indicate per-unit pricing)
INDIVIDUAL_UNIT_ABBRS = {'EA', 'EACH', 'BTL', 'BOTTLE', 'PC', 'PIECE'}
# Case abbreviations (invoice UOM strings that indicate per-case pricing)
CASE_UNIT_ABBRS = {'CS', 'CASE'}


def determine_price_is_per_unit(
    invoice_uom: Optional[str],
    vendor_purchase_abbr: Optional[str]
) -> Optional[bool]:
    """
    Determine whether an invoice line item's unit_price is per individual unit
    or per case, by comparing the parsed invoice UOM against the vendor item's
    structured purchase_unit_abbr.

    Returns:
        True  - price is per individual unit (EA/BTL/BOTTLE)
        False - price is per case (CS/CASE)
        None  - cannot determine (fallback to string-based logic)
    """
    uom = (invoice_uom or '').strip().upper()
    vendor_abbr = (vendor_purchase_abbr or '').strip().upper()

    # Invoice UOM takes priority - it describes what the price on THIS invoice is for
    if uom in INDIVIDUAL_UNIT_ABBRS:
        return True

    if uom in CASE_UNIT_ABBRS:
        return False

    # Fall back to vendor item's purchase unit when invoice UOM is empty/unknown
    if vendor_abbr in INDIVIDUAL_UNIT_ABBRS:
        return True

    if vendor_abbr in CASE_UNIT_ABBRS:
        return False

    # Cannot determine
    return None


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]



# Common food service abbreviations → full words for fuzzy matching
# Built from GFS invoice patterns and industry-standard abbreviations
FOOD_ABBREVIATIONS = {
    # Proteins
    'chix': 'chicken', 'chkn': 'chicken', 'ckn': 'chicken', 'chk': 'chicken',
    'wng': 'wing', 'wngs': 'wings',
    'brst': 'breast', 'brs': 'breast',
    'tndr': 'tender', 'tndrs': 'tenders', 'tndrln': 'tenderloin',
    'pty': 'patty', 'ptys': 'patties',
    'stk': 'steak', 'stks': 'steaks',
    'shrd': 'shredded',
    'grnd': 'ground',
    # Cooking/prep
    'brd': 'breaded', 'brdd': 'breaded',
    'ckd': 'cooked',
    'frsh': 'fresh',
    'frzn': 'frozen', 'frz': 'frozen',
    'frtd': 'fried', 'frd': 'fried', 'fritd': 'fried',
    'crspy': 'crispy',
    'rstd': 'roasted',
    'smkd': 'smoked',
    'grld': 'grilled',
    'slcd': 'sliced', 'sld': 'sliced',
    'dcd': 'diced',
    'hmstyl': 'homestyle',
    'ssnng': 'seasoning', 'ssnd': 'seasoned',
    # Sizes/shapes
    'jmbo': 'jumbo',
    'lrg': 'large',
    'med': 'medium',
    'sml': 'small', 'sm': 'small',
    'xl': 'extra large',
    'reg': 'regular',
    'mni': 'mini',
    # Cuts/forms
    'splt': 'split', 'spit': 'split',
    'bnls': 'boneless', 'bnlss': 'boneless',
    'skls': 'skinless', 'sknls': 'skinless',
    'w/skn': 'with skin',
    'w/tips': 'with tips',
    'w/bone': 'with bone',
    # Dairy/cheese
    'ched': 'cheddar', 'chdr': 'cheddar',
    'mozz': 'mozzarella',
    'parm': 'parmesan',
    'swss': 'swiss',
    'amrcn': 'american', 'amer': 'american',
    'crm': 'cream',
    # Produce
    'pot': 'potato', 'pots': 'potatoes',
    'tom': 'tomato', 'toms': 'tomatoes',
    'orng': 'orange',
    'lttc': 'lettuce',
    'onin': 'onion',
    'grn': 'green',
    'rd': 'red',
    'wht': 'white',
    'blk': 'black',
    'ylw': 'yellow',
    # Other food
    'sndwch': 'sandwich',
    'sce': 'sauce',
    'drsg': 'dressing',
    'sgr': 'sugar',
    'flr': 'flour',
    'slt': 'salt',
    'ppr': 'pepper',
    'mstrd': 'mustard',
    # Packaging/container
    'plas': 'plastic',
    'cont': 'container',
    'clr': 'clear',
    'liq': 'liquid',
    'pwdfr': 'powder free',
    'fc': 'food container',
    'nat': 'natural',
    'blnd': 'blend',
    'mld': 'mild',
    'wrfrm': 'wing reform',
    'cdn': 'canadian',
    'cvp': 'cryovac',
    'iqf': 'individually quick frozen',
    'ztf': 'zero trans fat',
    'gchc': 'golden choice',
    'bbl': 'barrel',
    'alt': 'alternative',
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison - lowercase, remove extra spaces/punctuation, expand abbreviations"""
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
    # Expand abbreviations to full words
    words = text.split()
    expanded = []
    for w in words:
        expanded.append(FOOD_ABBREVIATIONS.get(w, w))
    text = ' '.join(expanded)
    return text


def extract_keywords(text: str) -> set:
    """Extract meaningful keywords from product text"""
    normalized = normalize_text(text)
    # Split into words and filter short ones
    raw_words = [w for w in normalized.split() if len(w) >= 3]
    # Normalize simple plurals (wings→wing, tenders→tender) for better matching
    # Don't strip 's' from words ending in ss, us, is, es preceded by consonant clusters
    no_strip = {'less', 'ness', 'ross', 'bass', 'swiss', 'class', 'glass', 'bonus', 'citrus'}
    words = set()
    for w in raw_words:
        if (w.endswith('s') and len(w) > 4 and w not in no_strip
                and not w.endswith('ss') and not w.endswith('us')):
            words.add(w[:-1])
        else:
            words.add(w)
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
        self._vendor_expense_cache = {}

    def _get_vendor_expense_rule(self, vendor_id: int) -> Optional[Dict]:
        """Check if vendor is an expense vendor with a default GL account rule."""
        if vendor_id in self._vendor_expense_cache:
            return self._vendor_expense_cache[vendor_id]

        try:
            result = self.db.execute(
                sql_text("""
                    SELECT is_expense_vendor, default_gl_account, expense_category
                    FROM vendors
                    WHERE id = :vendor_id AND is_expense_vendor = true
                """),
                {"vendor_id": vendor_id}
            ).fetchone()

            if result:
                rule = {
                    'default_gl_account': result[1],
                    'expense_category': result[2] or 'Expense'
                }
                self._vendor_expense_cache[vendor_id] = rule
                return rule
            else:
                self._vendor_expense_cache[vendor_id] = None
                return None
        except Exception as e:
            logger.warning(f"Error checking vendor expense rule: {e}")
            return None

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
                    'units_per_case': int(vi.units_per_case) if vi.units_per_case else None,
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
        location_id: int = None,
        item_description: str = None
    ) -> Optional[Dict]:
        """
        Match item code against Hub vendor_items.vendor_sku
        Returns vendor item dict if found, None otherwise

        Location-aware matching strategy:
        1. First try exact match with vendor + location + SKU
        2. If not found, try vendor + SKU (any location) - allows cross-location matching

        Handles leading zeros: invoice may have '390982' while inventory has '000390982'

        Name safety check: If item_description is provided, verifies that the invoice
        description is reasonably similar to the vendor item's product name. This catches
        cases where vendors reassign SKUs to different products.

        Args:
            item_code: The item code/SKU to match
            vendor_id: Optional vendor ID to scope the search (Hub vendor ID)
            location_id: Optional location ID for location-specific matching
            item_description: Optional invoice item description for name similarity check
        """
        if not item_code:
            return None

        item_code_clean = str(item_code).strip()
        # Also create a normalized version without leading zeros
        item_code_normalized = item_code_clean.lstrip('0') or '0'

        vendor_items = self.fetch_vendor_items()

        def _sku_matches(vendor_sku, item_code_clean, item_code_normalized):
            """Check if vendor SKU matches the item code (exact or normalized)"""
            if not vendor_sku:
                return False
            vendor_sku_clean = str(vendor_sku).strip()
            vendor_sku_normalized = vendor_sku_clean.lstrip('0') or '0'
            return vendor_sku_clean == item_code_clean or vendor_sku_normalized == item_code_normalized

        def _check_name_similarity(vi, match_type, threshold=0.5):
            """Verify SKU match with name similarity check. Returns vi or None."""
            if item_description and vi.get('vendor_product_name'):
                similarity = calculate_similarity(item_description, vi['vendor_product_name'])
                if similarity < threshold:
                    logger.warning(
                        f"SKU match ({match_type}) REJECTED for {item_code}: "
                        f"invoice desc '{item_description}' vs vendor item {vi['id']} "
                        f"'{vi['vendor_product_name']}' — similarity {similarity:.2f} < {threshold} "
                        f"(possible SKU reassignment by vendor)"
                    )
                    return None
            logger.debug(f"SKU match ({match_type}): {item_code} → vendor item {vi['id']}")
            return vi

        # Pass 1: Location-specific match (if location provided)
        # Same vendor + exact SKU = trust it (no name similarity check)
        if location_id:
            for vi in vendor_items:
                if vendor_id and vi.get('vendor_id') != vendor_id:
                    continue
                if vi.get('location_id') != location_id:
                    continue
                if _sku_matches(vi.get('vendor_sku'), item_code_clean, item_code_normalized):
                    logger.debug(f"SKU match (location-specific): {item_code} → vendor item {vi['id']}")
                    return vi

        # Pass 2: Vendor-only match (any location) - for cross-location item discovery
        # Same vendor + exact SKU = trust it (no name similarity check)
        for vi in vendor_items:
            if vendor_id and vi.get('vendor_id') != vendor_id:
                continue
            if _sku_matches(vi.get('vendor_sku'), item_code_clean, item_code_normalized):
                logger.debug(f"SKU match (cross-location): {item_code} → vendor item {vi['id']}")
                return vi

        # Pass 3: Cross-vendor SKU match - handles vendor aliases/duplicates
        if vendor_id:
            for vi in vendor_items:
                if _sku_matches(vi.get('vendor_sku'), item_code_clean, item_code_normalized):
                    logger.debug(f"SKU match (cross-vendor): {item_code} → vendor item {vi['id']}")
                    return vi

        return None

    def match_by_near_sku(
        self,
        item_code: str,
        vendor_id: int = None,
        location_id: int = None,
        max_distance: int = 2,
        item_description: str = None,
        min_desc_similarity: float = 0.3
    ) -> Optional[Dict]:
        """
        Match item code against vendor SKUs using Levenshtein distance,
        with description similarity as confirmer and tiebreaker.

        Strategy:
        - Distance 1, single SKU match → accept (description optional)
        - Distance 1, multiple SKU matches → use description to pick best
        - Distance 2, single or multiple → require description confirmation
        - Description similarity is always used to rank and validate

        Args:
            item_code: The parsed item code from the invoice
            vendor_id: Vendor ID to scope the search
            location_id: Location ID for location-specific matching
            max_distance: Maximum Levenshtein distance (default 2)
            item_description: Invoice item description for confirming matches
            min_desc_similarity: Minimum description similarity for distance 2+ (default 0.3)

        Returns:
            Vendor item dict if confident match found, else None
        """
        if not item_code:
            return None

        item_code_clean = str(item_code).strip()
        item_code_norm = item_code_clean.lstrip('0') or '0'

        vendor_items = self.fetch_vendor_items()

        # Collect all near-matches, grouped by normalized SKU
        near_matches_by_sku = {}  # {normalized_sku: (vendor_item_dict, distance)}

        for vi in vendor_items:
            if vendor_id and vi.get('vendor_id') != vendor_id:
                continue

            vendor_sku = vi.get('vendor_sku')
            if not vendor_sku:
                continue

            sku_clean = str(vendor_sku).strip()
            sku_norm = sku_clean.lstrip('0') or '0'

            # Skip exact matches (handled by match_by_sku)
            if sku_norm == item_code_norm:
                continue

            # Quick length pre-check
            if abs(len(item_code_norm) - len(sku_norm)) > max_distance:
                continue

            dist = _levenshtein_distance(item_code_norm, sku_norm)
            if dist <= max_distance:
                # Keep the best (closest) match per SKU, prefer same location
                existing = near_matches_by_sku.get(sku_norm)
                if existing is None:
                    near_matches_by_sku[sku_norm] = (vi, dist)
                else:
                    # Prefer same-location match for the same SKU
                    existing_same_loc = existing[0].get('location_id') == location_id
                    new_same_loc = vi.get('location_id') == location_id
                    if new_same_loc and not existing_same_loc:
                        near_matches_by_sku[sku_norm] = (vi, dist)

        if len(near_matches_by_sku) == 0:
            return None

        # Score each candidate: combine SKU distance with description similarity
        scored = []
        for sku_norm, (vi, dist) in near_matches_by_sku.items():
            desc_score = 0.0
            if item_description and vi.get('vendor_product_name'):
                desc_score = calculate_similarity(item_description, vi['vendor_product_name'])
            scored.append((vi, dist, desc_score))

        # Sort: lowest distance first, then highest description score
        scored.sort(key=lambda x: (x[1], -x[2]))

        best_vi, best_dist, best_desc = scored[0]

        # Decision logic — always require description confirmation
        if best_dist == 1 and len(scored) == 1:
            # Single distance-1 match — still require description to prevent wrong product mapping
            if not item_description:
                logger.debug(f"Near-SKU skip (d=1): no description to confirm '{item_code}'")
                return None
            if best_desc < min_desc_similarity:
                logger.warning(
                    f"Near-SKU REJECTED (d=1): '{item_code}' → '{best_vi.get('vendor_sku')}' "
                    f"({best_vi.get('vendor_product_name', '')[:40]}) — "
                    f"desc similarity {best_desc:.2f} < {min_desc_similarity} "
                    f"(invoice desc: '{item_description[:50]}')"
                )
                return None
            logger.info(
                f"Near-SKU match (d=1): '{item_code}' → '{best_vi.get('vendor_sku')}' "
                f"({best_vi.get('vendor_product_name', '')[:40]}) [desc={best_desc:.2f}]"
            )
            return best_vi

        if best_dist == 1 and len(scored) > 1:
            # Multiple distance-1 matches — use description as tiebreaker
            if item_description and best_desc >= min_desc_similarity:
                second_desc = scored[1][2] if len(scored) > 1 else 0.0
                # Accept if best description score is clearly ahead
                if best_desc > second_desc + 0.1:
                    logger.info(
                        f"Near-SKU match (d=1, desc tiebreak): '{item_code}' → "
                        f"'{best_vi.get('vendor_sku')}' ({best_vi.get('vendor_product_name', '')[:40]}) "
                        f"[desc={best_desc:.2f} vs {second_desc:.2f}]"
                    )
                    return best_vi
            logger.debug(
                f"Near-SKU ambiguous (d=1): '{item_code}' has {len(scored)} candidates, "
                f"desc scores too close: {[(s[0].get('vendor_sku'), s[2]) for s in scored[:3]]}"
            )
            return None

        # Distance 2+ — require description confirmation
        if not item_description:
            logger.debug(f"Near-SKU skip (d={best_dist}): no description to confirm '{item_code}'")
            return None

        if best_desc < min_desc_similarity:
            logger.debug(
                f"Near-SKU reject (d={best_dist}): '{item_code}' → '{best_vi.get('vendor_sku')}' "
                f"desc too low ({best_desc:.2f} < {min_desc_similarity})"
            )
            return None

        # For distance 2 with multiple candidates, need clear desc winner
        if len(scored) > 1:
            second_desc = scored[1][2]
            if best_desc <= second_desc + 0.1:
                logger.debug(
                    f"Near-SKU ambiguous (d={best_dist}): '{item_code}' desc scores too close: "
                    f"{[(s[0].get('vendor_sku'), s[2]) for s in scored[:3]]}"
                )
                return None

        logger.info(
            f"Near-SKU match (d={best_dist}, desc={best_desc:.2f}): '{item_code}' → "
            f"'{best_vi.get('vendor_sku')}' ({best_vi.get('vendor_product_name', '')[:40]})"
        )
        return best_vi

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

    def match_by_learned_mapping(
        self,
        item_code: str,
        item_description: str,
        vendor_id: int
    ) -> Optional[Dict]:
        """
        Check if this item has a user-approved learned mapping.
        Uses learned_sku_mappings table (populated when users manually map items).

        Matching strategy (in order of priority):
        1. Match by vendor + item_code (most reliable)
        2. Match by vendor + item_description (case-insensitive, for OCR variations)

        Returns vendor item dict if found, None otherwise
        """
        if not vendor_id:
            return None

        # First try matching by vendor + item_code
        if item_code:
            result = self.db.execute(
                sql_text("""
                    SELECT vendor_item_id
                    FROM learned_sku_mappings
                    WHERE vendor_id = :vendor_id
                    AND item_code = :item_code
                    LIMIT 1
                """),
                {"vendor_id": vendor_id, "item_code": item_code}
            ).fetchone()

            if result:
                vendor_item_id = result[0]
                # Look up the vendor item
                for vi in self.fetch_vendor_items():
                    if vi['id'] == vendor_item_id:
                        logger.debug(f"Learned mapping found by item_code: '{item_code}' → vendor item {vendor_item_id}")
                        return vi

        # Then try matching by vendor + description (case-insensitive)
        if item_description:
            result = self.db.execute(
                sql_text("""
                    SELECT vendor_item_id
                    FROM learned_sku_mappings
                    WHERE vendor_id = :vendor_id
                    AND LOWER(item_description) = LOWER(:description)
                    LIMIT 1
                """),
                {"vendor_id": vendor_id, "description": item_description}
            ).fetchone()

            if result:
                vendor_item_id = result[0]
                # Look up the vendor item
                for vi in self.fetch_vendor_items():
                    if vi['id'] == vendor_item_id:
                        logger.debug(f"Learned mapping found by description: '{item_description[:30]}' → vendor item {vendor_item_id}")
                        return vi

        return None

    def match_by_expense_mapping(self, item_description: str, item_code: str = None) -> Optional[Dict]:
        """
        Check if this item is mapped as an expense item.
        Uses invoice_item_mapping_deprecated table (source of truth for expense items).

        Matching strategy (in order of priority):
        1. Match by item_code (most reliable for linen, supplies, etc.)
        2. Match by item_description (case-insensitive)

        Returns expense mapping dict if found, None otherwise
        """
        if not item_description and not item_code:
            return None

        # First try matching by item_code (most reliable)
        if item_code:
            result = self.db.execute(
                sql_text("""
                    SELECT id, gl_cogs_account, gl_asset_account, gl_waste_account,
                           inventory_category, item_description, item_code
                    FROM invoice_item_mapping_deprecated
                    WHERE TRIM(item_code) = TRIM(:code)
                    AND is_active = true
                    AND inventory_item_id IS NULL
                    LIMIT 1
                """),
                {"code": item_code}
            ).fetchone()

            if result:
                logger.debug(f"Expense mapping found by item_code: '{item_code}' → GL {result[1]} (mapping id: {result[0]})")
                return {
                    'is_expense': True,
                    'mapping_id': result[0],
                    'gl_cogs_account': result[1],
                    'gl_asset_account': result[2],
                    'gl_waste_account': result[3],
                    'inventory_category': result[4],
                    'gl_expense_account': result[1],
                    'matched_by': 'item_code'
                }

        # Then try matching by description (case-insensitive)
        if item_description:
            result = self.db.execute(
                sql_text("""
                    SELECT id, gl_cogs_account, gl_asset_account, gl_waste_account,
                           inventory_category, item_description, item_code
                    FROM invoice_item_mapping_deprecated
                    WHERE LOWER(TRIM(item_description)) = LOWER(TRIM(:desc))
                    AND is_active = true
                    AND inventory_item_id IS NULL
                    LIMIT 1
                """),
                {"desc": item_description}
            ).fetchone()

            if result:
                logger.debug(f"Expense mapping found by description: '{item_description[:30]}' → GL {result[1]} (mapping id: {result[0]})")
                return {
                    'is_expense': True,
                    'mapping_id': result[0],
                    'gl_cogs_account': result[1],
                    'gl_asset_account': result[2],
                    'gl_waste_account': result[3],
                    'inventory_category': result[4],
                    'gl_expense_account': result[1],
                    'matched_by': 'item_description'
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
            'vendor_sku': vendor_item.get('vendor_sku'),
            'inventory_vendor_item_id': vendor_item.get('inventory_vendor_item_id'),
            'vendor_item_name': vendor_item.get('vendor_product_name'),
            'master_item_id': vendor_item.get('inventory_master_item_id'),
            'master_item_name': vendor_item.get('inventory_master_item_name'),
            'category': category,
            'gl_asset_account': gl_accounts['gl_asset_account'] if gl_accounts else None,
            'gl_cogs_account': gl_accounts['gl_cogs_account'] if gl_accounts else None,
            'gl_waste_account': gl_accounts.get('gl_waste_account') if gl_accounts else None,
            'purchase_unit_abbr': vendor_item.get('purchase_unit_abbr'),
            'units_per_case': vendor_item.get('units_per_case'),
            'is_expense': False,
            'reason': None if has_required_gl else 'no_category_gl_mapping'
        }

    def map_item(self, item: HubInvoiceItem, vendor_id: int = None, location_id: int = None, csv_source: bool = False) -> Dict:
        """
        Attempt to automatically map a single item

        Matching strategy (in order of priority):
        0. Vendor expense rule - entire vendor is an expense vendor (all items → same GL)
        1. SKU match - exact match against vendor_items.vendor_sku
        1b. Near-SKU match - (PDF/AI-parsed only, skipped for CSV)
        2. Learned mapping - user-approved mappings from previous manual mappings
        3. Fuzzy description match - (PDF/AI-parsed only, skipped for CSV)
        4. Expense mapping - expense items from invoice_item_mapping_deprecated

        Args:
            item: The invoice item to map
            vendor_id: Hub vendor ID for the invoice (for vendor-scoped matching)
            location_id: Location ID from invoice (for location-specific matching)
            csv_source: If True, skip fuzzy/near-SKU matching (CSV has exact codes)

        Returns:
            Dict with mapping result including location info
        """
        # 0. Check if vendor is an expense vendor (all items go to same GL account)
        if vendor_id:
            vendor_expense = self._get_vendor_expense_rule(vendor_id)
            if vendor_expense:
                return {
                    'mapped': True,
                    'method': 'vendor_expense_rule',
                    'confidence': 1.0,
                    'vendor_item_id': None,
                    'inventory_vendor_item_id': None,
                    'vendor_item_name': None,
                    'master_item_id': None,
                    'master_item_name': None,
                    'category': vendor_expense['expense_category'],
                    'gl_asset_account': None,
                    'gl_cogs_account': vendor_expense['default_gl_account'],
                    'gl_waste_account': None,
                    'is_expense': True,
                    'expense_mapping_id': None,
                    'matched_location_id': None,
                    'is_cross_location': False
                }

        # 1. Try SKU match against Hub vendor items (location-aware)
        if item.item_code:
            vendor_item = self.match_by_sku(item.item_code, vendor_id, location_id, item_description=item.item_description)
            if vendor_item:
                result = self._build_mapping_result(vendor_item, 'sku_match', confidence=1.0)
                # Track if this was a cross-location match
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 1b. Try near-SKU match (1-2 digits off, confirmed by description similarity)
        # Skip for CSV-parsed invoices — CSV has exact machine-generated SKUs
        if item.item_code and not csv_source:
            vendor_item = self.match_by_near_sku(
                item.item_code, vendor_id, location_id,
                item_description=item.item_description
            )
            if vendor_item:
                result = self._build_mapping_result(vendor_item, 'near_sku_match', confidence=0.9)
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 2. Try learned mapping (user-approved mappings from manual mapping)
        if vendor_id:
            vendor_item = self.match_by_learned_mapping(item.item_code, item.item_description, vendor_id)
            if vendor_item:
                result = self._build_mapping_result(vendor_item, 'learned_mapping', confidence=1.0)
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 3. Try fuzzy description match against vendor items (vendor-scoped, high threshold)
        # Skip for CSV-parsed invoices — CSV has exact SKUs, fuzzy matching risks wrong products
        if vendor_id and item.item_description and not csv_source:
            fuzzy_result = self.match_by_fuzzy_name(
                item.item_description, vendor_id, location_id,
                min_similarity=0.8
            )
            if fuzzy_result:
                vendor_item, score = fuzzy_result
                result = self._build_mapping_result(vendor_item, 'fuzzy_name', confidence=score)
                result['matched_location_id'] = vendor_item.get('location_id')
                result['is_cross_location'] = (location_id and vendor_item.get('location_id') != location_id)
                return result

        # 4. Try expense mapping (from invoice_item_mapping_deprecated table)
        # Pass both description and item_code for better matching
        expense = self.match_by_expense_mapping(item.item_description, item.item_code)
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

        # 5. No match found
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
                # Overwrite parsed code/description with canonical vendor item values
                # Only for exact matches — near_sku_match should preserve original
                # parsed values so discrepancies are visible for review
                if mapping_result.get('method') != 'near_sku_match':
                    if mapping_result.get('vendor_sku'):
                        item.item_code = mapping_result['vendor_sku']
                    if mapping_result.get('vendor_item_name'):
                        item.item_description = mapping_result['vendor_item_name']

            # Store master item info if available
            if mapping_result.get('inventory_vendor_item_id'):
                # Store for reference when sending to Inventory
                item.inventory_item_name = mapping_result.get('master_item_name')

            # Determine price_is_per_unit from vendor item's purchase_unit_abbr (legacy)
            if mapping_result.get('purchase_unit_abbr'):
                item.price_is_per_unit = determine_price_is_per_unit(
                    item.unit_of_measure,
                    mapping_result.get('purchase_unit_abbr')
                )

            # Update vendor item pricing from invoice (so Purchasing & Pricing stays current)
            vendor_item_id = mapping_result.get('vendor_item_id')
            if vendor_item_id and item.unit_price:
                self._update_vendor_item_pricing(vendor_item_id, item)

            # Override pack_size with vendor item's units_per_case (more reliable than AI-parsed)
            vendor_upc = mapping_result.get('units_per_case')
            if vendor_upc:
                item.pack_size = vendor_upc

            # Only fully map if we have required GL accounts
            if not mapping_result.get('mapped'):
                return False

            item.inventory_category = mapping_result.get('category')
            item.gl_asset_account = mapping_result.get('gl_asset_account')
            item.gl_cogs_account = mapping_result.get('gl_cogs_account')
            item.gl_waste_account = mapping_result.get('gl_waste_account')
            item.is_mapped = True
            item.mapping_method = mapping_result.get('method')
            # Store confidence - 1.0 for exact SKU match, lower for fuzzy matches
            item.mapping_confidence = mapping_result.get('confidence', 1.0)

            return True

        except Exception as e:
            logger.error(f"Error applying mapping to item {item.id}: {str(e)}")
            return False

    def _update_vendor_item_pricing(self, vendor_item_id: int, invoice_item: HubInvoiceItem):
        """
        Update vendor item pricing fields from invoice data at mapping time.
        Keeps Purchasing & Pricing section current without waiting for send-to-inventory.
        """
        try:
            vendor_item = self.db.query(HubVendorItem).filter(
                HubVendorItem.id == vendor_item_id
            ).first()
            if not vendor_item:
                return

            unit_price = float(invoice_item.unit_price)
            invoice_date = invoice_item.invoice.invoice_date if invoice_item.invoice else None

            # UOM-aware cost calculation: use parsed unit to determine correct factor
            from integration_hub.services.uom_normalizer import get_effective_conversion_factor
            parsed_uom = getattr(invoice_item, 'unit_of_measure', None)
            cf = get_effective_conversion_factor(vendor_item, parsed_uom)
            if cf > 0:
                cost_per_primary = unit_price / cf
                units_per_case = float(vendor_item.units_per_case or 1)
                new_case_cost = round(cost_per_primary * units_per_case, 4)
            else:
                new_case_cost = round(unit_price, 4)

            if vendor_item.case_cost is None or float(vendor_item.case_cost) != new_case_cost:
                vendor_item.previous_purchase_price = vendor_item.last_purchase_price
                vendor_item.case_cost = new_case_cost
                vendor_item.last_purchase_price = unit_price
                vendor_item.price_updated_at = invoice_date
                logger.debug(f"Updated vendor item {vendor_item_id} pricing: case_cost={new_case_cost}, last_purchase_price={unit_price}")

        except Exception as e:
            logger.warning(f"Failed to update vendor item {vendor_item_id} pricing from invoice: {e}")

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

        # Detect CSV source — CSV has exact machine-generated SKUs, skip fuzzy matching
        csv_source = bool(
            invoice.source_filename and invoice.source_filename.lower().endswith('.csv')
        ) or bool(
            invoice.pdf_path and invoice.pdf_path.lower().endswith('.csv')
        )

        logger.info(f"Auto-mapping invoice {invoice_id}: vendor={vendor_id}, location={location_id}, csv={csv_source}")

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
            mapping_result = self.map_item(item, vendor_id=vendor_id, location_id=location_id, csv_source=csv_source)

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

    def get_fuzzy_suggestions(
        self,
        item_description: str,
        vendor_id: int,
        location_id: int = None,
        max_suggestions: int = 5,
        min_similarity: float = 0.5
    ) -> List[Dict]:
        """
        Get fuzzy match suggestions for an unmapped item.
        These are NOT auto-applied - shown to user for manual approval.

        Args:
            item_description: The invoice item description
            vendor_id: Hub vendor ID
            location_id: Optional location ID for location-specific ranking
            max_suggestions: Maximum number of suggestions to return
            min_similarity: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of suggestion dicts with vendor_item info and similarity score
        """
        if not item_description or not vendor_id:
            return []

        vendor_items = self.fetch_vendor_items()
        suggestions = []

        for vi in vendor_items:
            # Only match within the same vendor
            if vi.get('vendor_id') != vendor_id:
                continue

            vendor_product_name = vi.get('vendor_product_name')
            if not vendor_product_name:
                continue

            score = calculate_similarity(item_description, vendor_product_name)

            if score >= min_similarity:
                suggestions.append({
                    'vendor_item_id': vi['id'],
                    'vendor_sku': vi.get('vendor_sku'),
                    'vendor_product_name': vendor_product_name,
                    'category': vi.get('category'),
                    'location_id': vi.get('location_id'),
                    'similarity_score': round(score, 2),
                    'is_same_location': vi.get('location_id') == location_id
                })

        # Sort by similarity score (descending), prefer same location
        suggestions.sort(key=lambda x: (x['similarity_score'], x['is_same_location']), reverse=True)

        return suggestions[:max_suggestions]

    def save_learned_mapping(
        self,
        vendor_id: int,
        item_code: str,
        item_description: str,
        vendor_item_id: int,
        created_by: int = None
    ) -> bool:
        """
        Save a user-approved mapping to learned_sku_mappings table.
        Called when a user manually maps an item.

        Args:
            vendor_id: Hub vendor ID
            item_code: Invoice item code (may differ from vendor SKU)
            item_description: Invoice item description
            vendor_item_id: The vendor item ID to map to
            created_by: User ID who created this mapping

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Use upsert to handle duplicates
            self.db.execute(
                sql_text("""
                    INSERT INTO learned_sku_mappings
                    (vendor_id, item_code, item_description, vendor_item_id, created_by)
                    VALUES (:vendor_id, :item_code, :item_description, :vendor_item_id, :created_by)
                    ON CONFLICT (vendor_id, item_code, item_description)
                    DO UPDATE SET vendor_item_id = :vendor_item_id, created_by = :created_by
                """),
                {
                    "vendor_id": vendor_id,
                    "item_code": item_code,
                    "item_description": item_description,
                    "vendor_item_id": vendor_item_id,
                    "created_by": created_by
                }
            )
            self.db.commit()
            logger.info(f"Saved learned mapping: vendor={vendor_id}, code={item_code}, desc='{item_description[:30]}' → vendor_item={vendor_item_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving learned mapping: {str(e)}")
            return False


def get_auto_mapper(db: Session) -> AutoMapperService:
    """Get auto-mapper service instance"""
    return AutoMapperService(db)
