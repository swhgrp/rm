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

from integration_hub.db.database import get_db
from integration_hub.models.hub_vendor_item import HubVendorItem, VendorItemStatus
from integration_hub.models.vendor import Vendor
from integration_hub.services.vendor_item_review import VendorItemReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vendor-items", tags=["vendor-items-api"])

# Inventory API URL for fetching master items and UOM
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000/api")


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
    is_active: bool = True
    is_preferred: bool = False
    notes: Optional[str] = None

    # Sync info
    inventory_vendor_item_id: Optional[int] = None
    synced_to_inventory: bool = False

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
    page_size: int = Query(50, ge=1, le=500),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    master_item_id: Optional[int] = Query(None, description="Filter by master item"),
    search: Optional[str] = Query(None, description="Search by SKU or name"),
    status: Optional[str] = Query(None, description="Filter by status (active, needs_review, inactive)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status (deprecated, use status)"),
    category: Optional[str] = Query(None, description="Filter by category"),
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
    query = db.query(HubVendorItem).options(joinedload(HubVendorItem.vendor))

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

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    items = query.order_by(HubVendorItem.vendor_product_name).offset(offset).limit(page_size).all()

    # Build response
    result_items = []
    for item in items:
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
    # Verify vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == item_data.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

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

    db.add(item)
    db.commit()
    db.refresh(item)

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

    # Update fields
    update_data = item_data.dict(exclude_unset=True)

    # Track price changes (support both old and new field names)
    if "last_purchase_price" in update_data and update_data["last_purchase_price"] is not None:
        if item.last_purchase_price is not None:
            item.previous_purchase_price = item.last_purchase_price
        item.price_updated_at = datetime.utcnow()
    elif "unit_price" in update_data and update_data["unit_price"] is not None:
        if item.unit_price is not None:
            item.last_price = item.unit_price
        item.price_updated_at = datetime.utcnow()

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
    db: Session = Depends(get_db)
):
    """
    Delete a vendor item (soft delete - sets is_active=False).
    """
    item = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor)
    ).filter(HubVendorItem.id == vendor_item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

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
                params={"limit": 5000, "is_active": "true"}
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

    pack_factor = float(item.pack_to_primary_factor or item.conversion_factor or 1.0)

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
            return []

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

            prices.append({
                "location_id": location_id,
                "location_name": location_name,
                "last_price": float(row[1]) if row[1] else 0,
                "pack_factor": pack_factor,
                "last_invoice_date": row[2].isoformat() if row[2] else None
            })

        return prices

    except Exception as e:
        logger.error(f"Error fetching location prices for vendor item {vendor_item_id}: {str(e)}")
        # Return empty list on error
        return []


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
