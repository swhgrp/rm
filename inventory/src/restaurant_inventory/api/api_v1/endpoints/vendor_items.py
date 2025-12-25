"""
Vendor Items API endpoints
Handles CRUD operations for vendor-specific item details
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models import VendorItem, MasterItem, Vendor, UnitOfMeasure, User
from restaurant_inventory.schemas.vendor_item import (
    VendorItemCreate,
    VendorItemUpdate,
    VendorItemResponse,
    VendorItemWithDetails
)

router = APIRouter()


@router.get("/_hub/sync")
def get_vendor_items_for_hub(
    vendor_id: Optional[int] = None,
    is_active: bool = True,
    limit: int = 5000,
    db: Session = Depends(get_db)
):
    """
    Get all vendor items for Integration Hub sync
    No authentication required - this is an internal API call from the hub
    IMPORTANT: This route must be defined BEFORE /{vendor_item_id} route
    Path starts with _ to avoid being matched by /{vendor_item_id} pattern
    """
    query = db.query(VendorItem).options(
        joinedload(VendorItem.vendor),
        joinedload(VendorItem.master_item)
    )

    if vendor_id:
        query = query.filter(VendorItem.vendor_id == vendor_id)

    if is_active:
        query = query.filter(VendorItem.is_active == True)

    vendor_items = query.limit(limit).all()

    # Return simple dict format for hub
    item_list = []
    for vi in vendor_items:
        item_list.append({
            "id": vi.id,
            "vendor_id": vi.vendor_id,
            "vendor_name": vi.vendor.name if vi.vendor else None,
            "vendor_sku": vi.vendor_sku,
            "vendor_product_name": vi.vendor_product_name,
            "vendor_description": vi.vendor_description,
            "master_item_id": vi.master_item_id,
            "master_item_name": vi.master_item.name if vi.master_item else None,
            "master_item_category": vi.master_item.category if vi.master_item else None,
            "pack_size": vi.pack_size,
            "unit_price": float(vi.unit_price) if vi.unit_price else None,
            "is_active": vi.is_active,
            "is_preferred": vi.is_preferred
        })

    return item_list


@router.get("/", response_model=List[VendorItemResponse])
async def get_vendor_items(
    vendor_id: Optional[int] = None,
    master_item_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    linked: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all vendor items with optional filtering

    Args:
        linked: Filter by master item link status (True=linked, False=not linked, None=all)
    """
    query = db.query(VendorItem).options(
        joinedload(VendorItem.vendor),
        joinedload(VendorItem.master_item),
        joinedload(VendorItem.purchase_unit),
        joinedload(VendorItem.conversion_unit)
    )

    if vendor_id:
        query = query.filter(VendorItem.vendor_id == vendor_id)
    if master_item_id:
        query = query.filter(VendorItem.master_item_id == master_item_id)
    if is_active is not None:
        query = query.filter(VendorItem.is_active == is_active)
    if linked is not None:
        if linked:
            query = query.filter(VendorItem.master_item_id.isnot(None))
        else:
            query = query.filter(VendorItem.master_item_id.is_(None))

    vendor_items = query.order_by(VendorItem.vendor_id, VendorItem.master_item_id).all()

    # Build response with related data
    result = []
    for vi in vendor_items:
        result.append(VendorItemResponse(
            id=vi.id,
            vendor_id=vi.vendor_id,
            master_item_id=vi.master_item_id,
            vendor_sku=vi.vendor_sku,
            vendor_product_name=vi.vendor_product_name,
            vendor_description=vi.vendor_description,
            purchase_unit_id=vi.purchase_unit_id,
            pack_size=vi.pack_size,
            conversion_factor=vi.conversion_factor,
            conversion_unit_id=vi.conversion_unit_id,
            unit_price=vi.unit_price,
            last_price=vi.last_price,
            price_updated_at=vi.price_updated_at,
            minimum_order_quantity=vi.minimum_order_quantity,
            lead_time_days=vi.lead_time_days,
            notes=vi.notes,
            is_active=vi.is_active,
            is_preferred=vi.is_preferred,
            created_at=vi.created_at,
            updated_at=vi.updated_at,
            vendor_name=vi.vendor.name if vi.vendor else None,
            master_item_name=vi.master_item.name if vi.master_item else None,
            purchase_unit_name=vi.purchase_unit.name if vi.purchase_unit else None,
            purchase_unit_abbr=vi.purchase_unit.abbreviation if vi.purchase_unit else None,
            conversion_unit_name=vi.conversion_unit.name if vi.conversion_unit else None
        ))

    return result


