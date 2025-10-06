"""
Complete Transfer API endpoints with approval workflow and inventory integration
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime, timezone
from decimal import Decimal

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models.user import User
from restaurant_inventory.models.transfer import Transfer, TransferStatus
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.schemas.transfer import TransferCreate, TransferUpdate, TransferResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

router = APIRouter()

def require_manager_or_admin(current_user: User = Depends(get_current_user)):
    """Ensure user has manager or admin privileges"""
    if current_user.role not in ["Manager", "Admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager or Admin access required"
        )
    return current_user

def require_admin(current_user: User = Depends(get_current_user)):
    """Ensure user has admin privileges"""
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

@router.get("/", response_model=List[TransferResponse])
async def get_transfers(
    status_filter: Optional[TransferStatus] = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get transfers with optional filtering"""
    query = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester),
        joinedload(Transfer.approver)
    )
    
    # Apply filters
    if status_filter:
        query = query.filter(Transfer.status == status_filter)
    
    if location_id:
        query = query.filter(
            or_(
                Transfer.from_location_id == location_id,
                Transfer.to_location_id == location_id
            )
        )
    
    # If user is staff, only show transfers they requested or that involve their locations
    if current_user.role == "Staff":
        query = query.filter(Transfer.requested_by == current_user.id)
    
    transfers = query.order_by(Transfer.created_at.desc()).all()
    
    # Build response with related data
    result = []
    for transfer in transfers:
        transfer_data = TransferResponse(
            id=transfer.id,
            from_location_id=transfer.from_location_id,
            to_location_id=transfer.to_location_id,
            master_item_id=transfer.master_item_id,
            quantity=transfer.quantity,
            unit_cost=transfer.unit_cost,
            total_value=transfer.total_value,
            status=transfer.status,
            requested_by=transfer.requested_by,
            approved_by=transfer.approved_by,
            notes=transfer.notes,
            reason=transfer.reason,
            created_at=transfer.created_at,
            updated_at=transfer.updated_at,
            approved_at=transfer.approved_at,
            completed_at=transfer.completed_at,
            from_location_name=transfer.from_location.name,
            to_location_name=transfer.to_location.name,
            item_name=transfer.master_item.name,
            requester_name=transfer.requester.username,
            approver_name=transfer.approver.username if transfer.approver else None
        )
        result.append(transfer_data)
    
    return result

