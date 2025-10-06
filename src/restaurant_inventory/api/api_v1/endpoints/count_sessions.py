"""
Count Session CRUD endpoints with workflow management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timezone
from decimal import Decimal

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.count_session import CountSession, CountSessionItem, CountStatus
from restaurant_inventory.models.count_template import CountTemplate, CountTemplateItem
from restaurant_inventory.models.storage_area import StorageArea
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.user import User
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.schemas.count_session import (
    CountSessionCreate,
    CountSessionUpdate,
    CountSessionResponse,
    CountSessionItemResponse,
    CountSessionItemUpdate
)

router = APIRouter()

@router.get("/", response_model=List[CountSessionResponse])
async def get_count_sessions(
    storage_area_id: int = None,
    status_filter: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all count sessions, optionally filtered"""
    query = db.query(CountSession).options(
        joinedload(CountSession.storage_area),
        joinedload(CountSession.template),
        joinedload(CountSession.started_by_user),
        joinedload(CountSession.completed_by_user),
        joinedload(CountSession.approved_by_user),
        joinedload(CountSession.items)
    )

    if storage_area_id:
        query = query.filter(CountSession.storage_area_id == storage_area_id)

    if status_filter:
        query = query.filter(CountSession.status == status_filter)

    sessions = query.order_by(CountSession.started_at.desc()).all()

    return [_format_count_session(session) for session in sessions]

