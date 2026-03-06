"""
Vendor Items API endpoints

CRUD operations for Hub's vendor items table.
Hub is the source of truth for vendor items.

Location-Aware Costing:
- Vendor items are per-location (location_id)
- Status workflow: needs_review → active/inactive
- Review workflow for approving/rejecting new items
"""

import os
import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from integration_hub.db.database import get_db
from integration_hub.models.hub_vendor_item import HubVendorItem, VendorItemStatus
from integration_hub.models.vendor import Vendor
from integration_hub.models.unit_of_measure import UnitOfMeasure
from integration_hub.services.vendor_item_review import VendorItemReviewService, check_uom_completeness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vendor-items", tags=["vendor-items-api"])

# Inventory API URL for fetching master items and UOM
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000/api")

# Internal API key for Hub-to-system communication - MUST be set via environment
HUB_INTERNAL_API_KEY = os.getenv("HUB_INTERNAL_API_KEY")
if not HUB_INTERNAL_API_KEY:
    raise ValueError("HUB_INTERNAL_API_KEY environment variable must be set")

HUB_API_HEADERS = {"X-Hub-API-Key": HUB_INTERNAL_API_KEY}


async def sync_vendor_item_to_inventory(item: "HubVendorItem", vendor: "Vendor", action: str = "sync"):
    """
    Sync a vendor item change to Inventory.
    Called after create/update/delete operations in Hub.

    Args:
        item: The Hub vendor item
        vendor: The vendor (must have inventory_vendor_id)
        action: "sync" for create/update, "delete" for soft-delete
    """
    if not vendor.inventory_vendor_id:
        logger.warning(f"Cannot sync vendor item {item.id}: vendor {vendor.id} has no inventory_vendor_id")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if action == "delete":
                # Sync deletion
                response = await client.post(
                    f"{INVENTORY_API_URL}/hub-vendor-items/sync-delete",
                    params={
                        "hub_vendor_item_id": item.id,
                        "inventory_vendor_id": vendor.inventory_vendor_id,
                        "vendor_sku": item.vendor_sku,
                        "vendor_product_name": item.vendor_product_name
                    }
                )
            else:
                # Sync create/update
                sync_data = {
                    "hub_vendor_item_id": item.id,
                    "inventory_vendor_id": vendor.inventory_vendor_id,
                    "master_item_id": item.inventory_master_item_id,
                    "vendor_sku": item.vendor_sku,
                    "vendor_product_name": item.vendor_product_name,
                    "purchase_unit_id": item.purchase_unit_id,
                    "conversion_factor": float(item.conversion_factor) if item.conversion_factor else 1.0,
                    "unit_price": float(item.unit_price) if item.unit_price else None,
                    "is_preferred": item.is_preferred,
                    "notes": item.notes,
                    "is_active": item.is_active
                }
                response = await client.post(
                    f"{INVENTORY_API_URL}/hub-vendor-items/sync",
                    json=sync_data
                )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Synced vendor item {item.id} to Inventory: {result}")
                return result
            else:
                logger.error(f"Failed to sync vendor item {item.id} to Inventory: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Error syncing vendor item {item.id} to Inventory: {str(e)}")
        return None


def _find_inventory_uom(conn, name=None, abbreviation=None):
    """Look up a UOM from Inventory's units_of_measure table."""
    from sqlalchemy import text
    if name:
        row = conn.execute(
            text("SELECT id, name, abbreviation FROM units_of_measure WHERE LOWER(name) = LOWER(:name)"),
            {"name": name}
        ).fetchone()
        if row:
            return (row[0], row[1], row[2])
    if abbreviation:
        row = conn.execute(
            text("SELECT id, name, abbreviation FROM units_of_measure WHERE LOWER(abbreviation) = LOWER(:abbr)"),
            {"abbr": abbreviation}
        ).fetchone()
        if row:
            return (row[0], row[1], row[2])
    return None


def _find_specific_container_uom(conn, container_name, size_qty, size_symbol):
    """Try to find a specific UOM like 'Can 12oz' or 'Bottle 750ml' in Inventory."""
    from sqlalchemy import text
    if not size_qty or not size_symbol:
        return None
    # Format size: integer if whole number (12, not 12.0)
    size_val = int(size_qty) if size_qty == int(size_qty) else size_qty
    # Try exact match: "Can 12oz", "Bottle 750ml"
    search_name = f"{container_name.title()} {size_val}{size_symbol}"
    row = conn.execute(
        text("SELECT id, name, abbreviation FROM units_of_measure WHERE LOWER(name) = LOWER(:name)"),
        {"name": search_name}
    ).fetchone()
    if row:
        return (row[0], row[1], row[2])
    # Try pattern with unit symbol: "Bottle 1L%" matches "Bottle 1Lt" but not "Bottle 187ml"
    pattern_with_unit = f"{container_name.title()} {size_val}{size_symbol}%"
    row = conn.execute(
        text("SELECT id, name, abbreviation FROM units_of_measure WHERE name ILIKE :pattern"),
        {"pattern": pattern_with_unit}
    ).fetchone()
    if row:
        return (row[0], row[1], row[2])
    # Try pattern without unit but with word boundary: "Can 12 %" (space after number)
    pattern_space = f"{container_name.title()} {size_val} %"
    row = conn.execute(
        text("SELECT id, name, abbreviation FROM units_of_measure WHERE name ILIKE :pattern"),
        {"pattern": pattern_space}
    ).fetchone()
    if row:
        return (row[0], row[1], row[2])
    return None


def _get_inventory_uom_lookup():
    """
    Fetch ALL active Inventory UOMs into a lookup dict.
    Keys: lowercase abbreviation and lowercase name.
    Values: (id, name, abbreviation) tuples.
    Used by sync and API response serialization.
    """
    from sqlalchemy import text, create_engine
    inventory_db_url = os.getenv(
        'INVENTORY_DATABASE_URL',
        'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
    )
    inv_engine = create_engine(inventory_db_url)
    lookup = {}
    with inv_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name, abbreviation FROM units_of_measure WHERE is_active = true")
        ).fetchall()
    for row in rows:
        if row[2]:
            lookup[row[2].lower()] = (row[0], row[1], row[2])
        if row[1]:
            lookup[row[1].lower()] = (row[0], row[1], row[2])
    return lookup


def _check_uom_sync_status(item, inv_uom_lookup):
    """
    Check if a vendor item's size unit maps to an Inventory UOM.
    Returns (uom_sync_ok, uom_sync_warning).
    """
    if not item.inventory_master_item_id:
        return None, None  # No master item linked — not applicable

    if not item.size_unit_id:
        return False, "No size unit set on vendor item"

    # Check if size unit symbol or name is in the lookup
    size_symbol = item.size_unit.symbol if item.size_unit else None
    size_name = item.size_unit.name if item.size_unit else None

    if size_symbol and size_symbol.lower() in inv_uom_lookup:
        return True, None
    if size_name and size_name.lower() in inv_uom_lookup:
        return True, None

    # Not found — report warning
    unit_label = size_symbol or size_name or f"unit_id={item.size_unit_id}"
    return False, f"Size unit '{unit_label}' not found in Inventory UOMs"