@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific transfer by ID"""
    transfer = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester),
        joinedload(Transfer.approver)
    ).filter(Transfer.id == transfer_id).first()
    
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    # Check permissions
    if (current_user.role == "Staff" and
        transfer.requested_by != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this transfer"
        )
    
    return TransferResponse(
        id=transfer.id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        master_item_id=transfer.master_item_id,
        quantity=transfer.quantity,
        unit_cost=transfer.unit_cost,
        total_value=transfer.total_value,
        status=transfer.status,
        requested_by=transfer.requested_by,
        approved_by=transfer.approved_by,
        notes=transfer.notes,
        reason=transfer.reason,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
        approved_at=transfer.approved_at,
        completed_at=transfer.completed_at,
        from_location_name=transfer.from_location.name,
        to_location_name=transfer.to_location.name,
        item_name=transfer.master_item.name,
        requester_name=transfer.requester.username,
        approver_name=transfer.approver.username if transfer.approver else None
    )

@router.post("/", response_model=TransferResponse)
async def create_transfer(
    transfer_data: TransferCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new transfer request"""
    
    # Validate locations exist and are different
    if transfer_data.from_location_id == transfer_data.to_location_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination locations must be different"
        )
    
    from_location = db.query(Location).filter(Location.id == transfer_data.from_location_id).first()
    to_location = db.query(Location).filter(Location.id == transfer_data.to_location_id).first()
    
    if not from_location or not to_location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both locations not found"
        )
    
    # Validate item exists
    item = db.query(MasterItem).filter(MasterItem.id == transfer_data.master_item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    # Check source location has sufficient inventory
    source_inventory = db.query(Inventory).filter(
        and_(
            Inventory.location_id == transfer_data.from_location_id,
            Inventory.master_item_id == transfer_data.master_item_id
        )
    ).first()

    if not source_inventory or source_inventory.current_quantity < transfer_data.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory. Available: {source_inventory.current_quantity if source_inventory else 0}, Requested: {transfer_data.quantity}"
        )
    
    # Calculate total value if unit cost provided
    total_value = None
    unit_cost = transfer_data.unit_cost
    if not unit_cost and source_inventory:
        unit_cost = source_inventory.unit_cost
    
    if unit_cost:
        total_value = transfer_data.quantity * unit_cost
    
    # Create transfer
    transfer = Transfer(
        from_location_id=transfer_data.from_location_id,
        to_location_id=transfer_data.to_location_id,
        master_item_id=transfer_data.master_item_id,
        quantity=transfer_data.quantity,
        unit_cost=unit_cost,
        total_value=total_value,
        status=TransferStatus.PENDING,  # Start as pending for approval
        requested_by=current_user.id,
        notes=transfer_data.notes,
        reason=transfer_data.reason
    )
    
    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="transfer",
        entity_id=transfer.id,
        user=current_user,
        changes={
            "new": {
                "from_location_id": transfer.from_location_id,
                "to_location_id": transfer.to_location_id,
                "from_location": from_location.name,
                "to_location": to_location.name,
                "item": item.name,
                "quantity": float(transfer.quantity),
                "status": transfer.status.value
            }
        },
        request=request
    )

    # Load relationships for response
    transfer = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester)
    ).filter(Transfer.id == transfer.id).first()
    
    return TransferResponse(
        id=transfer.id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        master_item_id=transfer.master_item_id,
        quantity=transfer.quantity,
        unit_cost=transfer.unit_cost,
        total_value=transfer.total_value,
        status=transfer.status,
        requested_by=transfer.requested_by,
        approved_by=transfer.approved_by,
        notes=transfer.notes,
        reason=transfer.reason,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
        approved_at=transfer.approved_at,
        completed_at=transfer.completed_at,
        from_location_name=transfer.from_location.name,
        to_location_name=transfer.to_location.name,
        item_name=transfer.master_item.name,
        requester_name=transfer.requester.username,
        approver_name=None
    )