@router.get("/{session_id}", response_model=CountSessionResponse)
async def get_count_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific count session with all items"""
    session = db.query(CountSession).options(
        joinedload(CountSession.storage_area),
        joinedload(CountSession.template),
        joinedload(CountSession.started_by_user),
        joinedload(CountSession.completed_by_user),
        joinedload(CountSession.approved_by_user),
        joinedload(CountSession.items).joinedload(CountSessionItem.master_item)
    ).filter(CountSession.id == session_id).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    return _format_count_session(session, include_items=True)

@router.post("/", response_model=CountSessionResponse)
async def create_count_session(
    session_data: CountSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start a new count session at location level"""

    # Verify location exists
    from restaurant_inventory.models.location import Location
    location = db.query(Location).filter(Location.id == session_data.location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )

    # Create session at location level
    session = CountSession(
        location_id=session_data.location_id,
        storage_area_id=None,  # Not used in new workflow
        template_id=None,
        name=session_data.name,
        notes=session_data.notes,
        status=CountStatus.IN_PROGRESS,
        started_by=current_user.id
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return await get_count_session(session.id, db, current_user)

@router.put("/{session_id}/items/{item_id}", response_model=CountSessionItemResponse)
async def update_count_session_item(
    session_id: int,
    item_id: int,
    item_data: CountSessionItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a specific item in the count session"""

    session = db.query(CountSession).filter(CountSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    if session.locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Count session is locked. Only managers can unlock."
        )

    count_item = db.query(CountSessionItem).filter(
        CountSessionItem.id == item_id,
        CountSessionItem.session_id == session_id
    ).first()

    if not count_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count item not found"
        )

    # Update counted quantity
    if item_data.counted_quantity is not None:
        count_item.counted_quantity = item_data.counted_quantity
        count_item.counted_at = datetime.now(timezone.utc)
        count_item.counted_by = current_user.id

        # Calculate variance
        if count_item.expected_quantity is not None:
            count_item.variance = count_item.counted_quantity - count_item.expected_quantity
            if count_item.expected_quantity > 0:
                count_item.variance_percent = (count_item.variance / count_item.expected_quantity) * 100
            else:
                count_item.variance_percent = None

            # Flag if variance is significant (>20% or absolute variance >10 units)
            if (abs(count_item.variance_percent or 0) > 20) or (abs(count_item.variance or 0) > 10):
                count_item.flagged = True

    # Update notes
    if item_data.notes is not None:
        count_item.notes = item_data.notes

    db.commit()
    db.refresh(count_item)

    return _format_count_session_item(count_item, db)

@router.post("/{session_id}/items")
async def add_item_to_count_session(
    session_id: int,
    master_item_id: int,
    storage_area_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a new item to an existing count session for a specific storage area"""

    session = db.query(CountSession).filter(CountSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    if session.locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Count session is locked"
        )

    # Check if item already in session for this storage area
    existing = db.query(CountSessionItem).filter(
        CountSessionItem.session_id == session_id,
        CountSessionItem.master_item_id == master_item_id,
        CountSessionItem.storage_area_id == storage_area_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item already in count session for this storage area"
        )

    # Get expected quantity from inventory if exists
    inventory_record = None
    if storage_area_id:
        inventory_record = db.query(Inventory).filter(
            Inventory.storage_area_id == storage_area_id,
            Inventory.master_item_id == master_item_id
        ).first()

    count_item = CountSessionItem(
        session_id=session_id,
        storage_area_id=storage_area_id,
        master_item_id=master_item_id,
        inventory_id=inventory_record.id if inventory_record else None,
        expected_quantity=inventory_record.current_quantity if inventory_record else None,
        is_new_item=True  # Mark as added during count
    )

    db.add(count_item)
    db.commit()
    db.refresh(count_item)

    return _format_count_session_item(count_item, db)

@router.post("/{session_id}/complete")
async def complete_count_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark count session as completed"""

    session = db.query(CountSession).filter(CountSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    if session.status != CountStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete session with status {session.status}"
        )

    session.status = CountStatus.COMPLETED
    session.completed_by = current_user.id
    session.completed_at = datetime.now(timezone.utc)

    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="UPDATE",
        entity_type="count_session",
        entity_id=session.id,
        user=current_user,
        changes={"status": "COMPLETED"},
        request=request
    )

    return {"message": "Count session completed successfully", "session_id": session.id}

@router.post("/{session_id}/approve")
async def approve_count_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Approve count session and update inventory (Manager/Admin only)"""

    session = db.query(CountSession).options(
        joinedload(CountSession.items)
    ).filter(CountSession.id == session_id).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    if session.status != CountStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only approve completed count sessions"
        )

    # Update inventory records based on inventory type
    inventory_updates = []

    for item in session.items:
        # Determine the final quantity based on inventory type
        final_quantity = None

        if item.counted_quantity is not None:
            # Item was counted
            final_quantity = item.counted_quantity
        elif session.inventory_type and session.inventory_type.value == 'FULL':
            # FULL inventory: uncounted items are assumed to be 0
            final_quantity = 0
        # PARTIAL inventory: skip uncounted items (final_quantity stays None)

        if final_quantity is not None:
            if item.inventory_id:
                # Update existing inventory record
                inventory_record = db.query(Inventory).filter(Inventory.id == item.inventory_id).first()
                if inventory_record:
                    old_qty = float(inventory_record.current_quantity)
                    new_qty = float(final_quantity)

                    inventory_record.current_quantity = final_quantity
                    inventory_record.last_count_date = datetime.now(timezone.utc)
                    if inventory_record.unit_cost:
                        inventory_record.total_value = inventory_record.unit_cost * final_quantity

                    # Track the change for audit
                    inventory_updates.append({
                        'storage_area_id': item.storage_area_id,
                        'storage_area_name': item.storage_area.name if item.storage_area else None,
                        'item_name': item.master_item.name if item.master_item else None,
                        'master_item_id': item.master_item_id,
                        'old_quantity': old_qty,
                        'new_quantity': new_qty,
                        'variance': new_qty - old_qty,
                        'was_counted': item.counted_quantity is not None
                    })
            else:
                # Create new inventory record for items found during count
                master_item = db.query(MasterItem).filter(MasterItem.id == item.master_item_id).first()
                if master_item:
                    inventory_record = Inventory(
                        location_id=session.location_id,
                        storage_area_id=item.storage_area_id,
                        master_item_id=item.master_item_id,
                        current_quantity=final_quantity,
                        unit_cost=master_item.current_cost,
                        last_count_date=datetime.now(timezone.utc)
                    )
                    if inventory_record.unit_cost:
                        inventory_record.total_value = inventory_record.unit_cost * final_quantity
                    db.add(inventory_record)

                    # Track the change for audit
                    inventory_updates.append({
                        'storage_area_id': item.storage_area_id,
                        'storage_area_name': item.storage_area.name if item.storage_area else None,
                        'item_name': master_item.name,
                        'master_item_id': item.master_item_id,
                        'old_quantity': 0,
                        'new_quantity': float(final_quantity),
                        'variance': float(final_quantity),
                        'was_counted': item.counted_quantity is not None
                    })

    # Mark session as approved and locked
    session.status = CountStatus.APPROVED
    session.approved_by = current_user.id
    session.approved_at = datetime.now(timezone.utc)
    session.locked = True

    db.commit()

    # Log audit event for count session approval
    log_audit_event(
        db=db,
        action="APPROVE",
        entity_type="count_session",
        entity_id=session.id,
        user=current_user,
        changes={
            "status": "APPROVED",
            "locked": True,
            "inventory_type": session.inventory_type.value if session.inventory_type else "PARTIAL",
            "items_updated": len(inventory_updates),
            "inventory_updates": inventory_updates
        },
        request=request
    )

    # Log individual inventory updates
    for update in inventory_updates:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="inventory",
            entity_id=None,  # No single inventory ID for composite updates
            user=current_user,
            changes={
                "count_session_id": session.id,
                "count_session_name": session.name,
                "storage_area_id": update['storage_area_id'],
                "storage_area": update['storage_area_name'],
                "master_item_id": update['master_item_id'],
                "item_name": update['item_name'],
                "old_quantity": update['old_quantity'],
                "new_quantity": update['new_quantity'],
                "variance": update['variance'],
                "was_counted": update['was_counted'],
                "set_to_zero": not update['was_counted'] and update['new_quantity'] == 0
            },
            request=request
        )

    return {
        "message": "Count session approved and inventory updated",
        "session_id": session.id,
        "items_updated": len(inventory_updates),
        "inventory_type": session.inventory_type.value if session.inventory_type else "PARTIAL"
    }