def sync_master_item_defaults(item, db) -> dict:
    """
    Sync category and primary UOM from vendor item to master item.
    Hub is the strict source of truth — NO fallback to "Each".

    UOM resolution (priority order):
    1. Container + size → specific Inventory UOM (e.g. "Can 16oz", "Bottle 750ml", "Keg 1/6 Barrel")
    2. Hub size unit symbol/name → Inventory UOM lookup (e.g. "lb" → Pound, "patty" → Patty)
    3. If no match → skip UOM sync entirely (log warning, don't touch master item's UOM)

    Container+size is checked first because the size unit symbol (e.g. "oz") describes
    the size of the container, not the counting unit. "Can 16oz" is more useful than "Ounce".

    When a UOM is resolved, always update the master item (even if already set)
    so that Hub corrections propagate.

    Returns dict with sync result: {"uom_synced": bool, "uom_warning": str|None}
    """
    if not item.inventory_master_item_id:
        return {"uom_synced": False, "uom_warning": None}

    from sqlalchemy import text, create_engine

    try:
        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)

        with inv_engine.connect() as conn:
            # Read current master item state
            master = conn.execute(
                text("SELECT id, category, primary_uom_id FROM master_items WHERE id = :id"),
                {"id": item.inventory_master_item_id}
            ).fetchone()

            if not master:
                logger.warning(f"Master item {item.inventory_master_item_id} not found in Inventory")
                return

            uom = None
            uom_from_container = False

            # Primary: try container+size for specific UOMs (e.g. "Can 16oz", "Bottle 750ml")
            if item.container_id and item.size_quantity and item.size_unit_id:
                container = db.execute(
                    text("SELECT name FROM hub_containers WHERE id = :id"),
                    {"id": item.container_id}
                ).fetchone()
                size_unit = db.execute(
                    text("SELECT symbol FROM hub_size_units WHERE id = :id"),
                    {"id": item.size_unit_id}
                ).fetchone()
                if container and size_unit:
                    uom = _find_specific_container_uom(
                        conn, container[0],
                        float(item.size_quantity),
                        size_unit[0]
                    )
                    if uom:
                        uom_from_container = True

            # Secondary: use Hub size unit symbol/name (e.g. "lb" → Pound, "patty" → Patty)
            if not uom and item.size_unit_id:
                size_unit = db.execute(
                    text("SELECT symbol, name FROM hub_size_units WHERE id = :id"),
                    {"id": item.size_unit_id}
                ).fetchone()
                if size_unit and size_unit[0]:
                    uom = _find_inventory_uom(conn, abbreviation=size_unit[0])
                    if not uom:
                        uom = _find_inventory_uom(conn, name=size_unit[1])

            existing_category = master[1]
            changes = []

            # Set category if NULL
            if not existing_category and item.category:
                conn.execute(
                    text("UPDATE master_items SET category = :category, updated_at = NOW() WHERE id = :id"),
                    {"id": item.inventory_master_item_id, "category": item.category}
                )
                changes.append(f"category='{item.category}'")

            # UOM sync: only if resolved (no fallback)
            if uom:
                uom_id, uom_name, uom_abbr = uom

                # Always update master item UOM when Hub resolves one (fixes propagate)
                conn.execute(
                    text("""UPDATE master_items
                            SET primary_uom_id = :uom_id, primary_uom_name = :uom_name,
                                primary_uom_abbr = :uom_abbr, updated_at = NOW()
                            WHERE id = :id"""),
                    {"id": item.inventory_master_item_id, "uom_id": uom_id,
                     "uom_name": uom_name, "uom_abbr": uom_abbr}
                )
                changes.append(f"primary_uom='{uom_name}'")

                # Update or create primary count unit record
                existing_cu = conn.execute(
                    text("""SELECT id, uom_id FROM master_item_count_units
                            WHERE master_item_id = :mid AND is_primary = true AND is_active = true"""),
                    {"mid": item.inventory_master_item_id}
                ).fetchone()

                if existing_cu:
                    if existing_cu[1] != uom_id:
                        # Check if another count unit already has this uom_id for this master item
                        conflict_cu = conn.execute(
                            text("""SELECT id FROM master_item_count_units
                                    WHERE master_item_id = :mid AND uom_id = :uom_id AND id != :cu_id"""),
                            {"mid": item.inventory_master_item_id, "uom_id": uom_id, "cu_id": existing_cu[0]}
                        ).fetchone()
                        if conflict_cu:
                            # Delete the conflicting non-primary row, then update the primary
                            conn.execute(
                                text("DELETE FROM master_item_count_units WHERE id = :id"),
                                {"id": conflict_cu[0]}
                            )
                        conn.execute(
                            text("""UPDATE master_item_count_units
                                    SET uom_id = :uom_id, uom_name = :uom_name, uom_abbreviation = :uom_abbr
                                    WHERE id = :cu_id"""),
                            {"cu_id": existing_cu[0], "uom_id": uom_id,
                             "uom_name": uom_name, "uom_abbr": uom_abbr}
                        )
                        changes.append(f"count_unit='{uom_name}'")
                else:
                    conn.execute(
                        text("""INSERT INTO master_item_count_units
                                (master_item_id, uom_id, uom_name, uom_abbreviation, is_primary,
                                 conversion_to_primary, display_order, is_active, created_at)
                                VALUES (:mid, :uom_id, :uom_name, :uom_abbr, true,
                                        1.0, 0, true, NOW())
                                ON CONFLICT (master_item_id, uom_id) DO NOTHING"""),
                        {"mid": item.inventory_master_item_id, "uom_id": uom_id,
                         "uom_name": uom_name, "uom_abbr": uom_abbr}
                    )
                    changes.append(f"count_unit='{uom_name}'")

                # If primary UOM is a container unit (e.g. Can 16oz, Bottle 750ml),
                # pack_to_primary_factor should be units_per_case (not units_per_case × size_qty).
                # Each container is one primary unit, so the factor is just how many per case.
                if uom_from_container and item.units_per_case:
                    correct_factor = float(item.units_per_case)
                    current_factor = float(item.pack_to_primary_factor or 0)
                    if current_factor != correct_factor:
                        item.pack_to_primary_factor = correct_factor
                        item.conversion_factor = correct_factor
                        changes.append(f"pack_to_primary_factor={correct_factor}")
            else:
                # No match — log warning, don't touch UOM
                size_info = ""
                size_symbol = ""
                if item.size_unit_id:
                    su = db.execute(
                        text("SELECT symbol, name FROM hub_size_units WHERE id = :id"),
                        {"id": item.size_unit_id}
                    ).fetchone()
                    size_symbol = su[0] if su else 'unknown'
                    size_info = f" (size_unit: {size_symbol})"
                logger.warning(
                    f"Could not resolve UOM for vendor item {item.id}{size_info} "
                    f"→ master item {item.inventory_master_item_id} UOM unchanged"
                )

                conn.commit()
                if changes:
                    logger.info(f"Synced defaults to master item {item.inventory_master_item_id}: {', '.join(changes)}")
                return {
                    "uom_synced": False,
                    "uom_warning": f"No matching Inventory UOM for size unit \"{size_symbol}\". "
                                   f"Create a \"{size_symbol.title()}\" UOM in Inventory Settings → Units of Measure, then re-save."
                }

            conn.commit()

            if changes:
                logger.info(f"Synced defaults to master item {item.inventory_master_item_id}: {', '.join(changes)}")

            return {"uom_synced": True, "uom_warning": None}

    except Exception as e:
        logger.error(f"Error syncing master item defaults: {str(e)}")
        return {"uom_synced": False, "uom_warning": f"Sync error: {str(e)}"}


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class UOMResponse(BaseModel):
    """Unit of measure response"""
    id: int
    name: str
    abbreviation: str

    class Config:
        from_attributes = True


class VendorItemCreate(BaseModel):
    """Create vendor item request"""
    vendor_id: int
    inventory_master_item_id: Optional[int] = None
    inventory_master_item_name: Optional[str] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: str
    vendor_description: Optional[str] = None
    purchase_unit_id: int = 1  # Default to "Each"
    purchase_unit_name: Optional[str] = None
    purchase_unit_abbr: Optional[str] = None
    pack_size: Optional[str] = None
    conversion_factor: float = 1.0
    conversion_unit_id: Optional[int] = None
    unit_price: Optional[float] = None
    category: Optional[str] = None
    gl_asset_account: Optional[int] = None
    gl_cogs_account: Optional[int] = None
    gl_waste_account: Optional[int] = None
    is_active: bool = True
    is_preferred: bool = False
    notes: Optional[str] = None


class VendorItemUpdate(BaseModel):
    """Update vendor item request"""
    # Identity
    vendor_id: Optional[int] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: Optional[str] = None
    vendor_description: Optional[str] = None

    # Backbar-style Size Fields (NEW)
    size_quantity: Optional[float] = None  # e.g., 1, 750, 25
    size_unit_id: Optional[int] = None  # FK to hub_size_units
    container_id: Optional[int] = None  # FK to hub_containers
    units_per_case: Optional[int] = None  # How many units in a case
    case_cost: Optional[float] = None  # Cost per case from invoice

    # Purchasing Definition (DEPRECATED - kept for migration)
    purchase_unit_id: Optional[int] = None
    purchase_unit_name: Optional[str] = None
    purchase_unit_abbr: Optional[str] = None
    pack_size: Optional[str] = None
    unit_uom_id: Optional[int] = None  # DEPRECATED: Use size_unit_id + container_id
    unit_uom_name: Optional[str] = None  # DEPRECATED
    pack_to_primary_factor: Optional[float] = None  # DEPRECATED: Use units_per_case
    conversion_factor: Optional[float] = None  # DEPRECATED
    conversion_unit_id: Optional[int] = None  # DEPRECATED

    # Pricing
    last_purchase_price: Optional[float] = None  # New: current price
    unit_price: Optional[float] = None  # Deprecated alias
    minimum_order_quantity: Optional[float] = None

    # Mapping & Classification
    inventory_master_item_id: Optional[int] = None
    inventory_master_item_name: Optional[str] = None
    category: Optional[str] = None
    gl_asset_account: Optional[int] = None
    gl_cogs_account: Optional[int] = None
    gl_waste_account: Optional[int] = None

    # Status
    is_active: Optional[bool] = None
    is_preferred: Optional[bool] = None
    notes: Optional[str] = None


