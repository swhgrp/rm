"""
Storage Area API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin, filter_by_user_locations
from restaurant_inventory.models.user import User
from restaurant_inventory.models.storage_area import StorageArea, StorageAreaItem
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.schemas.storage_area import StorageAreaCreate, StorageAreaUpdate, StorageAreaResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict
from pydantic import BaseModel

router = APIRouter()


@router.get("/", response_model=List[StorageAreaResponse])
async def get_storage_areas(
    location_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all storage areas (filtered by user's assigned locations)"""
    query = db.query(StorageArea)

    # Apply user location filtering FIRST
    query = filter_by_user_locations(query, StorageArea.location_id, current_user)

    if location_id:
        query = query.filter(StorageArea.location_id == location_id)

    # Order by display_order, then by name
    return query.filter(StorageArea.is_active == True).order_by(StorageArea.display_order, StorageArea.name).all()


@router.get("/{storage_area_id}", response_model=StorageAreaResponse)
async def get_storage_area(
    storage_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific storage area by ID (only if user has access to its location)"""
    query = db.query(StorageArea).filter(StorageArea.id == storage_area_id)
    query = filter_by_user_locations(query, StorageArea.location_id, current_user)
    storage_area = query.first()
    if not storage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage area not found or you don't have access to it"
        )
    return storage_area


@router.post("/", response_model=StorageAreaResponse)
async def create_storage_area(
    storage_area_data: StorageAreaCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new storage area"""
    # Validate location exists
    location = db.query(Location).filter(Location.id == storage_area_data.location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Get max display_order for this location
    max_order = db.query(StorageArea).filter(
        StorageArea.location_id == storage_area_data.location_id
    ).count()

    storage_area = StorageArea(
        location_id=storage_area_data.location_id,
        name=storage_area_data.name,
        description=storage_area_data.description,
        display_order=max_order,
        is_active=storage_area_data.is_active
    )

    db.add(storage_area)
    db.commit()
    db.refresh(storage_area)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="storage_area",
        entity_id=storage_area.id,
        user=current_user,
        changes={
            "new": {
                "name": storage_area.name,
                "location": location.name,
                "location_id": storage_area.location_id
            }
        },
        request=request
    )

    return storage_area


# Pydantic schema for storage area reordering
class StorageAreaReorder(BaseModel):
    area_id: int
    display_order: int


@router.put("/reorder")
async def reorder_storage_areas(
    areas: List[StorageAreaReorder],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update display order of storage areas"""
    for area_data in areas:
        storage_area = db.query(StorageArea).filter(
            StorageArea.id == area_data.area_id
        ).first()

        if storage_area:
            storage_area.display_order = area_data.display_order

    db.commit()

    return {"success": True, "message": "Storage areas reordered"}


@router.put("/{storage_area_id}", response_model=StorageAreaResponse)
async def update_storage_area(
    storage_area_id: int,
    storage_area_data: StorageAreaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a storage area"""
    storage_area = db.query(StorageArea).filter(StorageArea.id == storage_area_id).first()
    if not storage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage area not found"
        )

    # Track old values
    old_data = {
        "name": storage_area.name,
        "description": storage_area.description,
        "is_active": storage_area.is_active
    }

    # Update fields
    if storage_area_data.name is not None:
        storage_area.name = storage_area_data.name
    if storage_area_data.description is not None:
        storage_area.description = storage_area_data.description
    if storage_area_data.is_active is not None:
        storage_area.is_active = storage_area_data.is_active

    db.commit()
    db.refresh(storage_area)

    # Track new values
    new_data = {
        "name": storage_area.name,
        "description": storage_area.description,
        "is_active": storage_area.is_active
    }

    changes = create_change_dict(old_data, new_data)
    if changes:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="storage_area",
            entity_id=storage_area.id,
            user=current_user,
            changes=changes,
            request=request
        )

    return storage_area


@router.delete("/{storage_area_id}")
async def delete_storage_area(
    storage_area_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a storage area (soft delete by setting is_active=False)"""
    storage_area = db.query(StorageArea).filter(StorageArea.id == storage_area_id).first()
    if not storage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage area not found"
        )

    # Soft delete
    storage_area.is_active = False
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="storage_area",
        entity_id=storage_area.id,
        user=current_user,
        changes={"old": {"name": storage_area.name}},
        request=request
    )

    return {"success": True, "message": "Storage area deleted"}





# Pydantic schemas for storage area items
class StorageAreaItemResponse(BaseModel):
    id: int
    storage_area_id: int
    master_item_id: int
    display_order: int
    item_name: str
    item_category: str
    item_unit: str

    class Config:
        from_attributes = True


class StorageAreaItemReorder(BaseModel):
    item_id: int
    display_order: int


@router.get("/{storage_area_id}/items", response_model=List[StorageAreaItemResponse])
async def get_storage_area_items(
    storage_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all default items for a storage area, ordered by display_order"""
    items = db.query(StorageAreaItem).filter(
        StorageAreaItem.storage_area_id == storage_area_id
    ).order_by(StorageAreaItem.display_order).all()

    result = []
    for item in items:
        master_item = db.query(MasterItem).filter(MasterItem.id == item.master_item_id).first()
        if master_item:
            result.append(StorageAreaItemResponse(
                id=item.id,
                storage_area_id=item.storage_area_id,
                master_item_id=item.master_item_id,
                display_order=item.display_order,
                item_name=master_item.name,
                item_category=master_item.category or "",
                item_unit=master_item.unit.name if master_item.unit else "Each"
            ))

    return result


@router.post("/{storage_area_id}/items/{master_item_id}")
async def add_item_to_storage_area(
    storage_area_id: int,
    master_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Add an item to storage area's default item list"""
    # Check if already exists
    existing = db.query(StorageAreaItem).filter(
        StorageAreaItem.storage_area_id == storage_area_id,
        StorageAreaItem.master_item_id == master_item_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item already in storage area"
        )

    # Get max display_order
    max_order = db.query(StorageAreaItem).filter(
        StorageAreaItem.storage_area_id == storage_area_id
    ).count()

    item = StorageAreaItem(
        storage_area_id=storage_area_id,
        master_item_id=master_item_id,
        display_order=max_order
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {"success": True, "id": item.id}


@router.delete("/{storage_area_id}/items/{item_id}")
async def remove_item_from_storage_area(
    storage_area_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Remove an item from storage area's default item list"""
    item = db.query(StorageAreaItem).filter(
        StorageAreaItem.id == item_id,
        StorageAreaItem.storage_area_id == storage_area_id
    ).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in storage area"
        )

    db.delete(item)
    db.commit()

    return {"success": True, "message": "Item removed"}


@router.put("/{storage_area_id}/items/reorder")
async def reorder_storage_area_items(
    storage_area_id: int,
    items: List[StorageAreaItemReorder],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update display order of items in storage area"""
    for item_data in items:
        item = db.query(StorageAreaItem).filter(
            StorageAreaItem.id == item_data.item_id,
            StorageAreaItem.storage_area_id == storage_area_id
        ).first()

        if item:
            item.display_order = item_data.display_order

    db.commit()

    return {"success": True, "message": "Items reordered"}
