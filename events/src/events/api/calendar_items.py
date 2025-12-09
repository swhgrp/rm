"""Calendar items API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from uuid import UUID, uuid4

from events.core.database import get_db
from events.core.deps import require_auth
from events.models.user import User, UserLocation
from events.models.calendar_item import CalendarItem, RecurrencePattern
from events.schemas.calendar_item import (
    CalendarItemCreate,
    CalendarItemUpdate,
    CalendarItemResponse
)

router = APIRouter(prefix="/calendar-items", tags=["calendar-items"])


def generate_occurrences(item: CalendarItem, start: datetime, end: datetime) -> List[dict]:
    """Generate virtual occurrences for a recurring calendar item within a date range"""
    occurrences = []

    if item.recurrence_pattern == RecurrencePattern.NONE:
        return occurrences

    # Calculate duration if end_at exists
    duration = None
    if item.end_at:
        duration = item.end_at - item.start_at

    # Start generating from the item's start date
    current_date = item.start_at

    # Determine recurrence end
    recurrence_end = end
    if item.recurrence_end_date:
        recurrence_end_dt = datetime.combine(item.recurrence_end_date, datetime.max.time())
        if recurrence_end_dt < recurrence_end:
            recurrence_end = recurrence_end_dt

    # Generate occurrences based on pattern
    while current_date <= recurrence_end:
        # Skip the original item date (it's already in the database)
        if current_date != item.start_at and current_date >= start:
            occurrence_end = None
            if duration:
                occurrence_end = current_date + duration

            occurrences.append({
                'id': str(item.id),  # Use parent ID for reference
                'title': item.title,
                'item_type': item.item_type,
                'description': item.description,
                'start_at': current_date,
                'end_at': occurrence_end,
                'location_id': item.location_id,
                'recurrence_pattern': item.recurrence_pattern,
                'recurrence_end_date': item.recurrence_end_date,
                'recurrence_days_of_week': item.recurrence_days_of_week,
                'created_by': item.created_by,
                'created_at': item.created_at,
                'updated_at': item.updated_at,
                'location': item.location,
                'creator': item.creator,
                'parent_item_id': item.id,
                'is_occurrence': True
            })

        # Calculate next occurrence
        if item.recurrence_pattern == RecurrencePattern.DAILY:
            current_date = current_date + timedelta(days=1)
        elif item.recurrence_pattern == RecurrencePattern.WEEKLY:
            if item.recurrence_days_of_week:
                # Find next day of week that matches
                found_next = False
                for i in range(1, 8):
                    next_date = current_date + timedelta(days=i)
                    if next_date.weekday() in item.recurrence_days_of_week:
                        current_date = next_date
                        found_next = True
                        break
                if not found_next:
                    current_date = current_date + timedelta(weeks=1)
            else:
                current_date = current_date + timedelta(weeks=1)
        elif item.recurrence_pattern == RecurrencePattern.BIWEEKLY:
            current_date = current_date + timedelta(weeks=2)
        elif item.recurrence_pattern == RecurrencePattern.MONTHLY:
            current_date = current_date + relativedelta(months=1)
        elif item.recurrence_pattern == RecurrencePattern.YEARLY:
            current_date = current_date + relativedelta(years=1)
        else:
            break

        # Safety: limit to 365 occurrences to prevent infinite loops
        if len(occurrences) >= 365:
            break

    return occurrences


@router.post("/", response_model=CalendarItemResponse)
async def create_calendar_item(
    item_data: CalendarItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new calendar item"""

    # Check if user has access to the specified location (location-based permissions)
    if item_data.location_id:
        user_roles = [role.code for role in current_user.roles]
        if "admin" not in user_roles:
            # Check if user has access to this location
            user_location = db.query(UserLocation).filter(
                UserLocation.user_id == current_user.id,
                UserLocation.venue_id == item_data.location_id
            ).first()

            if not user_location:
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
    location_id: Optional[UUID] = None,
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
            # Filter to items at user's assigned locations OR items created by the user
            query = query.filter(
                (CalendarItem.location_id.in_(user_venue_ids)) |
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

    if location_id:
        query = query.filter(CalendarItem.location_id == location_id)

    items = query.order_by(CalendarItem.start_at).all()
    return items


@router.get("/calendar")
async def get_calendar_items(
    start: datetime,
    end: datetime,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get calendar items for calendar view (date range required), including recurring occurrences"""

    # Get items that either:
    # 1. Start within the date range (non-recurring or first occurrence)
    # 2. Are recurring and could have occurrences in this range
    query = db.query(CalendarItem).filter(
        # Either item starts in range, or it's recurring and started before the range end
        ((CalendarItem.start_at >= start) & (CalendarItem.start_at <= end)) |
        ((CalendarItem.recurrence_pattern != RecurrencePattern.NONE) & (CalendarItem.start_at <= end))
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
                (CalendarItem.location_id.in_(user_venue_ids)) |
                (CalendarItem.created_by == current_user.id)
            )
        else:
            query = query.filter(CalendarItem.created_by == current_user.id)

    items = query.order_by(CalendarItem.start_at).all()

    # Build result with recurring occurrences
    result = []
    for item in items:
        # Add the original item if it's in range
        if start <= item.start_at <= end:
            item_dict = {
                'id': item.id,
                'title': item.title,
                'item_type': item.item_type,
                'description': item.description,
                'start_at': item.start_at,
                'end_at': item.end_at,
                'location_id': item.location_id,
                'recurrence_pattern': item.recurrence_pattern,
                'recurrence_end_date': item.recurrence_end_date,
                'recurrence_days_of_week': item.recurrence_days_of_week,
                'created_by': item.created_by,
                'created_at': item.created_at,
                'updated_at': item.updated_at,
                'location': item.location,
                'creator': item.creator,
                'parent_item_id': item.parent_item_id,
                'is_occurrence': False
            }
            result.append(item_dict)

        # Generate recurring occurrences
        if item.recurrence_pattern != RecurrencePattern.NONE:
            occurrences = generate_occurrences(item, start, end)
            result.extend(occurrences)

    # Sort by start_at
    result.sort(key=lambda x: x['start_at'])
    return result


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
        # User can view if they created it or have access to the location
        if item.created_by != current_user.id:
            if item.location_id:
                user_location = db.query(UserLocation).filter(
                    UserLocation.user_id == current_user.id,
                    UserLocation.venue_id == item.location_id
                ).first()

                if not user_location:
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

    # If changing location, check new location access
    if item_data.location_id and item_data.location_id != item.location_id:
        if "admin" not in user_roles:
            user_location = db.query(UserLocation).filter(
                UserLocation.user_id == current_user.id,
                UserLocation.venue_id == item_data.location_id
            ).first()

            if not user_location:
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