class VendorItemResponse(BaseModel):
    """Vendor item response schema"""
    id: int
    vendor_id: int
    vendor_name: Optional[str] = None
    inventory_vendor_id: Optional[int] = None  # Inventory's vendor ID for dropdown mapping
    inventory_master_item_id: Optional[int] = None
    inventory_master_item_name: Optional[str] = None

    # Vendor-specific details
    vendor_sku: Optional[str] = None
    vendor_product_name: str
    vendor_description: Optional[str] = None

    # Backbar-style Size Fields (NEW)
    size_quantity: Optional[float] = None  # e.g., 1, 750, 25
    size_unit_id: Optional[int] = None  # FK to hub_size_units
    size_unit_symbol: Optional[str] = None  # e.g., "L", "ml", "lb"
    size_unit_measure_type: Optional[str] = None  # e.g., "weight", "volume", "count"
    container_id: Optional[int] = None  # FK to hub_containers
    container_name: Optional[str] = None  # e.g., "bottle", "can", "bag"
    size_display: Optional[str] = None  # Formatted: "1 L bottle"
    units_per_case: Optional[int] = None  # How many units in a case
    case_cost: Optional[float] = None  # Cost per case from invoice
    unit_cost: Optional[float] = None  # Calculated: case_cost / units_per_case

    # Purchase unit and conversion (DEPRECATED - kept for migration)
    purchase_unit_id: Optional[int] = None
    purchase_unit_name: Optional[str] = None
    purchase_unit_abbr: Optional[str] = None
    pack_size: Optional[str] = None
    unit_uom_id: Optional[int] = None  # DEPRECATED: Use size_unit_id + container_id
    unit_uom_name: Optional[str] = None  # DEPRECATED
    pack_to_primary_factor: Optional[float] = None  # DEPRECATED: Use units_per_case
    conversion_factor: Optional[float] = None  # DEPRECATED
    conversion_unit_id: Optional[int] = None  # DEPRECATED

    # Pricing
    last_purchase_price: Optional[float] = None  # Current price per purchase unit
    previous_purchase_price: Optional[float] = None  # Previous price
    unit_price: Optional[float] = None  # Deprecated alias
    last_price: Optional[float] = None  # Deprecated alias
    minimum_order_quantity: Optional[float] = None

    # Category and GL
    category: Optional[str] = None
    gl_asset_account: Optional[int] = None
    gl_cogs_account: Optional[int] = None
    gl_waste_account: Optional[int] = None

    # Status
    status: Optional[str] = None  # 'active', 'needs_review', 'inactive'
    is_active: bool = True
    is_preferred: bool = False
    notes: Optional[str] = None

    # Sync info
    inventory_vendor_item_id: Optional[int] = None
    synced_to_inventory: bool = False

    # UOM completeness (for validation warnings)
    uom_complete: Optional[bool] = None
    uom_missing_fields: Optional[List[str]] = None

    # UOM sync status (does Hub size unit map to an Inventory UOM?)
    uom_sync_ok: Optional[bool] = None  # True=maps, False=no match, None=no master item
    uom_sync_warning: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VendorItemListResponse(BaseModel):
    """Paginated vendor item list"""
    items: List[VendorItemResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/", response_model=VendorItemListResponse)
async def list_vendor_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=2000),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    master_item_id: Optional[int] = Query(None, description="Filter by master item"),
    search: Optional[str] = Query(None, description="Search by SKU or name"),
    status: Optional[str] = Query(None, description="Filter by status (active, needs_review, inactive)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status (deprecated, use status)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    exclude_expense_only: Optional[bool] = Query(None, description="Exclude items with no inventory link (expense-only items)"),
    mapped_only: Optional[bool] = Query(None, description="Only show items mapped to master items"),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of vendor items from Hub database.

    Supports filtering by:
    - vendor_id: Hub vendor ID
    - location_id: Location ID (for location-aware queries)
    - status: Review status (active, needs_review, inactive)
    - category: Product category
    - search: SKU or product name
    """
    query = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor),
        joinedload(HubVendorItem.size_unit),
        joinedload(HubVendorItem.container)
    )

    # Apply filters
    if vendor_id:
        query = query.filter(HubVendorItem.vendor_id == vendor_id)

    if location_id:
        query = query.filter(HubVendorItem.location_id == location_id)

    if master_item_id:
        query = query.filter(HubVendorItem.inventory_master_item_id == master_item_id)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                HubVendorItem.vendor_sku.ilike(search_pattern),
                HubVendorItem.vendor_product_name.ilike(search_pattern)
            )
        )

    # Status filter (new)
    if status:
        try:
            status_enum = VendorItemStatus(status)
            query = query.filter(HubVendorItem.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Legacy is_active filter (deprecated)
    if is_active is not None:
        query = query.filter(HubVendorItem.is_active == is_active)

    if category:
        query = query.filter(HubVendorItem.category.ilike(f"%{category}%"))

    # Exclude expense-only items (items with no inventory link)
    if exclude_expense_only:
        query = query.filter(HubVendorItem.inventory_master_item_id.isnot(None))

    # Only mapped items (same as exclude_expense_only but more explicit)
    if mapped_only:
        query = query.filter(HubVendorItem.inventory_master_item_id.isnot(None))

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    items = query.order_by(HubVendorItem.vendor_product_name).offset(offset).limit(page_size).all()

    # Build UOM sync lookup once for all items
    try:
        inv_uom_lookup = _get_inventory_uom_lookup()
    except Exception:
        inv_uom_lookup = {}

    # Build response
    result_items = []
    for item in items:
        uom_check = check_uom_completeness(item)
        uom_sync_ok, uom_sync_warning = _check_uom_sync_status(item, inv_uom_lookup)
        result_items.append(VendorItemResponse(
            id=item.id,
            vendor_id=item.vendor_id,
            vendor_name=item.vendor.name if item.vendor else None,
            inventory_vendor_id=item.vendor.inventory_vendor_id if item.vendor else None,
            inventory_master_item_id=item.inventory_master_item_id,
            inventory_master_item_name=item.inventory_master_item_name,
            vendor_sku=item.vendor_sku,
            vendor_product_name=item.vendor_product_name,
            vendor_description=item.vendor_description,
            # Backbar-style size fields (NEW)
            size_quantity=float(item.size_quantity) if item.size_quantity else None,
            size_unit_id=item.size_unit_id,
            size_unit_symbol=item.size_unit.symbol if item.size_unit else None,
            size_unit_measure_type=item.size_unit.measure_type if item.size_unit else None,
            container_id=item.container_id,
            container_name=item.container.name if item.container else None,
            size_display=item.size_display,
            units_per_case=item.units_per_case,
            case_cost=float(item.case_cost) if item.case_cost else None,
            unit_cost=item.unit_cost,
            # Deprecated fields (kept for migration)
            purchase_unit_id=item.purchase_unit_id,
            purchase_unit_name=item.purchase_unit_name,
            purchase_unit_abbr=item.purchase_unit_abbr,
            pack_size=item.pack_size,
            pack_to_primary_factor=float(item.pack_to_primary_factor) if item.pack_to_primary_factor else 1.0,
            conversion_factor=float(item.conversion_factor) if item.conversion_factor else 1.0,
            conversion_unit_id=item.conversion_unit_id,
            last_purchase_price=float(item.last_purchase_price) if item.last_purchase_price else None,
            previous_purchase_price=float(item.previous_purchase_price) if item.previous_purchase_price else None,
            unit_price=float(item.unit_price) if item.unit_price else None,
            last_price=float(item.last_price) if item.last_price else None,
            minimum_order_quantity=float(item.minimum_order_quantity) if item.minimum_order_quantity else None,
            category=item.category,
            gl_asset_account=item.gl_asset_account,
            gl_cogs_account=item.gl_cogs_account,
            gl_waste_account=item.gl_waste_account,
            status=item.status.value if item.status else 'active',
            is_active=item.is_active,
            is_preferred=item.is_preferred,
            notes=item.notes,
            inventory_vendor_item_id=item.inventory_vendor_item_id,
            synced_to_inventory=item.synced_to_inventory,
            # UOM completeness
            uom_complete=uom_check['is_complete'],
            uom_missing_fields=uom_check['missing_fields'],
            # UOM sync status
            uom_sync_ok=uom_sync_ok,
            uom_sync_warning=uom_sync_warning,
            created_at=item.created_at,
            updated_at=item.updated_at
        ))

    return VendorItemListResponse(
        items=result_items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("/", response_model=VendorItemResponse)
async def create_vendor_item(
    item_data: VendorItemCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new vendor item in Hub database.
    """
    from sqlalchemy.exc import IntegrityError

    try:
        # Verify vendor exists
        vendor = db.query(Vendor).filter(Vendor.id == item_data.vendor_id).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

        # Verify purchase unit exists if provided
        if item_data.purchase_unit_id:
            purchase_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == item_data.purchase_unit_id).first()
            if not purchase_unit:
                raise HTTPException(status_code=400, detail=f"Purchase unit with ID {item_data.purchase_unit_id} not found")

        # Check for duplicate (vendor_id + vendor_sku + location_id)
        if item_data.vendor_sku:
            existing = db.query(HubVendorItem).filter(
                HubVendorItem.vendor_id == item_data.vendor_id,
                HubVendorItem.vendor_sku == item_data.vendor_sku,
                HubVendorItem.location_id == None  # New items don't have location_id set
            ).first()
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"A vendor item with SKU '{item_data.vendor_sku}' already exists for this vendor"
                )

        # Create the vendor item
        item = HubVendorItem(
            vendor_id=item_data.vendor_id,
            inventory_master_item_id=item_data.inventory_master_item_id,
            inventory_master_item_name=item_data.inventory_master_item_name,
            vendor_sku=item_data.vendor_sku,
            vendor_product_name=item_data.vendor_product_name,
            vendor_description=item_data.vendor_description,
            purchase_unit_id=item_data.purchase_unit_id,
            purchase_unit_name=item_data.purchase_unit_name,
            purchase_unit_abbr=item_data.purchase_unit_abbr,
            pack_size=item_data.pack_size,
            conversion_factor=item_data.conversion_factor,
            conversion_unit_id=item_data.conversion_unit_id,
            unit_price=item_data.unit_price,
            category=item_data.category,
            gl_asset_account=item_data.gl_asset_account,
            gl_cogs_account=item_data.gl_cogs_account,
            gl_waste_account=item_data.gl_waste_account,
            is_active=item_data.is_active,
            is_preferred=item_data.is_preferred,
            notes=item_data.notes
        )

        try:
            db.add(item)
            db.commit()
            db.refresh(item)
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            logger.error(f"IntegrityError creating vendor item: {error_msg}")
            if 'uq_vendor_item_location' in error_msg or 'duplicate' in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="A vendor item with this SKU already exists for this vendor"
                )
            elif 'foreign key' in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Invalid reference: purchase unit or other linked record not found"
                )
            raise HTTPException(status_code=400, detail=f"Database error: {error_msg}")

        logger.info(f"Created vendor item {item.id}: {item.vendor_product_name}")

        # Sync to Inventory
        sync_result = await sync_vendor_item_to_inventory(item, vendor, action="sync")
        if sync_result:
            item.synced_to_inventory = True
            if sync_result.get("inventory_vendor_item_id"):
                item.inventory_vendor_item_id = sync_result["inventory_vendor_item_id"]
            db.commit()
            db.refresh(item)

        return VendorItemResponse(
            id=item.id,
            vendor_id=item.vendor_id,
            vendor_name=vendor.name,
            inventory_vendor_id=vendor.inventory_vendor_id if vendor else None,
            inventory_master_item_id=item.inventory_master_item_id,
            inventory_master_item_name=item.inventory_master_item_name,
            vendor_sku=item.vendor_sku,
            vendor_product_name=item.vendor_product_name,
            vendor_description=item.vendor_description,
            purchase_unit_id=item.purchase_unit_id,
            purchase_unit_name=item.purchase_unit_name,
            purchase_unit_abbr=item.purchase_unit_abbr,
            pack_size=item.pack_size,
            conversion_factor=float(item.conversion_factor) if item.conversion_factor else 1.0,
            conversion_unit_id=item.conversion_unit_id,
            unit_price=float(item.unit_price) if item.unit_price else None,
            last_price=float(item.last_price) if item.last_price else None,
            category=item.category,
            gl_asset_account=item.gl_asset_account,
            gl_cogs_account=item.gl_cogs_account,
            gl_waste_account=item.gl_waste_account,
            is_active=item.is_active,
            is_preferred=item.is_preferred,
            inventory_vendor_item_id=item.inventory_vendor_item_id,
            synced_to_inventory=item.synced_to_inventory,
            created_at=item.created_at,
            updated_at=item.updated_at
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Unexpected error creating vendor item: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating vendor item: {str(e)}")


@router.get("/master-items")
async def get_master_items_from_inventory():
    """
    Fetch master items from Inventory database for mapping dropdown.

    Direct database connection to Inventory for reliability.
    Must be defined before /{vendor_item_id} to avoid route conflict.
    """
    from sqlalchemy import create_engine, text as sql_text

    inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')

    try:
        engine = create_engine(inventory_db_url)
        with engine.connect() as conn:
            results = conn.execute(
                sql_text("SELECT id, name, category FROM master_items WHERE is_active = true ORDER BY name LIMIT 2000")
            ).fetchall()
            return [{"id": row[0], "name": row[1], "category": row[2]} for row in results]

    except Exception as e:
        logger.error(f"Error fetching master items from Inventory DB: {str(e)}")
        return []


# ============================================================================
# CATEGORY CONFLICT DETECTION ENDPOINTS
# Must be defined before /{vendor_item_id} to avoid route conflict
# ============================================================================

class CategoryConflict(BaseModel):
    """Category conflict information"""
    master_item_id: int
    master_item_name: str
    master_item_category: Optional[str] = None
    vendor_items: List[dict]
    unique_categories: List[str]
    conflict_count: int


class CategoryConflictResponse(BaseModel):
    """Response for category conflict check"""
    conflicts: List[CategoryConflict]
    total_conflicts: int
    total_master_items_checked: int


@router.get("/category-conflicts", response_model=CategoryConflictResponse)
async def check_category_conflicts(
    db: Session = Depends(get_db)
):
    """
    Check for category conflicts across vendor items.

    Returns master items that have vendor items with different categories.
    This indicates a data inconsistency that needs manual resolution.

    Hub is the source of truth for categories, so when a master item has
    multiple vendor items with different categories, it's a conflict that
    needs human review.
    """
    from sqlalchemy import text

    # Find master items with multiple distinct categories across their vendor items
    conflict_query = text("""
        WITH vendor_item_categories AS (
            SELECT
                inventory_master_item_id,
                inventory_master_item_name,
                category,
                id as vendor_item_id,
                vendor_product_name,
                vendor_id
            FROM hub_vendor_items
            WHERE inventory_master_item_id IS NOT NULL
              AND is_active = true
        ),
        category_counts AS (
            SELECT
                inventory_master_item_id,
                inventory_master_item_name,
                COUNT(DISTINCT category) as unique_category_count,
                STRING_AGG(DISTINCT category, ', ' ORDER BY category) as categories
            FROM vendor_item_categories
            GROUP BY inventory_master_item_id, inventory_master_item_name
            HAVING COUNT(DISTINCT category) > 1
        )
        SELECT
            cc.inventory_master_item_id,
            cc.inventory_master_item_name,
            cc.unique_category_count,
            cc.categories
        FROM category_counts cc
        ORDER BY cc.unique_category_count DESC, cc.inventory_master_item_name
    """)

    try:
        results = db.execute(conflict_query).fetchall()

        conflicts = []
        for row in results:
            master_item_id = row[0]
            master_item_name = row[1]
            unique_count = row[2]
            categories_str = row[3]

            # Get the actual vendor items for this master item
            vendor_items = db.query(HubVendorItem).filter(
                HubVendorItem.inventory_master_item_id == master_item_id,
                HubVendorItem.is_active == True
            ).all()

            vendor_item_details = [
                {
                    "id": vi.id,
                    "vendor_id": vi.vendor_id,
                    "vendor_name": vi.vendor.name if vi.vendor else None,
                    "vendor_product_name": vi.vendor_product_name,
                    "category": vi.category
                }
                for vi in vendor_items
            ]

            # Get unique categories as list
            unique_categories = [c.strip() for c in categories_str.split(', ')] if categories_str else []

            # Fetch master item's current category from Inventory
            master_item_category = None
            try:
                from sqlalchemy import create_engine
                inventory_db_url = os.getenv(
                    'INVENTORY_DATABASE_URL',
                    'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
                )
                inv_engine = create_engine(inventory_db_url)
                with inv_engine.connect() as conn:
                    mi_result = conn.execute(
                        text("SELECT category FROM master_items WHERE id = :id"),
                        {"id": master_item_id}
                    ).fetchone()
                    if mi_result:
                        master_item_category = mi_result[0]
            except Exception as e:
                logger.warning(f"Could not fetch master item category: {e}")

            conflicts.append(CategoryConflict(
                master_item_id=master_item_id,
                master_item_name=master_item_name or "Unknown",
                master_item_category=master_item_category,
                vendor_items=vendor_item_details,
                unique_categories=unique_categories,
                conflict_count=unique_count
            ))

        # Count total master items with vendor items
        total_query = text("""
            SELECT COUNT(DISTINCT inventory_master_item_id)
            FROM hub_vendor_items
            WHERE inventory_master_item_id IS NOT NULL
              AND is_active = true
        """)
        total_checked = db.execute(total_query).scalar() or 0

        return CategoryConflictResponse(
            conflicts=conflicts,
            total_conflicts=len(conflicts),
            total_master_items_checked=total_checked
        )

    except Exception as e:
        logger.error(f"Error checking category conflicts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error checking category conflicts: {str(e)}")


@router.get("/category-summary")
async def get_category_summary(
    db: Session = Depends(get_db)
):
    """
    Get summary of categories across vendor items and master items.

    Shows:
    - Total vendor items by category
    - Master items linked to vendor items by category
    - Any mismatches between vendor item and master item categories
    """
    from sqlalchemy import text, create_engine

    # Get vendor item category distribution
    vi_query = text("""
        SELECT
            COALESCE(category, 'Uncategorized') as category,
            COUNT(*) as vendor_item_count,
            COUNT(DISTINCT inventory_master_item_id) as master_item_count
        FROM hub_vendor_items
        WHERE is_active = true
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY vendor_item_count DESC
    """)

    vi_results = db.execute(vi_query).fetchall()

    vendor_item_categories = [
        {
            "category": row[0],
            "vendor_item_count": row[1],
            "linked_master_item_count": row[2]
        }
        for row in vi_results
    ]

    # Get master item category distribution from Inventory
    master_item_categories = []
    try:
        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)
        with inv_engine.connect() as conn:
            mi_results = conn.execute(text("""
                SELECT
                    COALESCE(category, 'Uncategorized') as category,
                    COUNT(*) as count
                FROM master_items
                WHERE is_active = true
                GROUP BY COALESCE(category, 'Uncategorized')
                ORDER BY count DESC
            """)).fetchall()

            master_item_categories = [
                {"category": row[0], "count": row[1]}
                for row in mi_results
            ]
    except Exception as e:
        logger.warning(f"Could not fetch master item categories: {e}")

    return {
        "vendor_item_categories": vendor_item_categories,
        "master_item_categories": master_item_categories,
        "total_vendor_items": sum(c["vendor_item_count"] for c in vendor_item_categories),
        "total_master_items": sum(c["count"] for c in master_item_categories)
    }