@router.put("/{transfer_id}/approve", response_model=TransferResponse)
async def approve_transfer(
    transfer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Approve a pending transfer"""
    
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    if transfer.status != TransferStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve transfer in {transfer.status.value} status"
        )
    
    # Re-check inventory availability
    source_inventory = db.query(Inventory).filter(
        and_(
            Inventory.location_id == transfer.from_location_id,
            Inventory.master_item_id == transfer.master_item_id
        )
    ).first()

    if not source_inventory or source_inventory.current_quantity < transfer.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory. Available: {source_inventory.current_quantity if source_inventory else 0}"
        )
    
    # Update transfer
    transfer.status = TransferStatus.APPROVED
    transfer.approved_by = current_user.id
    transfer.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(transfer)

    # Log audit event
    log_audit_event(
        db=db,
        action="APPROVE",
        entity_type="transfer",
        entity_id=transfer.id,
        user=current_user,
        changes={
            "old": {"status": "PENDING"},
            "new": {"status": "APPROVED", "approved_by": current_user.username}
        },
        request=request
    )
    
    # Load relationships for response
    transfer = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester),
        joinedload(Transfer.approver)
    ).filter(Transfer.id == transfer.id).first()
    
    return TransferResponse(
        id=transfer.id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        master_item_id=transfer.master_item_id,
        quantity=transfer.quantity,
        unit_cost=transfer.unit_cost,
        total_value=transfer.total_value,
        status=transfer.status,
        requested_by=transfer.requested_by,
        approved_by=transfer.approved_by,
        notes=transfer.notes,
        reason=transfer.reason,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
        approved_at=transfer.approved_at,
        completed_at=transfer.completed_at,
        from_location_name=transfer.from_location.name,
        to_location_name=transfer.to_location.name,
        item_name=transfer.master_item.name,
        requester_name=transfer.requester.username,
        approver_name=transfer.approver.username
    )

@router.put("/{transfer_id}/complete", response_model=TransferResponse)
async def complete_transfer(
    transfer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Complete an approved transfer and update inventory"""
    
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    if transfer.status != TransferStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete transfer in {transfer.status.value} status"
        )

    try:
        # Get source inventory
        source_inventory = db.query(Inventory).filter(
            and_(
                Inventory.location_id == transfer.from_location_id,
                Inventory.master_item_id == transfer.master_item_id
            )
        ).with_for_update().first()  # Lock row for update

        if not source_inventory or source_inventory.current_quantity < transfer.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient inventory. Available: {source_inventory.current_quantity if source_inventory else 0}"
            )

        # Update source inventory (subtract)
        source_inventory.current_quantity -= transfer.quantity
        if source_inventory.unit_cost:
            source_inventory.total_value = source_inventory.current_quantity * source_inventory.unit_cost

        # Get or create destination inventory
        dest_inventory = db.query(Inventory).filter(
            and_(
                Inventory.location_id == transfer.to_location_id,
                Inventory.master_item_id == transfer.master_item_id
            )
        ).with_for_update().first()  # Lock row for update

        if dest_inventory:
            # Update existing inventory
            old_quantity = dest_inventory.current_quantity
            dest_inventory.current_quantity += transfer.quantity

            # Update unit cost with weighted average if transfer has cost
            if transfer.unit_cost and dest_inventory.unit_cost:
                total_value = (old_quantity * dest_inventory.unit_cost) + (transfer.quantity * transfer.unit_cost)
                dest_inventory.unit_cost = total_value / dest_inventory.current_quantity
                dest_inventory.total_value = total_value
            elif dest_inventory.unit_cost:
                dest_inventory.total_value = dest_inventory.current_quantity * dest_inventory.unit_cost
        else:
            # Create new inventory record
            dest_inventory = Inventory(
                location_id=transfer.to_location_id,
                master_item_id=transfer.master_item_id,
                current_quantity=transfer.quantity,
                unit_cost=transfer.unit_cost or source_inventory.unit_cost,
                total_value=(transfer.quantity * (transfer.unit_cost or source_inventory.unit_cost)) if (transfer.unit_cost or source_inventory.unit_cost) else None,
                reorder_level=Decimal('10'),  # Default reorder level
                max_level=Decimal('100')      # Default max level
            )
            db.add(dest_inventory)

        # Update transfer status
        transfer.status = TransferStatus.COMPLETED
        transfer.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(transfer)

        # Log audit event
        log_audit_event(
            db=db,
            action="COMPLETE",
            entity_type="transfer",
            entity_id=transfer.id,
            user=current_user,
            changes={
                "old": {"status": "APPROVED"},
                "new": {"status": "COMPLETED", "completed_by": current_user.username}
            },
            request=request
        )

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer completion failed: {str(e)}"
        )
    
    # Load relationships for response
    transfer = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester),
        joinedload(Transfer.approver)
    ).filter(Transfer.id == transfer.id).first()
    
    return TransferResponse(
        id=transfer.id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        master_item_id=transfer.master_item_id,
        quantity=transfer.quantity,
        unit_cost=transfer.unit_cost,
        total_value=transfer.total_value,
        status=transfer.status,
        requested_by=transfer.requested_by,
        approved_by=transfer.approved_by,
        notes=transfer.notes,
        reason=transfer.reason,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
        approved_at=transfer.approved_at,
        completed_at=transfer.completed_at,
        from_location_name=transfer.from_location.name,
        to_location_name=transfer.to_location.name,
        item_name=transfer.master_item.name,
        requester_name=transfer.requester.username,
        approver_name=transfer.approver.username
    )

