"""
Location CRUD endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.location import LocationCreate, LocationUpdate, LocationResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

router = APIRouter()

@router.get("/", response_model=List[LocationResponse])
async def get_locations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all locations"""
    locations = db.query(Location).offset(skip).limit(limit).all()
    return locations

@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific location by ID"""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    return location

@router.post("/", response_model=LocationResponse)
async def create_location(
    location_data: LocationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create new location (Manager/Admin only)"""

    # Check if location with same name already exists
    existing = db.query(Location).filter(Location.name == location_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location with this name already exists"
        )

    location = Location(**location_data.dict())
    db.add(location)
    db.commit()
    db.refresh(location)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="location",
        entity_id=location.id,
        user=current_user,
        changes={"new": {
            "name": location.name,
            "address": location.address
        }},
        request=request
    )

    return location

@router.put("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int,
    location_data: LocationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update location (Manager/Admin only)"""

    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Track old values
    old_data = {
        "name": location.name,
        "address": location.address
    }

    # Update fields that were provided
    update_data = location_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)

    db.commit()
    db.refresh(location)

    # Track new values
    new_data = {
        "name": location.name,
        "address": location.address
    }

    # Log audit event
    changes = create_change_dict(old_data, new_data)
    if changes:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="location",
            entity_id=location.id,
            user=current_user,
            changes=changes,
            request=request
        )

    return location

@router.delete("/{location_id}")
async def delete_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete location (Manager/Admin only)"""

    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Check if location has inventory records
    from restaurant_inventory.models.inventory import Inventory
    inventory_count = db.query(Inventory).filter(Inventory.location_id == location_id).count()

    if inventory_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete location with {inventory_count} inventory records. Please transfer or remove inventory first."
        )

    # Log before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="location",
        entity_id=location.id,
        user=current_user,
        changes={"old": {
            "name": location.name,
            "address": location.address
        }},
        request=request
    )

    db.delete(location)
    db.commit()
    return {"message": "Location deleted successfully"}
