"""
UOM Normalizer - Maps parsed invoice UOM strings to standard abbreviations

Centralizes all UOM string normalization to avoid scattered abbreviation mappings
throughout the codebase. Used by auto_mapper and cost_updater to deterministically
match invoice UOMs to vendor item purchase UOMs.
"""
import re
import logging
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Maps common invoice UOM strings (UPPERCASE) to standard units_of_measure.abbreviation
UOM_ALIAS_MAP = {
    # Case variations
    'CS': 'cs',
    'CASE': 'cs',
    'CA': 'cs',
    'CAS': 'cs',
    'CSE': 'cs',
    # Each variations
    'EA': 'ea',
    'EACH': 'ea',
    'PC': 'ea',
    'PIECE': 'ea',
    'PCS': 'ea',
    'UNIT': 'ea',
    # Bottle variations → map to "ea" (a bottle IS an individual unit)
    'BTL': 'ea',
    'BOTTLE': 'ea',
    'BTLS': 'ea',
    'BT': 'ea',
    'BO': 'ea',
    # Weight
    'LB': 'lb',
    'LBS': 'lb',
    'POUND': 'lb',
    'POUNDS': 'lb',
    'OZ': 'oz',
    'OUNCE': 'oz',
    'OUNCES': 'oz',
    'G': 'g',
    'GRAM': 'g',
    'KG': 'kg',
    'KILOGRAM': 'kg',
    # Volume
    'GAL': 'gal',
    'GALLON': 'gal',
    'GL': 'gal',
    'FL OZ': 'fl oz',
    'FLOZ': 'fl oz',
    'L': 'L',
    'LITER': 'L',
    'LITRE': 'L',
    'ML': 'mL',
    'MILLILITER': 'mL',
    'PT': 'pt',
    'PINT': 'pt',
    'QT': 'qt',
    'QUART': 'qt',
    # Keg
    'KEG': 'keg',
    'KE': 'keg',
    # Can → treat as individual unit
    'CAN': 'ea',
    'CN': 'ea',
    # Bag → treat as case-like (conversion_factor defines contents)
    'BG': 'bg',
    'BAG': 'bg',
    # Box
    'BX': 'bx',
    'BOX': 'bx',
    # Dozen
    'DZ': 'dz',
    'DOZ': 'dz',
    'DOZEN': 'dz',
    # Pack
    'PK': 'pk',
    'PACK': 'pk',
    # Deposit/Service (non-product lines)
    'DS': None,
}


def normalize_uom_string(raw_uom: Optional[str]) -> Optional[str]:
    """
    Normalize a parsed invoice UOM string to a standard abbreviation
    matching units_of_measure.abbreviation.

    Args:
        raw_uom: Raw UOM string from invoice (e.g., "CS", "CASE", "CA", "BTL")

    Returns:
        Standard abbreviation (e.g., "cs", "ea", "lb") or None if unrecognizable
    """
    if not raw_uom:
        return None

    cleaned = raw_uom.strip().upper()
    # Remove trailing numbers/periods (e.g., "BTL750ML" → "BTL")
    cleaned = re.sub(r'[\d.]+.*$', '', cleaned).strip()

    if not cleaned:
        return None

    result = UOM_ALIAS_MAP.get(cleaned)
    if result is not None:
        return result

    # Try without trailing 'S' (plurals)
    if cleaned.endswith('S') and len(cleaned) > 2:
        result = UOM_ALIAS_MAP.get(cleaned[:-1])
        if result is not None:
            return result

    logger.debug(f"Could not normalize UOM string: '{raw_uom}' (cleaned: '{cleaned}')")
    return None


# UOM categories for conversion factor logic
CASE_UOMS = {'CS', 'CASE', 'CA', 'CAS', 'CSE'}
PRIMARY_UNIT_GROUPS = {
    'lb': {'LB', 'LBS', 'POUND', 'POUNDS'},
    'ea': {'EA', 'EACH', 'PC', 'PIECE', 'PCS', 'UNIT'},
    'oz': {'OZ', 'OUNCE', 'OUNCES'},
    'gal': {'GAL', 'GALLON', 'GL'},
    'kg': {'KG', 'KILOGRAM'},
    'g': {'G', 'GRAM', 'GRAMS'},
    'L': {'L', 'LITER', 'LITRE'},
}