@router.post("/sync-all-master-item-categories")
async def sync_all_master_item_categories(
    dry_run: bool = Query(True, description="If true, only report what would change without making changes"),
    db: Session = Depends(get_db)
):
    """
    Sync all master item categories from their vendor items.

    For each master item that has vendor items (and no category conflicts),
    updates the master item's category to match the vendor item's category.

    Hub is the source of truth for categories.

    Use dry_run=true (default) to see what would change without making changes.
    Set dry_run=false to actually apply the changes.
    """
    from sqlalchemy import text, create_engine

    # Get vendor item categories for each master item (only where there's no conflict)
    category_query = text("""
        WITH vendor_categories AS (
            SELECT
                inventory_master_item_id,
                MAX(inventory_master_item_name) as master_item_name,
                MAX(category) as category,
                COUNT(DISTINCT category) as unique_categories
            FROM hub_vendor_items
            WHERE inventory_master_item_id IS NOT NULL
              AND is_active = true
              AND category IS NOT NULL
            GROUP BY inventory_master_item_id
            HAVING COUNT(DISTINCT category) = 1
        )
        SELECT
            inventory_master_item_id,
            master_item_name,
            category
        FROM vendor_categories
        ORDER BY inventory_master_item_id
    """)

    try:
        results = db.execute(category_query).fetchall()

        # Get master item categories from Inventory for comparison
        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)

        updates = []
        already_correct = 0
        updated = 0

        with inv_engine.connect() as conn:
            for row in results:
                master_item_id = row[0]
                master_item_name = row[1]
                vendor_category = row[2]

                # Get current master item category
                mi_result = conn.execute(
                    text("SELECT category FROM master_items WHERE id = :id"),
                    {"id": master_item_id}
                ).fetchone()

                if not mi_result:
                    continue

                current_category = mi_result[0]

                if current_category == vendor_category:
                    already_correct += 1
                    continue

                updates.append({
                    "master_item_id": master_item_id,
                    "master_item_name": master_item_name,
                    "old_category": current_category,
                    "new_category": vendor_category
                })

                if not dry_run:
                    conn.execute(
                        text("UPDATE master_items SET category = :category, updated_at = NOW() WHERE id = :id"),
                        {"id": master_item_id, "category": vendor_category}
                    )
                    updated += 1

            if not dry_run:
                conn.commit()

        return {
            "dry_run": dry_run,
            "total_master_items_with_vendor_items": len(results),
            "already_correct": already_correct,
            "updates_needed": len(updates),
            "updates_applied": updated if not dry_run else 0,
            "updates": updates[:50]  # Limit response size
        }

    except Exception as e:
        logger.error(f"Error syncing master item categories: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error syncing categories: {str(e)}")


