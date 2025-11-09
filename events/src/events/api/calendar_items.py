"""Calendar items API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from events.core.database import get_db
from events.core.deps import require_auth
from events.models.user import User, UserLocation
from events.models.calendar_item import CalendarItem
from events.schemas.calendar_item import (
    CalendarItemCreate,
    CalendarItemUpdate,
    CalendarItemResponse
)

router = APIRouter(prefix="/calendar-items", tags=["calendar-items"])


@router.post("/", response_model=CalendarItemResponse)
async def create_calendar_item(
    item_data: CalendarItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new calendar item"""

    # Check if user has access to the specified venue (location-based permissions)
    if item_data.venue_id:
        user_roles = [role.code for role in current_user.roles]
        if "admin" not in user_roles:
            # Check if user has access to this venue
            user_venue = db.query(UserLocation).filter(
                UserLocation.user_id == current_user.id,
                UserLocation.venue_id == item_data.venue_id
            ).first()

            if not user_venue:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to create items at this location"
                )

    # Create the calendar item
    new_item = CalendarItem(
        **item_data.model_dump(),
        created_by=current_user.id
    )

    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    return new_item


@router.get("/", response_model=List[CalendarItemResponse])
async def list_calendar_items(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    item_type: Optional[str] = None,
    venue_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List calendar items with optional filters"""

    query = db.query(CalendarItem)

    # Location-based filtering: Users only see items for their assigned locations
    # Admins see all items
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles:
        # Get user's assigned venue IDs
        user_venues = db.query(UserLocation.venue_id).filter(
            UserLocation.user_id == current_user.id
        ).all()
        user_venue_ids = [v[0] for v in user_venues]

        if user_venue_ids:
            # Filter to items at user's assigned venues OR items created by the user
            query = query.filter(
                (CalendarItem.venue_id.in_(user_venue_ids)) |
                (CalendarItem.created_by == current_user.id)
            )
        else:
            # User has no assigned locations - only show items they created
            query = query.filter(CalendarItem.created_by == current_user.id)

    # Apply filters
    if start:
        query = query.filter(CalendarItem.start_at >= start)

    if end:
        query = query.filter(CalendarItem.start_at <= end)

    if item_type:
        query = query.filter(CalendarItem.item_type == item_type)

    if venue_id:
        query = query.filter(CalendarItem.venue_id == venue_id)

    items = query.order_by(CalendarItem.start_at).all()
    return items


@router.get("/calendar", response_model=List[CalendarItemResponse])
async def get_calendar_items(
    start: datetime,
    end: datetime,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get calendar items for calendar view (date range required)"""

    query = db.query(CalendarItem).filter(
        CalendarItem.start_at >= start,
        CalendarItem.start_at <= end
    )

    # Location-based filtering
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles:
        user_venues = db.query(UserLocation.venue_id).filter(
            UserLocation.user_id == current_user.id
        ).all()
        user_venue_ids = [v[0] for v in user_venues]

        if user_venue_ids:
            query = query.filter(
                (CalendarItem.venue_id.in_(user_venue_ids)) |
                (CalendarItem.created_by == current_user.id)
            )
        else:
            query = query.filter(CalendarItem.created_by == current_user.id)

    items = query.order_by(CalendarItem.start_at).all()
    return items


@router.get("/{item_id}", response_model=CalendarItemResponse)
async def get_calendar_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific calendar item by ID"""

    item = db.query(CalendarItem).filter(CalendarItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Calendar item not found")

    # Check permissions
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles:
        # User can view if they created it or have access to the venue
        if item.created_by != current_user.id:
            if item.venue_id:
                user_venue = db.query(UserLocation).filter(
                    UserLocation.user_id == current_user.id,
                    UserLocation.venue_id == item.venue_id
                ).first()

                if not user_venue:
                    raise HTTPException(status_code=403, detail="Access denied")
            else:
                raise HTTPException(status_code=403, detail="Access denied")

    return item


@router.put("/{item_id}", response_model=CalendarItemResponse)
async def update_calendar_item(
    item_id: UUID,
    item_data: CalendarItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a calendar item"""

    item = db.query(CalendarItem).filter(CalendarItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Calendar item not found")

    # Check permissions - only creator or admin can edit
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles and item.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can edit this item")

    # If changing venue, check new venue access
    if item_data.venue_id and item_data.venue_id != item.venue_id:
        if "admin" not in user_roles:
            user_venue = db.query(UserLocation).filter(
                UserLocation.user_id == current_user.id,
                UserLocation.venue_id == item_data.venue_id
            ).first()

            if not user_venue:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this location"
                )

    # Update fields
    for field, value in item_data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    return item


@router.delete("/{item_id}")
async def delete_calendar_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a calendar item"""

    item = db.query(CalendarItem).filter(CalendarItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Calendar item not found")

    # Check permissions - only creator or admin can delete
    user_roles = [role.code for role in current_user.roles]
    if "admin" not in user_roles and item.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can delete this item")

    db.delete(item)
    db.commit()

    return {"message": "Calendar item deleted successfully"}
