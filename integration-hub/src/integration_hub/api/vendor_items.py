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
    purchase_unit_id: int
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

    # Build response
    result_items = []
    for item in items:
        uom_check = check_uom_completeness(item)
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

    db.commit()
    db.refresh(item)

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

    # Sync size_unit (primary UoM) to master item if updated and item is mapped
    # For VOLUME items: use Fluid Ounce (id=15) as primary for POS liquor tracking
    # For other items: use the vendor item's size unit
    if "size_unit_id" in update_data and item.inventory_master_item_id and item.size_unit_id:
        try:
            from sqlalchemy import text, create_engine
            from integration_hub.models.size_unit import SizeUnit

            # Get size unit details
            size_unit = db.query(SizeUnit).filter(SizeUnit.id == item.size_unit_id).first()
            if size_unit:
                inventory_db_url = os.getenv(
                    "INVENTORY_DATABASE_URL",
                    "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
                )
                inv_engine = create_engine(inventory_db_url)

                # For volume items, set primary UoM to Fluid Ounce for POS tracking
                if size_unit.measure_type == "volume" and size_unit.conversion_to_inventory_unit:
                    uom_id, uom_name, uom_abbr = 15, "Fluid Ounce", "fl oz"
                    logger.info(f"Volume item detected - using Fluid Ounce as primary UoM instead of {size_unit.symbol}")
                else:
                    uom_id, uom_name, uom_abbr = size_unit.id, size_unit.name, size_unit.symbol

                with inv_engine.connect() as conn:
                    conn.execute(
                        text("""UPDATE master_items
                                SET primary_uom_id = :uom_id,
                                    primary_uom_name = :uom_name,
                                    primary_uom_abbr = :uom_abbr,
                                    updated_at = NOW()
                                WHERE id = :id"""),
                        {
                            "id": item.inventory_master_item_id,
                            "uom_id": uom_id,
                            "uom_name": uom_name,
                            "uom_abbr": uom_abbr
                        }
                    )
                    conn.commit()
                    logger.info(f"Synced primary UoM '{uom_abbr}' to master item {item.inventory_master_item_id}")
        except Exception as e:
            logger.error(f"Error syncing primary UoM to master item: {str(e)}")

    # Sync category to master item if category was updated and item is mapped
    if "category" in update_data and item.inventory_master_item_id and item.category:
        try:
            from sqlalchemy import text, create_engine
            inventory_db_url = os.getenv(
                "INVENTORY_DATABASE_URL",
                "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
            )
            inv_engine = create_engine(inventory_db_url)
            with inv_engine.connect() as conn:
                conn.execute(
                    text("UPDATE master_items SET category = :category, updated_at = NOW() WHERE id = :id"),
                    {"id": item.inventory_master_item_id, "category": item.category}
                )
                conn.commit()
                logger.info(f"Synced category '{item.category}' to master item {item.inventory_master_item_id}")
        except Exception as e:
            logger.error(f"Error syncing category to master item: {str(e)}")

    # Auto-create bottle conversion and set primary UoM when vendor item with volume is mapped to master item
    if "inventory_master_item_id" in update_data and item.inventory_master_item_id and item.size_quantity and item.size_unit_id:
        try:
            from sqlalchemy import text, create_engine
            from integration_hub.models.size_unit import SizeUnit

            # Get size unit to check if it has conversion factor for inventory unit
            size_unit = db.query(SizeUnit).filter(SizeUnit.id == item.size_unit_id).first()
            if size_unit and size_unit.conversion_to_inventory_unit and size_unit.measure_type == "volume":
                # Calculate fl oz from vendor item size
                fl_oz_amount = float(item.size_quantity) * float(size_unit.conversion_to_inventory_unit)

                inventory_db_url = os.getenv(
                    "INVENTORY_DATABASE_URL",
                    "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"
                )
                inv_engine = create_engine(inventory_db_url)
                with inv_engine.connect() as conn:
                    # Set primary UoM to Fluid Ounce for volume items
                    conn.execute(
                        text("""UPDATE master_items
                                SET primary_uom_id = 15,
                                    primary_uom_name = 'Fluid Ounce',
                                    primary_uom_abbr = 'fl oz',
                                    updated_at = NOW()
                                WHERE id = :id"""),
                        {"id": item.inventory_master_item_id}
                    )
                    logger.info(f"Set primary UoM to Fluid Ounce for master item {item.inventory_master_item_id}")

                    # Check if conversion already exists for this item (fl oz -> Bottle)
                    existing = conn.execute(
                        text("""SELECT id FROM item_unit_conversions
                                WHERE master_item_id = :master_item_id
                                AND from_unit_id = 15 AND to_unit_id = 7"""),
                        {"master_item_id": item.inventory_master_item_id}
                    ).fetchone()

                    if not existing:
                        # Insert new bottle conversion: 1 Bottle = X fl oz
                        # from_unit = Fluid Ounce (15), to_unit = Bottle (7)
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
                    else:
                        logger.info(f"Bottle conversion already exists for master item {item.inventory_master_item_id}")

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
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get price history for a specific vendor item.
    """
    from integration_hub.services.price_tracker import get_price_tracker

    # Verify item exists
    item = db.query(HubVendorItem).filter(HubVendorItem.id == vendor_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    tracker = get_price_tracker(db)
    history = tracker.get_price_history(vendor_item_id, limit=limit)

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

    # Query hub_invoice_items joined with hub_invoices to get prices by location
    # Match by vendor + item_code OR vendor + item_description
    query = text("""
        SELECT
            i.location_id,
            MAX(ii.unit_price) as last_price,
            MAX(i.invoice_date) as last_invoice_date
        FROM hub_invoice_items ii
        JOIN hub_invoices i ON ii.invoice_id = i.id
        WHERE i.vendor_id = :vendor_id
          AND (
            (ii.item_code IS NOT NULL AND ii.item_code = :vendor_sku)
            OR (ii.item_description = :vendor_product_name)
          )
          AND i.location_id IS NOT NULL
        GROUP BY i.location_id
        ORDER BY last_invoice_date DESC
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

        prices = []
        for row in results:
            location_id = row[0]
            # location_id in Hub invoices is often a string name like "Tiki Terrace"
            # Try to match against Inventory locations by ID or by name
            location_name = location_names.get(location_id, None)
            if not location_name:
                # If location_id is actually a name string, use it directly
                location_name = str(location_id) if location_id else "Unknown"

            # Invoice unit_price is case cost, calculate unit cost
            case_cost = float(row[1]) if row[1] else 0
            unit_cost = case_cost / units_per_case if units_per_case > 0 else case_cost

            prices.append({
                "location_id": location_id,
                "location_name": location_name,
                "case_cost": case_cost,
                "unit_cost": unit_cost,
                "last_purchase_price": case_cost,  # Alias for compatibility
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

    # Query invoices that contain this vendor item
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
        WHERE i.vendor_id = :vendor_id
          AND (
            (ii.item_code IS NOT NULL AND ii.item_code = :vendor_sku)
            OR (ii.item_description = :vendor_product_name)
          )
        ORDER BY i.invoice_date DESC, i.id DESC
        LIMIT :limit
    """)

    try:
        results = db.execute(query, {
            "vendor_id": item.vendor_id,
            "vendor_sku": item.vendor_sku,
            "vendor_product_name": item.vendor_product_name,
            "limit": limit
        }).fetchall()

        invoices = []
        for row in results:
            invoices.append({
                "invoice_id": row[0],
                "invoice_number": row[1],
                "invoice_date": row[2].isoformat() if row[2] else None,
                "location_id": row[3],
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