@router.post("/sync-master-item-category/{master_item_id}")
async def sync_master_item_category(
    master_item_id: int,
    category: str = Query(..., description="Category to set on master item"),
    db: Session = Depends(get_db)
):
    """
    Sync a master item's category from its vendor items.

    This endpoint updates the master item's category in Inventory to match
    the specified category from its vendor items.

    Use this after resolving category conflicts to set the correct category.
    """
    from sqlalchemy import text, create_engine

    # Verify the master item has vendor items with this category
    vendor_items = db.query(HubVendorItem).filter(
        HubVendorItem.inventory_master_item_id == master_item_id,
        HubVendorItem.category == category,
        HubVendorItem.is_active == True
    ).all()

    if not vendor_items:
        raise HTTPException(
            status_code=400,
            detail=f"No active vendor items found for master item {master_item_id} with category '{category}'"
        )

    # Update master item in Inventory
    try:
        inventory_db_url = os.getenv(
            'INVENTORY_DATABASE_URL',
            'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
        )
        inv_engine = create_engine(inventory_db_url)
        with inv_engine.connect() as conn:
            # Get current category first
            current = conn.execute(
                text("SELECT category FROM master_items WHERE id = :id"),
                {"id": master_item_id}
            ).fetchone()

            if not current:
                raise HTTPException(status_code=404, detail=f"Master item {master_item_id} not found")

            old_category = current[0]

            # Update category
            conn.execute(
                text("UPDATE master_items SET category = :category, updated_at = NOW() WHERE id = :id"),
                {"id": master_item_id, "category": category}
            )
            conn.commit()

            logger.info(f"Updated master item {master_item_id} category from '{old_category}' to '{category}'")

            return {
                "success": True,
                "master_item_id": master_item_id,
                "old_category": old_category,
                "new_category": category,
                "vendor_items_count": len(vendor_items)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing master item category: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error syncing category: {str(e)}")


@router.post("/sync-master-item-name/{master_item_id}")
async def sync_master_item_name(
    master_item_id: int,
    name: str = Query(..., description="New name for the master item"),
    db: Session = Depends(get_db)
):
    """
    Sync a master item's name to all related vendor items in Hub.

    This endpoint updates the cached `inventory_master_item_name` field
    on all vendor items mapped to this master item.

    Called by Inventory when a master item is renamed.
    """
    # Update all vendor items with this master item ID
    updated = db.query(HubVendorItem).filter(
        HubVendorItem.inventory_master_item_id == master_item_id
    ).update({
        HubVendorItem.inventory_master_item_name: name
    })

    db.commit()

    logger.info(f"Updated cached name for master item {master_item_id} to '{name}' on {updated} vendor items")

    return {
        "success": True,
        "master_item_id": master_item_id,
        "new_name": name,
        "vendor_items_updated": updated
    }


@router.get("/{vendor_item_id}", response_model=VendorItemResponse)
async def get_vendor_item(
    vendor_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific vendor item by ID.
    """
    item = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor),
        joinedload(HubVendorItem.size_unit),
        joinedload(HubVendorItem.container)
    ).filter(HubVendorItem.id == vendor_item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    uom_check = check_uom_completeness(item)
    try:
        inv_uom_lookup = _get_inventory_uom_lookup()
    except Exception:
        inv_uom_lookup = {}
    uom_sync_ok, uom_sync_warning = _check_uom_sync_status(item, inv_uom_lookup)

    return VendorItemResponse(
        id=item.id,
        vendor_id=item.vendor_id,
        vendor_name=item.vendor.name if item.vendor else None,
        inventory_vendor_id=item.vendor.inventory_vendor_id if item.vendor else None,
        inventory_master_item_id=item.inventory_master_item_id,
        inventory_master_item_name=item.inventory_master_item_name,
        vendor_sku=item.vendor_sku,
        vendor_product_name=item.vendor_product_name,
        vendor_description=item.vendor_description,
        # Backbar-style size fields
        size_quantity=float(item.size_quantity) if item.size_quantity else None,
        size_unit_id=item.size_unit_id,
        size_unit_symbol=item.size_unit.symbol if item.size_unit else None,
        container_id=item.container_id,
        container_name=item.container.name if item.container else None,
        size_display=item.size_display,
        units_per_case=item.units_per_case,
        case_cost=float(item.case_cost) if item.case_cost else None,
        unit_cost=item.unit_cost,
        # Deprecated fields (kept for migration)
        purchase_unit_id=item.purchase_unit_id,
        purchase_unit_name=item.purchase_unit_name,
        purchase_unit_abbr=item.purchase_unit_abbr,
        pack_size=item.pack_size,
        unit_uom_id=item.unit_uom_id,
        unit_uom_name=item.unit_uom_name,
        pack_to_primary_factor=float(item.pack_to_primary_factor) if item.pack_to_primary_factor else 1.0,
        conversion_factor=float(item.conversion_factor) if item.conversion_factor else 1.0,
        conversion_unit_id=item.conversion_unit_id,
        last_purchase_price=float(item.last_purchase_price) if item.last_purchase_price else None,
        previous_purchase_price=float(item.previous_purchase_price) if item.previous_purchase_price else None,
        unit_price=float(item.unit_price) if item.unit_price else None,
        last_price=float(item.last_price) if item.last_price else None,
        minimum_order_quantity=float(item.minimum_order_quantity) if item.minimum_order_quantity else None,
        category=item.category,
        gl_asset_account=item.gl_asset_account,
        gl_cogs_account=item.gl_cogs_account,
        gl_waste_account=item.gl_waste_account,
        status=item.status.value if hasattr(item.status, 'value') else (item.status or 'active'),
        is_active=item.is_active,
        is_preferred=item.is_preferred,
        notes=item.notes,
        inventory_vendor_item_id=item.inventory_vendor_item_id,
        synced_to_inventory=item.synced_to_inventory if item.synced_to_inventory is not None else False,
        # UOM completeness
        uom_complete=uom_check['is_complete'],
        uom_missing_fields=uom_check['missing_fields'],
        # UOM sync status
        uom_sync_ok=uom_sync_ok,
        uom_sync_warning=uom_sync_warning,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.put("/{vendor_item_id}", response_model=VendorItemResponse)
@router.patch("/{vendor_item_id}", response_model=VendorItemResponse)
async def update_vendor_item(
    vendor_item_id: int,
    item_data: VendorItemUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a vendor item.
    """
    item = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor),
        joinedload(HubVendorItem.size_unit),
        joinedload(HubVendorItem.container)
    ).filter(HubVendorItem.id == vendor_item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Save original status for auto-approval check
    original_status = item.status

    # Update fields
    update_data = item_data.dict(exclude_unset=True)

    # Track price changes (support both old and new field names)
    if "last_purchase_price" in update_data and update_data["last_purchase_price"] is not None:
        if item.last_purchase_price is not None:
            item.previous_purchase_price = item.last_purchase_price
        item.price_updated_at = get_now()
    elif "unit_price" in update_data and update_data["unit_price"] is not None:
        if item.unit_price is not None:
            item.last_price = item.unit_price
        item.price_updated_at = get_now()

    for field, value in update_data.items():
        setattr(item, field, value)

    # Auto-calculate pack_to_primary_factor from size fields
    # pack_to_primary_factor = units_per_case × size_quantity (for weight/count items)
    # For volume items (ml, L), size_quantity is descriptive only → ptpf = units_per_case
    size_fields = {"units_per_case", "size_quantity", "size_unit_id"}
    if size_fields & set(update_data.keys()):
        upc = float(item.units_per_case or 1)
        sq = float(item.size_quantity or 1)
        # Check measure_type from size_unit
        multiply_size = False
        if item.size_unit_id:
            from integration_hub.models.size_unit import SizeUnit as SU
            su = db.query(SU).filter(SU.id == item.size_unit_id).first()
            if su and su.measure_type in ('weight', 'count'):
                multiply_size = True
        if multiply_size and sq > 1:
            item.pack_to_primary_factor = upc * sq
        else:
            item.pack_to_primary_factor = upc
        # Keep conversion_factor in sync (legacy field)
        item.conversion_factor = item.pack_to_primary_factor

    db.commit()
    db.refresh(item)

    # Cascade SKU/name changes to all mapped invoice items
    if "vendor_sku" in update_data or "vendor_product_name" in update_data:
        from sqlalchemy import text as sql_text
        cascade_fields = []
        cascade_params = {"vi_id": vendor_item_id}
        if "vendor_sku" in update_data and item.vendor_sku:
            cascade_fields.append("item_code = :sku")
            cascade_params["sku"] = item.vendor_sku
        if "vendor_product_name" in update_data and item.vendor_product_name:
            cascade_fields.append("item_description = :name")
            cascade_params["name"] = item.vendor_product_name
        if cascade_fields:
            result = db.execute(sql_text(f"""
                UPDATE hub_invoice_items
                SET {', '.join(cascade_fields)}
                WHERE inventory_item_id = :vi_id AND is_mapped = true
            """), cascade_params)
            if result.rowcount > 0:
                db.commit()
                logger.info(f"Cascaded vendor item {vendor_item_id} changes to {result.rowcount} invoice items")

    # Reload relationships after update
    db.refresh(item)
    if item.size_unit_id:
        from integration_hub.models.size_unit import SizeUnit
        item.size_unit = db.query(SizeUnit).filter(SizeUnit.id == item.size_unit_id).first()
    if item.container_id:
        from integration_hub.models.container import Container
        item.container = db.query(Container).filter(Container.id == item.container_id).first()

    logger.info(f"Updated vendor item {item.id}")

    # Auto-approve if item was needs_review and UOM is now complete
    if original_status == VendorItemStatus.needs_review:
        uom_check = check_uom_completeness(item)
        if uom_check['is_complete']:
            item.status = VendorItemStatus.active
            db.commit()
            db.refresh(item)
            logger.info(f"Auto-approved vendor item {item.id} - UOM is now complete")

    # Sync category, primary UOM, and count unit to master item
    sync_warning = None
    if item.inventory_master_item_id:
        trigger_fields = {"inventory_master_item_id", "size_unit_id", "size_quantity", "category", "container_id"}
        if trigger_fields & set(update_data.keys()):
            sync_result = sync_master_item_defaults(item, db)
            if sync_result and not sync_result.get("uom_synced"):
                sync_warning = sync_result.get("uom_warning")

    # Auto-create bottle conversion for volume items (used by item_detail.html UI)
    if "inventory_master_item_id" in update_data and item.inventory_master_item_id and item.size_quantity and item.size_unit_id:
        try:
            from sqlalchemy import text, create_engine
            from integration_hub.models.size_unit import SizeUnit

            size_unit = db.query(SizeUnit).filter(SizeUnit.id == item.size_unit_id).first()
            if size_unit and size_unit.conversion_to_inventory_unit and size_unit.measure_type == "volume":
                fl_oz_amount = float(item.size_quantity) * float(size_unit.conversion_to_inventory_unit)

                inventory_db_url = os.getenv(
                    "INVENTORY_DATABASE_URL",
                    "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
                )
                inv_engine = create_engine(inventory_db_url)
                with inv_engine.connect() as conn:
                    existing = conn.execute(
                        text("""SELECT id FROM item_unit_conversions
                                WHERE master_item_id = :master_item_id
                                AND from_unit_id = 15 AND to_unit_id = 7"""),
                        {"master_item_id": item.inventory_master_item_id}
                    ).fetchone()

                    if not existing:
                        conn.execute(
                            text("""INSERT INTO item_unit_conversions
                                    (master_item_id, from_unit_id, from_unit_name, from_unit_abbr,
                                     to_unit_id, to_unit_name, to_unit_abbr, conversion_factor,
                                     is_active, created_at, notes)
                                    VALUES (:master_item_id, 15, 'Fluid Ounce', 'fl oz',
                                            7, 'Bottle', 'btl', :factor,
                                            true, NOW(), :notes)"""),
                            {
                                "master_item_id": item.inventory_master_item_id,
                                "factor": round(fl_oz_amount, 4),
                                "notes": f"Auto-created from vendor item size: {item.size_quantity} {size_unit.symbol}"
                            }
                        )
                        logger.info(f"Auto-created bottle conversion for master item {item.inventory_master_item_id}: "
                                   f"1 Bottle = {round(fl_oz_amount, 4)} fl oz (from {item.size_quantity} {size_unit.symbol})")

                    conn.commit()
        except Exception as e:
            logger.error(f"Error auto-creating bottle conversion: {str(e)}")

    # Sync to Inventory
    if item.vendor:
        sync_result = await sync_vendor_item_to_inventory(item, item.vendor, action="sync")
        if sync_result:
            item.synced_to_inventory = True
            if sync_result.get("inventory_vendor_item_id"):
                item.inventory_vendor_item_id = sync_result["inventory_vendor_item_id"]
            db.commit()
            db.refresh(item)

    # Check UOM sync status for response
    resp_uom_sync_ok = None
    resp_uom_sync_warning = sync_warning
    if item.inventory_master_item_id and not sync_warning:
        try:
            inv_uom_lookup = _get_inventory_uom_lookup()
            resp_uom_sync_ok, resp_uom_sync_warning = _check_uom_sync_status(item, inv_uom_lookup)
        except Exception:
            pass

    return VendorItemResponse(
        id=item.id,
        vendor_id=item.vendor_id,
        vendor_name=item.vendor.name if item.vendor else None,
        inventory_vendor_id=item.vendor.inventory_vendor_id if item.vendor else None,
        inventory_master_item_id=item.inventory_master_item_id,
        inventory_master_item_name=item.inventory_master_item_name,
        vendor_sku=item.vendor_sku,
        vendor_product_name=item.vendor_product_name,
        vendor_description=item.vendor_description,
        # Backbar-style size fields
        size_quantity=float(item.size_quantity) if item.size_quantity else None,
        size_unit_id=item.size_unit_id,
        size_unit_symbol=item.size_unit.symbol if item.size_unit else None,
        container_id=item.container_id,
        container_name=item.container.name if item.container else None,
        size_display=item.size_display,
        units_per_case=item.units_per_case,
        case_cost=float(item.case_cost) if item.case_cost else None,
        unit_cost=item.unit_cost,
        # Deprecated fields (kept for migration)
        purchase_unit_id=item.purchase_unit_id,
        purchase_unit_name=item.purchase_unit_name,
        purchase_unit_abbr=item.purchase_unit_abbr,
        pack_size=item.pack_size,
        unit_uom_id=item.unit_uom_id,
        unit_uom_name=item.unit_uom_name,
        pack_to_primary_factor=float(item.pack_to_primary_factor) if item.pack_to_primary_factor else 1.0,
        conversion_factor=float(item.conversion_factor) if item.conversion_factor else 1.0,
        conversion_unit_id=item.conversion_unit_id,
        last_purchase_price=float(item.last_purchase_price) if item.last_purchase_price else None,
        previous_purchase_price=float(item.previous_purchase_price) if item.previous_purchase_price else None,
        unit_price=float(item.unit_price) if item.unit_price else None,
        last_price=float(item.last_price) if item.last_price else None,
        minimum_order_quantity=float(item.minimum_order_quantity) if item.minimum_order_quantity else None,
        category=item.category,
        gl_asset_account=item.gl_asset_account,
        gl_cogs_account=item.gl_cogs_account,
        gl_waste_account=item.gl_waste_account,
        is_active=item.is_active,
        is_preferred=item.is_preferred,
        notes=item.notes,
        inventory_vendor_item_id=item.inventory_vendor_item_id,
        synced_to_inventory=item.synced_to_inventory,
        uom_sync_ok=resp_uom_sync_ok if sync_warning is None else False,
        uom_sync_warning=resp_uom_sync_warning,
        created_at=item.created_at,
        updated_at=item.updated_at
    )


@router.delete("/{vendor_item_id}")
async def delete_vendor_item(
    vendor_item_id: int,
    permanent: bool = Query(False, description="If true, permanently delete (only if no invoices)"),
    db: Session = Depends(get_db)
):
    """
    Delete a vendor item.

    By default, performs a soft delete (sets is_active=False).

    With permanent=true, performs a hard delete but ONLY if the item has no
    associated invoice line items (no location prices recorded).
    """
    item = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor)
    ).filter(HubVendorItem.id == vendor_item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    if permanent:
        # Check if item has invoice records (indicates invoices exist)
        from sqlalchemy import text
        invoice_check = text("""
            SELECT COUNT(*) FROM hub_invoice_items ii
            JOIN hub_invoices i ON ii.invoice_id = i.id
            WHERE i.vendor_id = :vendor_id
              AND (
                (ii.item_code IS NOT NULL AND ii.item_code = :vendor_sku)
                OR (ii.item_description = :vendor_product_name)
              )
        """)
        result = db.execute(invoice_check, {
            "vendor_id": item.vendor_id,
            "vendor_sku": item.vendor_sku,
            "vendor_product_name": item.vendor_product_name
        }).scalar()
        price_count = result or 0

        if price_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot permanently delete: item has {price_count} location price record(s) from invoices. Use deactivate instead."
            )

        # Also sync deletion to Inventory first
        if item.vendor:
            await sync_vendor_item_to_inventory(item, item.vendor, action="delete")

        # Hard delete
        db.delete(item)
        db.commit()
        logger.info(f"Permanently deleted vendor item {vendor_item_id}")
        return {"message": "Vendor item permanently deleted", "id": vendor_item_id}

    else:
        # Soft delete
        item.is_active = False
        db.commit()

        logger.info(f"Soft-deleted vendor item {vendor_item_id}")

        # Sync deletion to Inventory
        if item.vendor:
            await sync_vendor_item_to_inventory(item, item.vendor, action="delete")

        return {"message": "Vendor item deactivated", "id": vendor_item_id}


