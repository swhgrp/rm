"""
Waste API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime

from restaurant_inventory.core.deps import get_db, get_current_user, filter_by_user_locations
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.models import User, WasteRecord, Location, MasterItem, Inventory
from restaurant_inventory.schemas.waste import (
    WasteRecordCreate, WasteRecordUpdate, WasteRecordInDB,
    WasteRecordWithDetails, WasteRecordList
)

router = APIRouter()


@router.get("/", response_model=List[WasteRecordList])
def list_waste_records(
    skip: int = 0,
    limit: int = 100,
    location_id: Optional[int] = None,
    reason_code: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all waste records with optional filtering (filtered by user's assigned locations)"""
    query = db.query(WasteRecord).options(
        joinedload(WasteRecord.location),
        joinedload(WasteRecord.master_item),
        joinedload(WasteRecord.recorder)
    )

    # Apply user location filtering FIRST
    query = filter_by_user_locations(query, WasteRecord.location_id, current_user)

    # Apply filters
    if location_id:
        query = query.filter(WasteRecord.location_id == location_id)
    if reason_code:
        query = query.filter(WasteRecord.reason_code == reason_code)
    if start_date:
        query = query.filter(WasteRecord.waste_date >= start_date)
    if end_date:
        query = query.filter(WasteRecord.waste_date <= end_date)

    query = query.order_by(desc(WasteRecord.waste_date))
    waste_records = query.offset(skip).limit(limit).all()

    # Format response
    result = []
    for record in waste_records:
        # Use the stored unit_of_measure if available, otherwise fall back to master item's UOM
        unit = record.unit_of_measure or (record.master_item.unit_of_measure if record.master_item else None)
        result.append(WasteRecordList(
            id=record.id,
            location_id=record.location_id,
            location_name=record.location.name if record.location else None,
            master_item_id=record.master_item_id,
            item_name=record.master_item.name if record.master_item else None,
            quantity_wasted=float(record.quantity_wasted),
            unit=unit,
            total_cost=record.total_cost,
            reason_code=record.reason_code,
            waste_date=record.waste_date,
            recorded_by_name=record.recorder.full_name if record.recorder else None
        ))

    return result


@router.get("/{waste_id}", response_model=WasteRecordWithDetails)
def get_waste_record(
    waste_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get waste record details by ID"""
    record = db.query(WasteRecord).options(
        joinedload(WasteRecord.location),
        joinedload(WasteRecord.master_item),
        joinedload(WasteRecord.recorder)
    ).filter(WasteRecord.id == waste_id).first()

    if not record:
        raise HTTPException(status_code=404, detail="Waste record not found")

    # Build response with related data
    record_dict = WasteRecordInDB.from_orm(record).dict()
    record_dict["location_name"] = record.location.name if record.location else None
    record_dict["item_name"] = record.master_item.name if record.master_item else None
    record_dict["item_unit"] = record.master_item.unit.name if record.master_item and record.master_item.unit else None
    record_dict["recorded_by_name"] = record.recorder.full_name if record.recorder else None

    return WasteRecordWithDetails(**record_dict)


@router.post("/", response_model=WasteRecordInDB, status_code=status.HTTP_201_CREATED)
def create_waste_record(
    waste: WasteRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new waste record"""
    
    # Validate location exists
    location = db.query(Location).filter(Location.id == waste.location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Validate master item exists
    master_item = db.query(MasterItem).filter(MasterItem.id == waste.master_item_id).first()
    if not master_item:
        raise HTTPException(status_code=404, detail="Master item not found")

    # Get unit cost from master item
    unit_cost = master_item.current_cost or master_item.average_cost or 0
    total_cost = float(waste.quantity_wasted) * float(unit_cost)

    # Find related inventory record
    inventory_record = db.query(Inventory).filter(
        Inventory.master_item_id == waste.master_item_id,
        Inventory.location_id == waste.location_id
    ).first()

    # Create waste record
    waste_record = WasteRecord(
        location_id=waste.location_id,
        master_item_id=waste.master_item_id,
        inventory_id=inventory_record.id if inventory_record else None,
        quantity_wasted=waste.quantity_wasted,
        unit_of_measure=waste.unit_of_measure,
        unit_cost=unit_cost,
        total_cost=total_cost,
        reason_code=waste.reason_code,
        description=waste.description,
        waste_date=waste.waste_date,
        recorded_by=current_user.id
    )

    db.add(waste_record)

    # Update inventory quantity (reduce by wasted amount)
    if inventory_record:
        inventory_record.current_quantity = float(inventory_record.current_quantity) - waste.quantity_wasted
        if inventory_record.current_quantity < 0:
            inventory_record.current_quantity = 0

    db.commit()
    db.refresh(waste_record)

    # Log action
    log_audit_event(
        db=db,
        user=current_user,
        action="waste_create",
        entity_type="waste",
        entity_id=waste_record.id,
        changes={
            "item": master_item.name,
            "quantity": waste.quantity_wasted,
            "reason": waste.reason_code,
            "cost": float(total_cost)
        }
    )

    return WasteRecordInDB.from_orm(waste_record)


@router.put("/{waste_id}", response_model=WasteRecordInDB)
def update_waste_record(
    waste_id: int,
    waste_update: WasteRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a waste record"""
    waste_record = db.query(WasteRecord).filter(WasteRecord.id == waste_id).first()
    if not waste_record:
        raise HTTPException(status_code=404, detail="Waste record not found")

    # Track changes for audit
    changes = {}
    update_data = waste_update.dict(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(waste_record, field):
            old_value = getattr(waste_record, field)
            if old_value != value:
                changes[field] = {"old": old_value, "new": value}
                setattr(waste_record, field, value)

    # Recalculate total cost if quantity changed
    if "quantity_wasted" in update_data:
        master_item = db.query(MasterItem).filter(MasterItem.id == waste_record.master_item_id).first()
        if master_item:
            unit_cost = master_item.current_cost or master_item.average_cost or 0
            waste_record.total_cost = float(waste_record.quantity_wasted) * float(unit_cost)

    if changes:
        db.commit()
        db.refresh(waste_record)

        log_audit_event(
            db=db,
            user=current_user,
            action="waste_update",
            entity_type="waste",
            entity_id=waste_record.id,
            changes=changes
        )

    return WasteRecordInDB.from_orm(waste_record)


@router.delete("/{waste_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_waste_record(
    waste_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a waste record"""
    waste_record = db.query(WasteRecord).filter(WasteRecord.id == waste_id).first()
    if not waste_record:
        raise HTTPException(status_code=404, detail="Waste record not found")

    db.delete(waste_record)
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="waste_delete",
        entity_type="waste",
        entity_id=waste_id,
        changes={"quantity": float(waste_record.quantity_wasted), "reason": waste_record.reason_code}
    )

    return None
