"""
Location Management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, joinedload
from typing import List

from hr.db.database import get_db
from hr.models.user import User
from hr.models.location import Location
from hr.schemas.location import (
    LocationCreate, LocationUpdate, LocationResponse,
    UserLocationAssignment, UserLocationResponse
)
from hr.api.auth import require_admin, require_auth
from hr.core.authorization import filter_by_user_locations


router = APIRouter(prefix="/api/locations", tags=["Locations"])


@router.get("/all", response_model=List[LocationResponse])
def list_all_locations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List ALL locations without filtering (Admin only - for user management)"""
    locations = db.query(Location).filter(Location.is_active == True).offset(skip).limit(limit).all()
    return locations


@router.get("/", response_model=List[LocationResponse])
def list_locations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all locations (filtered by user's assigned locations)"""
    query = db.query(Location)

    # Apply user location filtering
    query = filter_by_user_locations(query, Location.id, current_user)

    locations = query.filter(Location.is_active == True).offset(skip).limit(limit).all()
    return locations


@router.get("/{location_id}", response_model=LocationResponse)
def get_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific location by ID (only if user has access)"""
    query = db.query(Location).filter(Location.id == location_id)
    query = filter_by_user_locations(query, Location.id, current_user)

    location = query.first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found or you don't have access to it"
        )

    return location


@router.post("/", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def create_location(
    location_data: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new location (Admin only)"""
    # Check if location name already exists
    existing = db.query(Location).filter(Location.name == location_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location with this name already exists"
        )

    new_location = Location(**location_data.model_dump())
    db.add(new_location)
    db.commit()
    db.refresh(new_location)

    return new_location


@router.put("/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: int,
    location_data: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a location (Admin only)"""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Check name uniqueness if changing name
    if location_data.name and location_data.name != location.name:
        existing = db.query(Location).filter(
            Location.name == location_data.name,
            Location.id != location_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location with this name already exists"
            )

    # Update fields
    update_data = location_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)

    db.commit()
    db.refresh(location)

    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a location (Admin only)"""
    location = db.query(Location).filter(Location.id == location_id).first()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Check if location has assigned users
    if location.assigned_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete location. It is assigned to {len(location.assigned_users)} user(s)"
        )

    db.delete(location)
    db.commit()

    return None


@router.get("/user/{user_id}", response_model=UserLocationResponse)
def get_user_locations(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get assigned locations for a user (Admin only)"""
    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserLocationResponse(
        user_id=user.id,
        username=user.username,
        assigned_locations=[LocationResponse.model_validate(loc) for loc in user.assigned_locations],
        has_restrictions=len(user.assigned_locations) > 0
    )


@router.post("/user/{user_id}", response_model=dict)
def assign_user_locations(
    user_id: int,
    assignment: UserLocationAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Assign locations to a user (Admin only)

    Empty location_ids list means user has access to ALL locations (no restrictions)
    Populated list means user can only access those specific locations
    """
    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    location_ids = assignment.location_ids

    # Validate all location IDs exist
    if location_ids:
        locations = db.query(Location).filter(Location.id.in_(location_ids)).all()
        if len(locations) != len(location_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more location IDs are invalid"
            )
    else:
        locations = []

    # Store old assignments for logging
    old_location_ids = [loc.id for loc in user.assigned_locations]

    # Update assignments - replace all
    user.assigned_locations = locations
    db.commit()

    return {
        "message": "User locations updated successfully",
        "user_id": user.id,
        "username": user.username,
        "assigned_location_count": len(locations),
        "has_restrictions": len(locations) > 0,
        "old_assignments": old_location_ids,
        "new_assignments": location_ids
    }


@router.delete("/user/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_user_locations(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Clear all location assignments for a user (grants access to all locations) (Admin only)"""
    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.assigned_locations = []
    db.commit()

    return None