@router.get("/by-sku/{vendor_sku}")
async def get_vendor_item_by_sku(
    vendor_sku: str,
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    db: Session = Depends(get_db)
):
    """
    Look up vendor item by SKU.
    """
    query = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor)
    ).filter(HubVendorItem.vendor_sku == vendor_sku)

    if vendor_id:
        query = query.filter(HubVendorItem.vendor_id == vendor_id)

    item = query.first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Vendor item with SKU '{vendor_sku}' not found")

    return {
        "id": item.id,
        "vendor_id": item.vendor_id,
        "vendor_name": item.vendor.name if item.vendor else None,
        "inventory_master_item_id": item.inventory_master_item_id,
        "inventory_master_item_name": item.inventory_master_item_name,
        "vendor_sku": item.vendor_sku,
        "vendor_product_name": item.vendor_product_name,
        "purchase_unit_id": item.purchase_unit_id,
        "purchase_unit_name": item.purchase_unit_name,
        "purchase_unit_abbr": item.purchase_unit_abbr,
        "pack_size": item.pack_size,
        "conversion_factor": float(item.conversion_factor) if item.conversion_factor else 1.0,
        "category": item.category,
        "is_active": item.is_active
    }


@router.post("/import-from-inventory")
async def import_vendor_items_from_inventory(
    db: Session = Depends(get_db)
):
    """
    Import vendor items from Inventory database.
    This is a one-time migration endpoint.
    """
    try:
        # Fetch vendor items from Inventory's hub sync API
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{INVENTORY_API_URL}/vendor-items/_hub/sync",
                params={"limit": 5000, "is_active": "true"},
                headers=HUB_API_HEADERS
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch from Inventory: {response.status_code} - {response.text}"
                )

            inventory_items = response.json()

        logger.info(f"Fetched {len(inventory_items)} vendor items from Inventory")

        imported = 0
        skipped = 0
        errors = []

        for inv_item in inventory_items:
            try:
                # Check if already imported
                existing = db.query(HubVendorItem).filter(
                    HubVendorItem.inventory_vendor_item_id == inv_item["id"]
                ).first()

                if existing:
                    skipped += 1
                    continue

                # Find Hub vendor by Inventory vendor ID
                vendor = db.query(Vendor).filter(
                    Vendor.inventory_vendor_id == inv_item["vendor_id"]
                ).first()

                if not vendor:
                    errors.append(f"Vendor ID {inv_item['vendor_id']} ({inv_item.get('vendor_name')}) not found in Hub")
                    continue

                # Create Hub vendor item
                hub_item = HubVendorItem(
                    vendor_id=vendor.id,
                    inventory_master_item_id=inv_item.get("master_item_id"),
                    inventory_master_item_name=inv_item.get("master_item_name"),
                    vendor_sku=inv_item.get("vendor_sku"),
                    vendor_product_name=inv_item.get("vendor_product_name"),
                    vendor_description=inv_item.get("vendor_description"),
                    purchase_unit_id=inv_item.get("purchase_unit_id") or 1,
                    purchase_unit_name=inv_item.get("purchase_unit_name"),
                    purchase_unit_abbr=inv_item.get("purchase_unit_abbr"),
                    pack_size=inv_item.get("pack_size"),
                    conversion_factor=inv_item.get("conversion_factor") or 1.0,
                    conversion_unit_id=inv_item.get("conversion_unit_id"),
                    unit_price=inv_item.get("unit_price"),
                    last_price=inv_item.get("last_price"),
                    category=inv_item.get("category"),
                    is_active=inv_item.get("is_active", True),
                    is_preferred=inv_item.get("is_preferred", False),
                    inventory_vendor_item_id=inv_item["id"],
                    synced_to_inventory=True
                )

                db.add(hub_item)
                imported += 1

            except Exception as e:
                errors.append(f"Error importing item {inv_item.get('id')}: {str(e)}")
                logger.error(f"Error importing item {inv_item.get('id')}: {str(e)}")

        db.commit()

        logger.info(f"Import complete: {imported} imported, {skipped} skipped, {len(errors)} errors")

        return {
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "total_from_inventory": len(inventory_items),
            "errors": errors[:20] if errors else []
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRICE HISTORY ENDPOINTS
# ============================================================================

@router.get("/{vendor_item_id}/price-history")
async def get_vendor_item_price_history(
    vendor_item_id: int,
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get price history for a vendor item from actual invoice data.
    Returns every invoice appearance with date, price, quantity for charting.
    """
    from sqlalchemy import text

    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    query = text("""
        SELECT
            i.id as invoice_id,
            i.invoice_number,
            i.invoice_date,
            ii.quantity,
            ii.unit_price,
            ii.total_amount
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        WHERE ii.inventory_item_id = :vendor_item_id
          AND i.invoice_date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY i.invoice_date ASC, i.id ASC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "vendor_item_id": vendor_item_id,
        "days": days,
        "limit": limit
    }).fetchall()

    history = []
    for row in results:
        history.append({
            "invoice_id": row[0],
            "invoice_number": row[1],
            "invoice_date": row[2].isoformat() if row[2] else None,
            "quantity": float(row[3]) if row[3] else None,
            "unit_price": float(row[4]) if row[4] else None,
            "total": float(row[5]) if row[5] else None
        })

    return {
        "vendor_item_id": vendor_item_id,
        "product_name": item.vendor_product_name,
        "current_price": float(item.unit_price) if item.unit_price else None,
        "history": history
    }


