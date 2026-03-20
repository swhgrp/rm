"""
CSV Preference Service

Checks whether a vendor+location combination expects CSV invoices.
When CSV is expected, PDF invoices are stored as reference only.
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_

from integration_hub.models.csv_expected_vendor import CsvExpectedVendor

logger = logging.getLogger(__name__)

# In-memory cache (refreshed on first miss or manually)
_cache = None


def _load_cache(db: Session):
    """Load all active CSV-expected vendor+location pairs into memory."""
    global _cache
    rows = db.query(CsvExpectedVendor).filter(
        CsvExpectedVendor.is_active == True
    ).all()
    # Build set of (vendor_id, location_id) tuples
    # location_id=None means all locations for that vendor
    _cache = set()
    _all_locations_vendors = set()
    for row in rows:
        if row.location_id is None:
            _all_locations_vendors.add(row.vendor_id)
        else:
            _cache.add((row.vendor_id, row.location_id))
    _cache_all_locations = _all_locations_vendors
    # Store as tuple for immutability
    _load_cache._all_locations = _all_locations_vendors
    logger.info(f"Loaded CSV preference cache: {len(_cache)} vendor+location pairs, "
                f"{len(_all_locations_vendors)} all-location vendors")


def is_csv_expected(vendor_id: int, location_id: int, db: Session) -> bool:
    """
    Check if CSV invoices are expected for this vendor+location.

    Args:
        vendor_id: Hub vendor ID
        location_id: Location ID (1-6)
        db: Database session

    Returns:
        True if CSV is expected (PDF should be reference-only)
    """
    global _cache
    if _cache is None:
        _load_cache(db)

    if not vendor_id or not location_id:
        return False

    # Check exact match
    if (vendor_id, location_id) in _cache:
        return True

    # Check all-locations match
    if hasattr(_load_cache, '_all_locations') and vendor_id in _load_cache._all_locations:
        return True

    return False


def refresh_cache(db: Session):
    """Force refresh of the CSV preference cache."""
    global _cache
    _cache = None
    _load_cache(db)