@router.put("/{transfer_id}/cancel", response_model=TransferResponse)
async def cancel_transfer(
    transfer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a transfer (if user created it or user is manager/admin)"""
    
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    # Check permissions
    if (current_user.role == "Staff" and
        transfer.requested_by != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this transfer"
        )
    
    if transfer.status in [TransferStatus.COMPLETED, TransferStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel transfer in {transfer.status.value} status"
        )
    
    old_status = transfer.status.value
    transfer.status = TransferStatus.CANCELLED

    db.commit()
    db.refresh(transfer)

    # Log audit event
    log_audit_event(
        db=db,
        action="CANCEL",
        entity_type="transfer",
        entity_id=transfer.id,
        user=current_user,
        changes={
            "old": {"status": old_status},
            "new": {"status": "CANCELLED", "cancelled_by": current_user.username}
        },
        request=request
    )

    # Load relationships for response
    transfer = db.query(Transfer).options(
        joinedload(Transfer.from_location),
        joinedload(Transfer.to_location),
        joinedload(Transfer.master_item),
        joinedload(Transfer.requester),
        joinedload(Transfer.approver)
    ).filter(Transfer.id == transfer.id).first()
    
    return TransferResponse(
        id=transfer.id,
        from_location_id=transfer.from_location_id,
        to_location_id=transfer.to_location_id,
        master_item_id=transfer.master_item_id,
        quantity=transfer.quantity,
        unit_cost=transfer.unit_cost,
        total_value=transfer.total_value,
        status=transfer.status,
        requested_by=transfer.requested_by,
        approved_by=transfer.approved_by,
        notes=transfer.notes,
        reason=transfer.reason,
        created_at=transfer.created_at,
        updated_at=transfer.updated_at,
        approved_at=transfer.approved_at,
        completed_at=transfer.completed_at,
        from_location_name=transfer.from_location.name,
        to_location_name=transfer.to_location.name,
        item_name=transfer.master_item.name,
        requester_name=transfer.requester.username,
        approver_name=transfer.approver.username if transfer.approver else None
    )

@router.delete("/{transfer_id}")
async def delete_transfer(
    transfer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a transfer (admin only, and only if not completed)"""
    
    transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )
    
    if transfer.status == TransferStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete completed transfer"
        )

    # Load relationships before deletion for audit log
    from_location = transfer.from_location.name if transfer.from_location else "Unknown"
    to_location = transfer.to_location.name if transfer.to_location else "Unknown"
    item = transfer.master_item.name if transfer.master_item else "Unknown"

    # Log audit event before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="transfer",
        entity_id=transfer.id,
        user=current_user,
        changes={
            "old": {
                "from_location": from_location,
                "to_location": to_location,
                "item": item,
                "quantity": float(transfer.quantity),
                "status": transfer.status.value
            }
        },
        request=request
    )

    db.delete(transfer)
    db.commit()

    return {"success": True, "message": "Transfer deleted"}

@router.get("/pending/count")
async def get_pending_transfers_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Get count of pending transfers (for dashboard alerts)"""

    count = db.query(Transfer).filter(Transfer.status == TransferStatus.PENDING).count()

    return {"pending_count": count}

@router.get("/statistics")
async def get_transfer_statistics(
    days: int = 30,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get transfer statistics for dashboard"""
    from sqlalchemy import func
    from datetime import timedelta

    # Calculate date threshold
    date_threshold = datetime.now(timezone.utc) - timedelta(days=days)

    # Build base query
    query = db.query(Transfer).filter(Transfer.created_at >= date_threshold)

    if location_id:
        query = query.filter(
            or_(
                Transfer.from_location_id == location_id,
                Transfer.to_location_id == location_id
            )
        )

    # If staff, only show their transfers
    if current_user.role == "Staff":
        query = query.filter(Transfer.requested_by == current_user.id)

    # Count by status
    pending = query.filter(Transfer.status == TransferStatus.PENDING).count()
    approved = query.filter(Transfer.status == TransferStatus.APPROVED).count()
    completed = query.filter(Transfer.status == TransferStatus.COMPLETED).count()
    cancelled = query.filter(Transfer.status == TransferStatus.CANCELLED).count()

    # Calculate total value of completed transfers
    completed_transfers = query.filter(Transfer.status == TransferStatus.COMPLETED).all()
    total_value = sum(t.total_value for t in completed_transfers if t.total_value) if completed_transfers else Decimal('0')

    # Get most transferred items
    top_items = db.query(
        MasterItem.name,
        func.count(Transfer.id).label('transfer_count'),
        func.sum(Transfer.quantity).label('total_quantity')
    ).join(
        Transfer, Transfer.master_item_id == MasterItem.id
    ).filter(
        Transfer.created_at >= date_threshold,
        Transfer.status == TransferStatus.COMPLETED
    ).group_by(
        MasterItem.name
    ).order_by(
        func.count(Transfer.id).desc()
    ).limit(5).all()

    return {
        "period_days": days,
        "summary": {
            "pending": pending,
            "approved": approved,
            "completed": completed,
            "cancelled": cancelled,
            "total": pending + approved + completed + cancelled
        },
        "total_value_completed": float(total_value),
        "top_items": [
            {
                "item_name": item[0],
                "transfer_count": item[1],
                "total_quantity": float(item[2])
            }
            for item in top_items
        ]
    }
