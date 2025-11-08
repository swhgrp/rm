"""Event Packages API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from events.core.database import get_db
from events.models.user import User
from events.models.event import EventPackage
from events.schemas.package import (
    EventPackageCreate,
    EventPackageUpdate,
    EventPackageResponse,
    EventPackageListItem
)
from events.core.deps import require_auth, require_role, check_permission

router = APIRouter()


@router.get("/", response_model=List[EventPackageListItem])
async def list_packages(
    event_type: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get all event packages

    Optionally filter by event_type
    """
    query = db.query(EventPackage)

    if event_type:
        query = query.filter(EventPackage.event_type == event_type)

    packages = query.order_by(EventPackage.name).all()

    # Transform to list items with extracted pricing
    result = []
    for pkg in packages:
        item = {
            "id": pkg.id,
            "name": pkg.name,
            "event_type": pkg.event_type,
            "created_at": pkg.created_at,
            "base_price": None,
            "per_guest_price": None
        }

        if pkg.price_components_json:
            item["base_price"] = pkg.price_components_json.get("base_price")
            item["per_guest_price"] = pkg.price_components_json.get("per_guest_price")

        result.append(EventPackageListItem(**item))

    return result


@router.get("/{package_id}", response_model=EventPackageResponse)
async def get_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific event package by ID"""
    package = db.query(EventPackage).filter(EventPackage.id == package_id).first()

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event package not found"
        )

    # Convert price_components_json to PriceComponents model
    response_data = {
        "id": package.id,
        "name": package.name,
        "event_type": package.event_type,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
        "price_components": package.price_components_json
    }

    return EventPackageResponse(**response_data)


@router.post("/", response_model=EventPackageResponse, status_code=status.HTTP_201_CREATED)
async def create_package(
    package_data: EventPackageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Create a new event package"""
    # Convert price_components to JSON
    price_json = None
    if package_data.price_components:
        price_json = package_data.price_components.model_dump()

    package = EventPackage(
        name=package_data.name,
        event_type=package_data.event_type,
        price_components_json=price_json
    )

    db.add(package)
    db.commit()
    db.refresh(package)

    # Convert back to response model
    response_data = {
        "id": package.id,
        "name": package.name,
        "event_type": package.event_type,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
        "price_components": package.price_components_json
    }

    return EventPackageResponse(**response_data)


@router.put("/{package_id}", response_model=EventPackageResponse)
async def update_package(
    package_id: UUID,
    package_data: EventPackageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "event_manager"))
):
    """Update an event package"""
    package = db.query(EventPackage).filter(EventPackage.id == package_id).first()

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event package not found"
        )

    # Update fields
    if package_data.name is not None:
        package.name = package_data.name
    if package_data.event_type is not None:
        package.event_type = package_data.event_type
    if package_data.price_components is not None:
        package.price_components_json = package_data.price_components.model_dump()

    db.commit()
    db.refresh(package)

    # Convert back to response model
    response_data = {
        "id": package.id,
        "name": package.name,
        "event_type": package.event_type,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
        "price_components": package.price_components_json
    }

    return EventPackageResponse(**response_data)


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """Delete an event package"""
    package = db.query(EventPackage).filter(EventPackage.id == package_id).first()

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event package not found"
        )

    # Check if package is used by any events
    from events.models.event import Event
    events_using_package = db.query(Event).filter(Event.package_id == package_id).count()

    if events_using_package > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete package: {events_using_package} event(s) are using this package"
        )

    db.delete(package)
    db.commit()

    return None