@router.get("/{vendor_item_id}", response_model=VendorItemWithDetails)
async def get_vendor_item(
    vendor_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific vendor item with full details"""
    vendor_item = db.query(VendorItem).options(
        joinedload(VendorItem.vendor),
        joinedload(VendorItem.master_item),
        joinedload(VendorItem.purchase_unit),
        joinedload(VendorItem.conversion_unit)
    ).filter(VendorItem.id == vendor_item_id).first()

    if not vendor_item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Calculate cost per master unit
    cost_per_master_unit = None
    if vendor_item.unit_price and vendor_item.conversion_factor:
        cost_per_master_unit = vendor_item.unit_price / vendor_item.conversion_factor

    return VendorItemWithDetails(
        id=vendor_item.id,
        vendor_id=vendor_item.vendor_id,
        master_item_id=vendor_item.master_item_id,
        vendor_sku=vendor_item.vendor_sku,
        vendor_product_name=vendor_item.vendor_product_name,
        vendor_description=vendor_item.vendor_description,
        purchase_unit_id=vendor_item.purchase_unit_id,
        pack_size=vendor_item.pack_size,
        conversion_factor=vendor_item.conversion_factor,
        conversion_unit_id=vendor_item.conversion_unit_id,
        unit_price=vendor_item.unit_price,
        last_price=vendor_item.last_price,
        price_updated_at=vendor_item.price_updated_at,
        minimum_order_quantity=vendor_item.minimum_order_quantity,
        lead_time_days=vendor_item.lead_time_days,
        notes=vendor_item.notes,
        is_active=vendor_item.is_active,
        is_preferred=vendor_item.is_preferred,
        created_at=vendor_item.created_at,
        updated_at=vendor_item.updated_at,
        vendor_name=vendor_item.vendor.name if vendor_item.vendor else None,
        master_item_name=vendor_item.master_item.name if vendor_item.master_item else None,
        purchase_unit_name=vendor_item.purchase_unit.name if vendor_item.purchase_unit else None,
        purchase_unit_abbr=vendor_item.purchase_unit.abbreviation if vendor_item.purchase_unit else None,
        conversion_unit_name=vendor_item.conversion_unit.name if vendor_item.conversion_unit else None,
        master_item_category=vendor_item.master_item.category if vendor_item.master_item else None,
        master_item_unit_name=vendor_item.master_item.unit.name if vendor_item.master_item and vendor_item.master_item.unit else None,
        cost_per_master_unit=cost_per_master_unit
    )


@router.post("/", response_model=VendorItemResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_item(
    vendor_item: VendorItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new vendor item"""
    # Validate vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == vendor_item.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Validate master item exists
    master_item = db.query(MasterItem).filter(MasterItem.id == vendor_item.master_item_id).first()
    if not master_item:
        raise HTTPException(status_code=404, detail="Master item not found")

    # Validate purchase unit exists
    purchase_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == vendor_item.purchase_unit_id).first()
    if not purchase_unit:
        raise HTTPException(status_code=404, detail="Purchase unit not found")

    # Create vendor item
    db_vendor_item = VendorItem(**vendor_item.model_dump())
    db.add(db_vendor_item)
    db.commit()
    db.refresh(db_vendor_item)

    # Load relationships
    db_vendor_item = db.query(VendorItem).options(
        joinedload(VendorItem.vendor),
        joinedload(VendorItem.master_item),
        joinedload(VendorItem.purchase_unit),
        joinedload(VendorItem.conversion_unit)
    ).filter(VendorItem.id == db_vendor_item.id).first()

    return VendorItemResponse(
        id=db_vendor_item.id,
        vendor_id=db_vendor_item.vendor_id,
        master_item_id=db_vendor_item.master_item_id,
        vendor_sku=db_vendor_item.vendor_sku,
        vendor_product_name=db_vendor_item.vendor_product_name,
        vendor_description=db_vendor_item.vendor_description,
        purchase_unit_id=db_vendor_item.purchase_unit_id,
        pack_size=db_vendor_item.pack_size,
        conversion_factor=db_vendor_item.conversion_factor,
        conversion_unit_id=db_vendor_item.conversion_unit_id,
        unit_price=db_vendor_item.unit_price,
        last_price=db_vendor_item.last_price,
        price_updated_at=db_vendor_item.price_updated_at,
        minimum_order_quantity=db_vendor_item.minimum_order_quantity,
        lead_time_days=db_vendor_item.lead_time_days,
        notes=db_vendor_item.notes,
        is_active=db_vendor_item.is_active,
        is_preferred=db_vendor_item.is_preferred,
        created_at=db_vendor_item.created_at,
        updated_at=db_vendor_item.updated_at,
        vendor_name=db_vendor_item.vendor.name if db_vendor_item.vendor else None,
        master_item_name=db_vendor_item.master_item.name if db_vendor_item.master_item else None,
        purchase_unit_name=db_vendor_item.purchase_unit.name if db_vendor_item.purchase_unit else None,
        purchase_unit_abbr=db_vendor_item.purchase_unit.abbreviation if db_vendor_item.purchase_unit else None,
        conversion_unit_name=db_vendor_item.conversion_unit.name if db_vendor_item.conversion_unit else None
    )