@router.get("/price-changes/significant")
async def get_significant_price_changes(
    min_change_pct: float = Query(5.0, ge=0),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get significant price changes across all vendor items.
    Useful for detecting price increases/decreases that need attention.
    """
    from integration_hub.services.price_tracker import get_price_tracker

    tracker = get_price_tracker(db)
    changes = tracker.get_significant_price_changes(
        min_change_pct=min_change_pct,
        days=days,
        limit=limit
    )

    return {
        "min_change_pct": min_change_pct,
        "days": days,
        "changes": changes
    }


# ============================================================================
# REVIEW WORKFLOW ENDPOINTS
# ============================================================================

@router.get("/review/stats")
async def get_review_stats(db: Session = Depends(get_db)):
    """
    Get statistics about items in review workflow.

    Returns counts by status, location, and vendor.
    """
    service = VendorItemReviewService(db)
    return service.get_review_stats()


@router.get("/review/needs-review")
async def get_items_needing_review(
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get all vendor items that need review.

    Returns items with status='needs_review' for approval/rejection.
    """
    service = VendorItemReviewService(db)
    items = service.get_items_needing_review(
        vendor_id=vendor_id,
        location_id=location_id,
        limit=limit
    )
    return {"items": items, "count": len(items)}


@router.post("/review/{item_id}/approve")
async def approve_vendor_item(
    item_id: int,
    approved_by: Optional[str] = Query(None, description="Username of approver"),
    db: Session = Depends(get_db)
):
    """
    Approve a vendor item for use in costing.

    Changes status from needs_review to active.
    """
    service = VendorItemReviewService(db)
    result = service.approve_item(item_id, approved_by)
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])
    return result


@router.post("/review/{item_id}/reject")
async def reject_vendor_item(
    item_id: int,
    reason: Optional[str] = Query(None, description="Rejection reason"),
    rejected_by: Optional[str] = Query(None, description="Username of rejecter"),
    db: Session = Depends(get_db)
):
    """
    Reject a vendor item, marking it inactive.
    """
    service = VendorItemReviewService(db)
    result = service.reject_item(item_id, reason, rejected_by)
    if result.get('error'):
        raise HTTPException(status_code=400, detail=result['error'])
    return result


class BulkApproveRequest(BaseModel):
    """Bulk approve request"""
    item_ids: List[int]
    approved_by: Optional[str] = None


@router.post("/review/bulk-approve")
async def bulk_approve_vendor_items(
    request: BulkApproveRequest,
    db: Session = Depends(get_db)
):
    """
    Approve multiple vendor items at once.
    """
    service = VendorItemReviewService(db)
    return service.bulk_approve(request.item_ids, request.approved_by)


class CloneToLocationRequest(BaseModel):
    """Clone to location request"""
    target_location_id: int
    price: Optional[float] = None


@router.post("/{item_id}/clone-to-location")
async def clone_vendor_item_to_location(
    item_id: int,
    request: CloneToLocationRequest,
    db: Session = Depends(get_db)
):
    """
    Clone a vendor item to a new location.

    Used when an item is discovered via cross-location matching.
    Creates a new vendor item at the target location with needs_review status.
    """
    service = VendorItemReviewService(db)
    result = service.clone_to_location(
        source_item_id=item_id,
        target_location_id=request.target_location_id,
        price=request.price
    )
    if result.get('error'):
        if result.get('existing_item_id'):
            return result  # Not a hard error, just already exists
        raise HTTPException(status_code=400, detail=result['error'])
    return result


class CreateFromInvoiceRequest(BaseModel):
    """Create from invoice request"""
    vendor_id: int
    location_id: int
    item_code: str
    item_description: str
    unit_price: Optional[float] = None