@router.post("/{session_id}/unlock")
async def unlock_count_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Unlock a locked count session (Manager/Admin only)"""

    session = db.query(CountSession).filter(CountSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count session not found"
        )

    session.locked = False
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="UPDATE",
        entity_type="count_session",
        entity_id=session.id,
        user=current_user,
        changes={"locked": False},
        request=request
    )

    return {"message": "Count session unlocked", "session_id": session.id}

def _format_count_session(session: CountSession, include_items: bool = False) -> CountSessionResponse:
    """Helper to format count session response"""
    items_list = []
    counted_items = 0
    flagged_items = 0
    new_items = 0

    if include_items:
        for item in session.items:
            items_list.append(_format_count_session_item(item, None))
            if item.counted_quantity is not None:
                counted_items += 1
            if item.flagged:
                flagged_items += 1
            if item.is_new_item:
                new_items += 1
    else:
        # Just calculate counts
        counted_items = sum(1 for item in session.items if item.counted_quantity is not None)
        flagged_items = sum(1 for item in session.items if item.flagged)
        new_items = sum(1 for item in session.items if item.is_new_item)

    return CountSessionResponse(
        id=session.id,
        location_id=session.location_id,
        storage_area_id=session.storage_area_id,
        template_id=session.template_id,
        name=session.name,
        notes=session.notes,
        inventory_type=session.inventory_type.value if session.inventory_type else "PARTIAL",
        status=session.status.value,
        locked=session.locked,
        started_by=session.started_by,
        started_at=session.started_at,
        completed_by=session.completed_by,
        completed_at=session.completed_at,
        approved_by=session.approved_by,
        approved_at=session.approved_at,
        storage_area_name=session.storage_area.name if session.storage_area else None,
        location_name=session.location.name if session.location else (session.storage_area.location.name if session.storage_area and session.storage_area.location else None),
        template_name=session.template.name if session.template else None,
        started_by_name=session.started_by_user.username if session.started_by_user else None,
        completed_by_name=session.completed_by_user.username if session.completed_by_user else None,
        approved_by_name=session.approved_by_user.username if session.approved_by_user else None,
        total_items=len(session.items),
        counted_items=counted_items,
        flagged_items=flagged_items,
        new_items=new_items,
        items=items_list
    )

def _format_count_session_item(item: CountSessionItem, db: Session = None) -> CountSessionItemResponse:
    """Helper to format count session item response"""
    return CountSessionItemResponse(
        id=item.id,
        session_id=item.session_id,
        storage_area_id=item.storage_area_id,
        master_item_id=item.master_item_id,
        inventory_id=item.inventory_id,
        expected_quantity=item.expected_quantity,
        counted_quantity=item.counted_quantity,
        variance=item.variance,
        variance_percent=item.variance_percent,
        flagged=item.flagged,
        is_new_item=item.is_new_item,
        notes=item.notes,
        counted_at=item.counted_at,
        counted_by=item.counted_by,
        counted_by_name=item.counted_by_user.username if item.counted_by_user else None,
        storage_area_name=item.storage_area.name if item.storage_area else None,
        item_name=item.master_item.name if item.master_item else None,
        item_category=item.master_item.category if item.master_item else None,
        item_unit=item.master_item.unit_of_measure if item.master_item else None,
        item_barcode=item.master_item.barcode if item.master_item else None
    )

@router.delete("/{session_id}")
async def delete_count_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None
):
    """
    Delete a count session (Admin only, must be completed/approved/cancelled)
    """
    # Check if user is admin
    is_admin = current_user.role == "Admin"

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete count sessions"
        )

    # Get the session
    session = db.query(CountSession).filter(CountSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count session not found")

    # Only allow deletion of completed/approved/cancelled sessions
    if session.status not in [CountStatus.COMPLETED, CountStatus.APPROVED, CountStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete completed, approved, or cancelled count sessions"
        )

    # Log audit event before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="count_session",
        entity_id=session_id,
        user=current_user,
        request=request,
        changes={"session_name": session.name, "status": session.status.value}
    )

    # Delete the session (cascade will handle items)
    db.delete(session)
    db.commit()

    return {"message": "Count session deleted successfully"}

@router.post("/{session_id}/storage-area/{storage_area_id}/finish")
async def mark_storage_area_finished(
    session_id: int,
    storage_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a storage area as finished for this count session"""
    from restaurant_inventory.models.count_session import CountSessionStorageArea

    # Get or create the storage area record
    area_status = db.query(CountSessionStorageArea).filter(
        CountSessionStorageArea.session_id == session_id,
        CountSessionStorageArea.storage_area_id == storage_area_id
    ).first()

    if not area_status:
        area_status = CountSessionStorageArea(
            session_id=session_id,
            storage_area_id=storage_area_id,
            is_finished=True,
            finished_at=datetime.now(timezone.utc),
            finished_by=current_user.id
        )
        db.add(area_status)
    else:
        area_status.is_finished = True
        area_status.finished_at = datetime.now(timezone.utc)
        area_status.finished_by = current_user.id

    db.commit()
    db.refresh(area_status)

    return {
        "id": area_status.id,
        "session_id": area_status.session_id,
        "storage_area_id": area_status.storage_area_id,
        "is_finished": area_status.is_finished,
        "finished_at": area_status.finished_at,
        "finished_by": area_status.finished_by
    }