def get_effective_conversion_factor(vendor_item, parsed_uom: Optional[str]) -> float:
    """
    Calculate the correct conversion factor based on the parsed invoice UOM.

    The invoice unit_price may be per-case, per-bag, or per-pound depending on
    what the Unit column says. This function returns the right divisor to get
    cost_per_primary_unit.

    Logic:
    - CS/CASE/CA: price is per case → divide by pack_to_primary_factor
    - Normalizes to same unit as vendor item's primary (BO→ea, BTL→ea, LBS→lb):
      price is per primary unit → divide by 1
    - BAG/BX/PK/etc (sub-unit): price is per sub-unit → divide by size_quantity

    Example: Onions, vendor item has units_per_case=10, size_quantity=5, pack_to_primary=50
    - CS at $46.50 → factor=50 → $0.93/lb
    - BAG at $4.65 → factor=5 → $0.93/lb
    - LB at $0.93  → factor=1 → $0.93/lb

    Example: Wine 750ml, vendor item has units_per_case=12, purchase_unit_abbr=ea
    - CA at $81.00 → factor=12 → $6.75/bottle
    - BO at $15.60 → normalized to "ea" matches primary "ea" → factor=1 → $15.60/bottle
    """
    cf = float(vendor_item.pack_to_primary_factor or 1.0)
    if cf <= 0:
        return 1.0

    parsed = (parsed_uom or '').strip().upper()
    primary = (getattr(vendor_item, 'purchase_unit_abbr', '') or '').strip().upper()

    # No parsed UOM or it's a case → full case factor (default behavior)
    if not parsed or parsed in CASE_UOMS:
        return cf

    # Normalize both sides using the alias map to catch BO→ea, BTL→ea, LBS→lb, etc.
    normalized_parsed = normalize_uom_string(parsed)
    normalized_primary = normalize_uom_string(primary) if primary else primary.lower()

    # If both normalize to the same standard abbreviation, it's a primary unit match
    # e.g., BO→"ea" and EA→"ea", or LBS→"lb" and LB→"lb"
    if normalized_parsed and normalized_primary and normalized_parsed == normalized_primary:
        return 1.0

    # Direct match (fallback for UOMs not in alias map)
    if parsed == primary:
        return 1.0

    # Check alias groups (fallback for UOMs not in alias map)
    for canonical, aliases in PRIMARY_UNIT_GROUPS.items():
        if parsed in aliases and primary in aliases:
            return 1.0

    # Otherwise it's a sub-unit (BAG, BX, PK, JUG, etc.)
    # Use size_quantity as the factor (primary units per sub-unit)
    # e.g., one BAG of "10x5 LB" onions = 5 lbs → factor=5
    size_qty = float(getattr(vendor_item, 'size_quantity', 0) or 0)
    if size_qty > 0:
        logger.info(
            f"UOM-aware factor: parsed='{parsed}' (→{normalized_parsed}), primary='{primary}' (→{normalized_primary}), "
            f"using size_quantity={size_qty} instead of pack_to_primary={cf}"
        )
        return size_qty

    # Can't determine sub-unit size; fall back to full case factor
    logger.warning(
        f"UOM-aware factor: parsed='{parsed}' (→{normalized_parsed}) is not CS or primary='{primary}' (→{normalized_primary}), "
        f"but no size_quantity on vendor item — falling back to pack_to_primary={cf}"
    )
    return cf


def resolve_uom_id(raw_uom: str, db: Session) -> Optional[int]:
    """
    Resolve a parsed invoice UOM string to a units_of_measure.id.

    Args:
        raw_uom: Raw UOM string from invoice
        db: Database session

    Returns:
        units_of_measure.id or None
    """
    from integration_hub.models.unit_of_measure import UnitOfMeasure

    abbr = normalize_uom_string(raw_uom)
    if not abbr:
        return None

    uom = db.query(UnitOfMeasure).filter(
        func.lower(UnitOfMeasure.abbreviation) == abbr.lower(),
        UnitOfMeasure.is_active.is_(True)
    ).first()

    return uom.id if uom else None