@router.put("/{vendor_item_id}", response_model=VendorItemResponse)
async def update_vendor_item(
    vendor_item_id: int,
    vendor_item_update: VendorItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a vendor item"""
    import logging
    logger = logging.getLogger(__name__)

    db_vendor_item = db.query(VendorItem).filter(VendorItem.id == vendor_item_id).first()
    if not db_vendor_item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Track price changes
    if vendor_item_update.unit_price is not None and vendor_item_update.unit_price != db_vendor_item.unit_price:
        db_vendor_item.last_price = db_vendor_item.unit_price
        from datetime import datetime
        db_vendor_item.price_updated_at = datetime.now()

    # Update fields
    update_data = vendor_item_update.model_dump(exclude_unset=True)
    logger.info(f"Updating vendor item {vendor_item_id} with data: {update_data}")
    logger.info(f"master_item_id in update_data: {update_data.get('master_item_id')}")

    for field, value in update_data.items():
        logger.info(f"Setting {field} = {value}")
        setattr(db_vendor_item, field, value)

    db.commit()
    db.refresh(db_vendor_item)

    logger.info(f"After commit, master_item_id = {db_vendor_item.master_item_id}")

    # Load relationships
    db_vendor_item = db.query(VendorItem).options(
        joinedload(VendorItem.vendor),
        joinedload(VendorItem.master_item),
        joinedload(VendorItem.purchase_unit),
        joinedload(VendorItem.conversion_unit)
    ).filter(VendorItem.id == db_vendor_item.id).first()

    return VendorItemResponse(
        id=db_vendor_item.id,
        vendor_id=db_vendor_item.vendor_id,
        master_item_id=db_vendor_item.master_item_id,
        vendor_sku=db_vendor_item.vendor_sku,
        vendor_product_name=db_vendor_item.vendor_product_name,
        vendor_description=db_vendor_item.vendor_description,
        purchase_unit_id=db_vendor_item.purchase_unit_id,
        pack_size=db_vendor_item.pack_size,
        conversion_factor=db_vendor_item.conversion_factor,
        conversion_unit_id=db_vendor_item.conversion_unit_id,
        unit_price=db_vendor_item.unit_price,
        last_price=db_vendor_item.last_price,
        price_updated_at=db_vendor_item.price_updated_at,
        minimum_order_quantity=db_vendor_item.minimum_order_quantity,
        lead_time_days=db_vendor_item.lead_time_days,
        notes=db_vendor_item.notes,
        is_active=db_vendor_item.is_active,
        is_preferred=db_vendor_item.is_preferred,
        created_at=db_vendor_item.created_at,
        updated_at=db_vendor_item.updated_at,
        vendor_name=db_vendor_item.vendor.name if db_vendor_item.vendor else None,
        master_item_name=db_vendor_item.master_item.name if db_vendor_item.master_item else None,
        purchase_unit_name=db_vendor_item.purchase_unit.name if db_vendor_item.purchase_unit else None,
        purchase_unit_abbr=db_vendor_item.purchase_unit.abbreviation if db_vendor_item.purchase_unit else None,
        conversion_unit_name=db_vendor_item.conversion_unit.name if db_vendor_item.conversion_unit else None
    )


@router.delete("/{vendor_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_item(
    vendor_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a vendor item"""
    db_vendor_item = db.query(VendorItem).filter(VendorItem.id == vendor_item_id).first()
    if not db_vendor_item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    db.delete(db_vendor_item)
    db.commit()
    return None