@router.post("/{session_id}/storage-area/{storage_area_id}/unfinish")
async def mark_storage_area_unfinished(
    session_id: int,
    storage_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a storage area as unfinished (reopen for editing)"""
    from restaurant_inventory.models.count_session import CountSessionStorageArea

    area_status = db.query(CountSessionStorageArea).filter(
        CountSessionStorageArea.session_id == session_id,
        CountSessionStorageArea.storage_area_id == storage_area_id
    ).first()

    if area_status:
        area_status.is_finished = False
        area_status.finished_at = None
        area_status.finished_by = None
        db.commit()
        db.refresh(area_status)

    return {
        "id": area_status.id if area_status else None,
        "session_id": session_id,
        "storage_area_id": storage_area_id,
        "is_finished": False
    }

@router.get("/{session_id}/storage-areas/status")
async def get_storage_areas_status(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get finished status for all storage areas in this session"""
    from restaurant_inventory.models.count_session import CountSessionStorageArea

    statuses = db.query(CountSessionStorageArea).filter(
        CountSessionStorageArea.session_id == session_id
    ).all()

    return [
        {
            "storage_area_id": s.storage_area_id,
            "is_finished": s.is_finished,
            "finished_at": s.finished_at,
            "finished_by": s.finished_by
        }
        for s in statuses
    ]