@router.post("/create-from-invoice")
async def create_vendor_item_from_invoice(
    request: CreateFromInvoiceRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new vendor item from an unmapped invoice item.

    Creates with needs_review status for later approval.
    """
    service = VendorItemReviewService(db)
    return service.create_from_invoice_item(
        vendor_id=request.vendor_id,
        location_id=request.location_id,
        item_code=request.item_code,
        item_description=request.item_description,
        unit_price=request.unit_price
    )


# ============================================================================
# LOCATION PRICES ENDPOINTS (from invoices)
# ============================================================================

@router.get("/{vendor_item_id}/location-prices")
async def get_vendor_item_location_prices(
    vendor_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Get prices by location for a vendor item.

    Aggregates invoice data to show the last price and date per location
    where this vendor item has been purchased.

    Matches invoice items by vendor + item_code OR vendor + item_description.
    Fetches location names from Inventory API.
    """
    from sqlalchemy import text

    # Get vendor item
    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Use units_per_case (Backbar-style) for cost calculation
    units_per_case = float(item.units_per_case or item.pack_to_primary_factor or item.conversion_factor or 1.0)

    # Use pack_to_primary_factor for conversion
    pack_to_primary = float(item.pack_to_primary_factor or 1.0)

    # Query hub_invoice_items joined with hub_invoices to get prices by location
    # Match by vendor + item_code OR vendor + item_description
    query = text("""
        SELECT
            i.location_id,
            ii.unit_price as last_price,
            i.invoice_date as last_invoice_date
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        WHERE i.vendor_id = :vendor_id
          AND (
            (ii.item_code IS NOT NULL AND ii.item_code = :vendor_sku)
            OR (ii.item_description = :vendor_product_name)
          )
          AND i.location_id IS NOT NULL
        ORDER BY i.invoice_date DESC, ii.id DESC
    """)

    try:
        results = db.execute(query, {
            "vendor_id": item.vendor_id,
            "vendor_sku": item.vendor_sku,
            "vendor_product_name": item.vendor_product_name
        }).fetchall()

        if not results:
            return {"prices": []}

        # Fetch location names from Inventory database directly
        # (API requires auth, so we use DB connection)
        location_names = {}
        try:
            from sqlalchemy import create_engine
            import os
            inventory_db_url = os.getenv(
                'INVENTORY_DATABASE_URL',
                'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db'
            )
            inv_engine = create_engine(inventory_db_url)
            with inv_engine.connect() as conn:
                loc_results = conn.execute(
                    text("SELECT id, name FROM locations WHERE is_active = true ORDER BY name")
                ).fetchall()
                for row in loc_results:
                    location_names[row[0]] = row[1]
        except Exception as e:
            logger.warning(f"Could not fetch location names from Inventory DB: {e}")

        # Deduplicate: keep only the most recent invoice line per location
        seen_locations = {}
        for row in results:
            location_id = row[0]
            if location_id not in seen_locations:
                seen_locations[location_id] = row

        prices = []
        for location_id, row in seen_locations.items():
            location_name = location_names.get(location_id, None)
            if not location_name:
                location_name = str(location_id) if location_id else "Unknown"

            invoice_price = float(row[1]) if row[1] else 0

            # Calculate costs using pack_to_primary_factor
            unit_cost = invoice_price / pack_to_primary if pack_to_primary > 0 else invoice_price
            case_cost = unit_cost * units_per_case

            prices.append({
                "location_id": location_id,
                "location_name": location_name,
                "case_cost": round(case_cost, 2),
                "unit_cost": round(unit_cost, 2),
                "last_purchase_price": round(invoice_price, 2),
                "units_per_case": units_per_case,
                "price_updated_at": row[2].isoformat() if row[2] else None
            })

        return {"prices": prices}

    except Exception as e:
        logger.error(f"Error fetching location prices for vendor item {vendor_item_id}: {str(e)}")
        # Return empty prices on error
        return {"prices": []}


# ============================================================================
# LOCATION COST ENDPOINTS
# ============================================================================

@router.get("/{vendor_item_id}/location-cost")
async def get_vendor_item_location_cost(
    vendor_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the current location cost for a vendor item's master item.

    Returns the weighted average cost from Inventory's MasterItemLocationCost table.
    """
    from integration_hub.services.location_cost_updater import LocationCostUpdaterService

    # Get vendor item to find master_item_id and location_id
    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    if not item.inventory_master_item_id:
        return {"error": "Vendor item not linked to master item", "master_item_id": None}

    if not item.location_id:
        return {"error": "Vendor item has no location", "location_id": None}

    service = LocationCostUpdaterService(db)
    cost = service.get_location_cost(item.inventory_master_item_id, item.location_id)

    return {
        "vendor_item_id": vendor_item_id,
        "master_item_id": item.inventory_master_item_id,
        "location_id": item.location_id,
        "location_cost": cost
    }


@router.get("/{vendor_item_id}/cost-history")
async def get_vendor_item_cost_history(
    vendor_item_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get cost change history for a vendor item's master item at its location.
    """
    from integration_hub.services.location_cost_updater import LocationCostUpdaterService

    # Get vendor item to find master_item_id and location_id
    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    if not item.inventory_master_item_id or not item.location_id:
        return {"history": [], "message": "Vendor item not linked to master item or has no location"}

    service = LocationCostUpdaterService(db)
    history = service.get_cost_history(item.inventory_master_item_id, item.location_id, limit)

    return {
        "vendor_item_id": vendor_item_id,
        "master_item_id": item.inventory_master_item_id,
        "location_id": item.location_id,
        "history": history
    }


@router.post("/seed-location-costs")
async def seed_location_costs(
    master_item_id: Optional[int] = Query(None, description="Seed for specific master item only"),
    db: Session = Depends(get_db)
):
    """
    Seed location costs from vendor item pricing.

    For master items that don't have invoice-based location costs yet,
    this creates MasterItemLocationCost records using the vendor item's
    unit cost (case_cost / units_per_case) as the default price.

    This ensures inventory counts have pricing data even before invoices
    are processed through the Hub.
    """
    from integration_hub.services.location_cost_updater import LocationCostUpdaterService

    service = LocationCostUpdaterService(db)
    result = service.seed_location_costs_from_vendor_items(master_item_id)

    return result


@router.post("/fix-location-costs")
async def fix_location_costs(
    master_item_id: Optional[int] = Query(None, description="Fix for specific master item only"),
    db: Session = Depends(get_db)
):
    """
    Fix location costs that were seeded with incorrect values.

    This updates seeded location costs (those without last_purchase_cost)
    to use the correct unit cost (case_cost / units_per_case) instead of
    the case cost that may have been incorrectly used before.
    """
    from integration_hub.services.location_cost_updater import LocationCostUpdaterService

    service = LocationCostUpdaterService(db)
    result = service.fix_seeded_location_costs(master_item_id)

    return result


@router.post("/reprocess-sent-invoices")
async def reprocess_sent_invoices(db: Session = Depends(get_db)):
    """
    Re-process all sent invoices to update location costs.

    This is useful after fixing bugs in the location cost calculation.
    It will re-run the cost updater for all invoices that were already
    sent to inventory, applying any fixes to the calculation logic.
    """
    from integration_hub.services.location_cost_updater import LocationCostUpdaterService
    from integration_hub.models.hub_invoice import HubInvoice

    # Get all sent invoices
    sent_invoices = db.query(HubInvoice).filter(
        HubInvoice.sent_to_inventory == True,
        HubInvoice.location_id.isnot(None)
    ).order_by(HubInvoice.invoice_date).all()

    stats = {
        'invoices_processed': 0,
        'total_items_updated': 0,
        'total_items_created': 0,
        'errors': []
    }

    service = LocationCostUpdaterService(db)

    for invoice in sent_invoices:
        try:
            result = service.update_costs_from_invoice(invoice.id)
            stats['invoices_processed'] += 1
            stats['total_items_updated'] += result.get('costs_updated', 0)
            stats['total_items_created'] += result.get('costs_created', 0)
        except Exception as e:
            stats['errors'].append(f"Invoice {invoice.id}: {str(e)}")

    return stats


# ============================================================================
# LOOKUP ENDPOINTS FOR BACKBAR-STYLE SIZE FIELDS
# ============================================================================

@router.get("/lookup/size-units")
async def get_size_units(db: Session = Depends(get_db)):
    """
    Get all active size units for dropdown.
    Returns units grouped by measure type (volume, weight, count).
    """
    from integration_hub.models.size_unit import SizeUnit

    units = db.query(SizeUnit).filter(
        SizeUnit.is_active == True
    ).order_by(SizeUnit.measure_type, SizeUnit.sort_order).all()

    return [
        {
            "id": u.id,
            "name": u.name,
            "symbol": u.symbol,
            "measure_type": u.measure_type,
            "display_name": u.display_name
        }
        for u in units
    ]


@router.get("/lookup/containers")
async def get_containers(db: Session = Depends(get_db)):
    """
    Get all active containers for dropdown.
    """
    from integration_hub.models.container import Container

    containers = db.query(Container).filter(
        Container.is_active == True
    ).order_by(Container.sort_order).all()

    return [
        {
            "id": c.id,
            "name": c.name
        }
        for c in containers
    ]


# ============================================================================
# MAPPED ITEM CODES ENDPOINT
# ============================================================================

@router.get("/{vendor_item_id}/mapped-codes")
async def get_vendor_item_mapped_codes(
    vendor_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Get distinct item codes from invoice items mapped to this vendor item.
    Shows the canonical SKU plus any alternate codes (store variants, OCR misreads).
    """
    from sqlalchemy import text

    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    rows = db.execute(text("""
        SELECT ii.item_code,
               COUNT(*) as invoice_count,
               MIN(i.invoice_date) as first_seen,
               MAX(i.invoice_date) as last_seen
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        WHERE ii.inventory_item_id = :vendor_item_id
          AND ii.item_code IS NOT NULL
          AND ii.item_code != ''
        GROUP BY ii.item_code
        ORDER BY COUNT(*) DESC, ii.item_code
    """), {"vendor_item_id": vendor_item_id}).fetchall()

    return {
        "vendor_item_id": vendor_item_id,
        "vendor_sku": item.vendor_sku,
        "codes": [
            {
                "item_code": r[0],
                "invoice_count": r[1],
                "first_seen": str(r[2]) if r[2] else None,
                "last_seen": str(r[3]) if r[3] else None,
                "is_canonical": r[0] == item.vendor_sku
            }
            for r in rows
        ]
    }


# ============================================================================
# UNMAP CODE ENDPOINT
# ============================================================================

class UnmapCodeRequest(BaseModel):
    item_code: str

@router.post("/{vendor_item_id}/unmap-code")
async def unmap_code_from_vendor_item(
    vendor_item_id: int,
    request: UnmapCodeRequest,
    db: Session = Depends(get_db)
):
    """
    Unmap all invoice items with a specific item_code from this vendor item.
    Sets inventory_item_id to NULL and is_mapped to False on matching items.
    """
    from sqlalchemy import text

    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Don't allow unmapping the canonical SKU
    if request.item_code == item.vendor_sku:
        raise HTTPException(status_code=400, detail="Cannot unmap the canonical SKU. Edit the vendor item SKU instead.")

    result = db.execute(text("""
        UPDATE hub_invoice_items
        SET inventory_item_id = NULL, is_mapped = false
        WHERE inventory_item_id = :vendor_item_id
          AND item_code = :item_code
    """), {"vendor_item_id": vendor_item_id, "item_code": request.item_code})

    unmapped_count = result.rowcount

    # Recalculate status on affected invoices
    affected_invoices = db.execute(text("""
        SELECT DISTINCT invoice_id FROM hub_invoice_items
        WHERE item_code = :item_code AND inventory_item_id IS NULL AND is_mapped = false
    """), {"item_code": request.item_code}).fetchall()

    db.commit()

    # Update invoice statuses
    from integration_hub.services.invoice_status import update_invoice_status
    from integration_hub.models.hub_models import HubInvoice
    for row in affected_invoices:
        invoice = db.query(HubInvoice).filter(HubInvoice.id == row[0]).first()
        if invoice and invoice.status not in ('sent', 'partial', 'error'):
            update_invoice_status(invoice, db)

    logger.info(f"Unmapped {unmapped_count} invoice items with code '{request.item_code}' from vendor item {vendor_item_id}")

    return {
        "success": True,
        "unmapped_count": unmapped_count,
        "item_code": request.item_code,
        "vendor_item_id": vendor_item_id
    }


# ============================================================================
# INVOICE HISTORY ENDPOINT
# ============================================================================

@router.get("/{vendor_item_id}/invoice-history")
async def get_vendor_item_invoice_history(
    vendor_item_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get invoice history for a vendor item.

    Returns all invoices where this vendor item appeared, with details for
    verification purposes (invoice number, date, quantity, price, item code).

    Matches by vendor + item_code OR vendor + item_description.
    """
    from sqlalchemy import text

    # Get vendor item
    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Build location name lookup from Inventory DB
    location_names = {}
    try:
        inventory_db_url = os.getenv('INVENTORY_DATABASE_URL', '')
        if inventory_db_url:
            from sqlalchemy import create_engine
            inv_engine = create_engine(inventory_db_url)
            with inv_engine.connect() as inv_conn:
                loc_rows = inv_conn.execute(
                    text("SELECT id, name FROM locations WHERE is_active = true")
                ).fetchall()
                location_names = {r[0]: r[1] for r in loc_rows}
    except Exception as e:
        logger.warning(f"Could not fetch location names: {e}")

    # Query invoices that contain this vendor item (by direct mapping relationship)
    query = text("""
        SELECT
            i.id as invoice_id,
            i.invoice_number,
            i.invoice_date,
            i.location_id,
            ii.quantity,
            ii.unit_price,
            ii.item_code,
            ii.item_description,
            ii.total_amount
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        WHERE ii.inventory_item_id = :vendor_item_id
        ORDER BY i.invoice_date DESC, i.id DESC
        LIMIT :limit
    """)

    try:
        results = db.execute(query, {
            "vendor_item_id": vendor_item_id,
            "limit": limit
        }).fetchall()

        invoices = []
        for row in results:
            loc_id = row[3]
            invoices.append({
                "invoice_id": row[0],
                "invoice_number": row[1],
                "invoice_date": row[2].isoformat() if row[2] else None,
                "location_id": loc_id,
                "location_name": location_names.get(loc_id, f"Location {loc_id}") if loc_id else None,
                "quantity": float(row[4]) if row[4] else None,
                "unit_price": float(row[5]) if row[5] else None,
                "item_code": row[6],
                "item_description": row[7],
                "total_amount": float(row[8]) if row[8] else None
            })

        return {
            "vendor_item_id": vendor_item_id,
            "product_name": item.vendor_product_name,
            "vendor_sku": item.vendor_sku,
            "invoices": invoices,
            "count": len(invoices)
        }

    except Exception as e:
        logger.error(f"Error fetching invoice history for vendor item {vendor_item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching invoice history: {str(e)}")


@router.get("/master-item/{master_item_id}/compatible-dimensions")
async def get_compatible_dimensions(
    master_item_id: int,
    db: Session = Depends(get_db)
):
    """
    Get compatible dimensions for a master item based on linked vendor items.

    Returns the measure types (dimensions) that should be allowed for count units
    based on the SIZE UNIT of how the item is purchased from vendors.

    Logic:
    - The base UoM comes from the vendor item's size_unit ONLY
    - volume size_unit -> only volume UoMs allowed
    - weight size_unit -> only weight UoMs allowed
    - count size_unit -> only count UoMs allowed
    - units_per_case is just packaging info, NOT a count dimension
    - If no vendor items linked, all dimensions are allowed
    - If you need to count in a different dimension, define a conversion on the master item

    Response:
    - compatible_dimensions: list of dimension strings (e.g., ["volume"] or ["weight"])
    - vendor_item_dimensions: list of {vendor_name, product_name, measure_type} for each linked vendor item
    """
    from integration_hub.models.size_unit import SizeUnit

    # Find vendor items linked to this master item
    vendor_items = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor),
        joinedload(HubVendorItem.size_unit)
    ).filter(
        HubVendorItem.inventory_master_item_id == master_item_id,
        HubVendorItem.status == VendorItemStatus.active
    ).all()

    # If no vendor items linked, allow all dimensions
    if not vendor_items:
        return {
            "compatible_dimensions": ["volume", "weight", "count"],
            "vendor_item_dimensions": [],
            "has_vendor_items": False,
            "message": "No active vendor items linked. All dimensions allowed."
        }

    # Collect unique measure types from vendor items
    vendor_item_info = []
    measure_types = set()

    for vi in vendor_items:
        measure_type = None
        if vi.size_unit:
            measure_type = vi.size_unit.measure_type
            measure_types.add(measure_type)

        vendor_item_info.append({
            "vendor_name": vi.vendor.name if vi.vendor else "Unknown",
            "product_name": vi.vendor_product_name,
            "size_display": vi.size_display,
            "measure_type": measure_type
        })

    # Determine compatible dimensions - ONLY the size_unit dimension
    # The base UoM must match the vendor item's size_unit measure type
    # units_per_case is packaging info, not a reason to add "count" dimension
    compatible = set()

    for mt in measure_types:
        if mt == "volume":
            compatible.add("volume")
        elif mt == "weight":
            compatible.add("weight")
        elif mt == "count":
            compatible.add("count")

    # If no size units set, allow all
    if not measure_types:
        compatible = {"volume", "weight", "count"}

    return {
        "compatible_dimensions": sorted(list(compatible)),
        "vendor_item_dimensions": vendor_item_info,
        "has_vendor_items": True,
        "message": f"Compatible dimensions based on {len(vendor_items)} active vendor item(s)."
    }

