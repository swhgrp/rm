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
    # Bottle variations → map to "each" (a bottle IS an individual unit)
    'BTL': 'ea',
    'BOTTLE': 'ea',
    'BTLS': 'ea',
    'BT': 'ea',
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
