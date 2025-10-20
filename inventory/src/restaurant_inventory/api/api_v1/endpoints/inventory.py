"""
Inventory CRUD endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin, filter_by_user_locations
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.inventory_transaction import InventoryTransaction, TransactionType
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.user import User
from restaurant_inventory.models.storage_area import StorageArea
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.schemas.inventory import InventoryCreate, InventoryUpdate, InventoryResponse
from datetime import datetime, date

class InventoryCountUpdate(BaseModel):
    new_quantity: float

router = APIRouter()

@router.get("/", response_model=List[InventoryResponse])
async def get_inventory_records(
    skip: int = 0,
    limit: int = 100,
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    storage_area_id: Optional[int] = Query(None, description="Filter by storage area ID"),
    category: Optional[str] = Query(None, description="Filter by item category"),
    low_stock: bool = Query(False, description="Show only items below reorder level"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get inventory records with filtering (filtered by user's assigned locations)"""
    query = db.query(Inventory).options(
        joinedload(Inventory.location),
        joinedload(Inventory.storage_area),
        joinedload(Inventory.master_item)
    )

    # Apply user location filtering FIRST
    query = filter_by_user_locations(query, Inventory.location_id, current_user)

    if location_id:
        query = query.filter(Inventory.location_id == location_id)

    if storage_area_id:
        query = query.filter(Inventory.storage_area_id == storage_area_id)

    if category:
        query = query.join(MasterItem).filter(MasterItem.category == category)
    
    if low_stock:
        query = query.filter(
            Inventory.reorder_level.isnot(None),
            Inventory.current_quantity <= Inventory.reorder_level
        )
    
    inventory_records = query.offset(skip).limit(limit).all()
    
    # Format response with related data
    response_data = []
    for record in inventory_records:
        record_data = {
            "id": record.id,
            "location_id": record.location_id,
            "storage_area_id": record.storage_area_id,
            "master_item_id": record.master_item_id,
            "current_quantity": record.current_quantity,
            "unit_cost": record.unit_cost,
            "reorder_level": record.reorder_level,
            "max_level": record.max_level,
            "total_value": record.total_value,
            "last_count_date": record.last_count_date,
            "last_updated": record.last_updated,
            "location_name": record.location.name if record.location else None,
            "storage_area_name": record.storage_area.name if record.storage_area else None,
            "item_name": record.master_item.name if record.master_item else None,
            "item_category": record.master_item.category if record.master_item else None,
            "item_unit": record.master_item.unit_of_measure if record.master_item else None
        }
        response_data.append(InventoryResponse(**record_data))
    
    return response_data

@router.get("/location/{location_id}", response_model=List[InventoryResponse])
async def get_location_inventory(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all inventory for specific location"""
    
    # Verify location exists
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    return await get_inventory_records(
        location_id=location_id, 
        db=db, 
        current_user=current_user
    )

# Transactions endpoint - MUST be before /{inventory_id} to avoid path conflicts
@router.get("/transactions")
async def get_inventory_transactions(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get inventory transactions with filtering"""
    # Query transactions
    query = db.query(InventoryTransaction).options(
        joinedload(InventoryTransaction.master_item),
        joinedload(InventoryTransaction.location)
    )

    query = query.order_by(InventoryTransaction.transaction_date.desc())
    transactions = query.offset(skip).limit(limit).all()

    # Return as plain dicts
    result = []
    for txn in transactions:
        result.append({
            "id": txn.id,
            "master_item_id": txn.master_item_id,
            "master_item_name": txn.master_item.name if txn.master_item else "Unknown",
            "location_id": txn.location_id,
            "location_name": txn.location.name if txn.location else None,
            "transaction_type": txn.transaction_type,
            "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
            "quantity_change": float(txn.quantity_change),
            "unit_of_measure": txn.unit_of_measure,
            "quantity_before": float(txn.quantity_before) if txn.quantity_before else None,
            "quantity_after": float(txn.quantity_after) if txn.quantity_after else None,
            "unit_cost": float(txn.unit_cost) if txn.unit_cost else None,
            "total_cost": float(txn.total_cost) if txn.total_cost else None,
            "pos_sale_id": txn.pos_sale_id,
            "reason": txn.reason,
            "notes": txn.notes
        })

    return result

@router.get("/{inventory_id}", response_model=InventoryResponse)
async def get_inventory_record(
    inventory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific inventory record"""
    record = db.query(Inventory).options(
        joinedload(Inventory.location),
        joinedload(Inventory.master_item)
    ).filter(Inventory.id == inventory_id).first()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found"
        )
    
    return InventoryResponse(
        id=record.id,
        location_id=record.location_id,
        master_item_id=record.master_item_id,
        current_quantity=record.current_quantity,
        unit_cost=record.unit_cost,
        reorder_level=record.reorder_level,
        max_level=record.max_level,
        total_value=record.total_value,
        last_count_date=record.last_count_date,
        last_updated=record.last_updated,
        location_name=record.location.name if record.location else None,
        item_name=record.master_item.name if record.master_item else None,
        item_category=record.master_item.category if record.master_item else None,
        item_unit=record.master_item.unit_of_measure if record.master_item else None
    )

@router.post("/", response_model=InventoryResponse)
async def create_inventory_record(
    inventory_data: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create new inventory record (Manager/Admin only)"""

    # If storage_area_id is provided, infer location_id from it
    # This allows adding items directly to storage areas without specifying location
    location_id = inventory_data.location_id
    if inventory_data.storage_area_id:
        storage_area = db.query(StorageArea).filter(StorageArea.id == inventory_data.storage_area_id).first()
        if not storage_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage area not found"
            )
        # Override location_id with the one from storage area
        location_id = storage_area.location_id
    elif not location_id:
        # If no storage_area_id and no location_id, error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either location_id or storage_area_id must be provided"
        )

    # Verify location exists (if not already verified via storage area)
    if not inventory_data.storage_area_id:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Location not found"
            )

    # Verify master item exists
    master_item = db.query(MasterItem).filter(MasterItem.id == inventory_data.master_item_id).first()
    if not master_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )

    # Check if record already exists for this storage_area/item combination
    # Same item can exist in different storage areas
    existing = db.query(Inventory).filter(
        Inventory.master_item_id == inventory_data.master_item_id,
        Inventory.storage_area_id == inventory_data.storage_area_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inventory record already exists for this storage area/item combination"
        )

    # Create inventory record with inferred location_id
    inventory_dict = inventory_data.dict()
    inventory_dict['location_id'] = location_id
    inventory = Inventory(**inventory_dict)

    # Calculate total value if unit cost is provided
    if inventory.unit_cost and inventory.current_quantity:
        inventory.total_value = inventory.unit_cost * inventory.current_quantity

    # Set last count date
    from datetime import datetime, timezone
    inventory.last_count_date = datetime.now(timezone.utc)

    db.add(inventory)
    db.commit()
    db.refresh(inventory)

    return await get_inventory_record(inventory.id, db, current_user)

@router.put("/{inventory_id}", response_model=InventoryResponse)
async def update_inventory_record(
    inventory_id: int,
    inventory_data: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update inventory record"""
    
    record = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found"
        )
    
    # Update fields
    update_data = inventory_data.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(record, field, value)
    
    # Recalculate total value if quantity or cost changed
    if record.unit_cost and record.current_quantity:
        record.total_value = record.unit_cost * record.current_quantity
    
    # Update last count date if quantity changed
    if "current_quantity" in update_data:
        from datetime import datetime, timezone
        record.last_count_date = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(record)
    
    return await get_inventory_record(inventory_id, db, current_user)

@router.delete("/{inventory_id}")
async def delete_inventory_record(
    inventory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete inventory record (Manager/Admin only)"""
    
    record = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found"
        )
    
    db.delete(record)
    db.commit()
    return {"message": "Inventory record deleted successfully"}

@router.post("/count/{inventory_id}")
async def update_inventory_count(
    inventory_id: int,
    count_data: InventoryCountUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update inventory count (for physical counts)"""

    record = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found"
        )

    old_quantity = float(record.current_quantity)
    new_quantity = Decimal(str(count_data.new_quantity))
    record.current_quantity = new_quantity

    # Recalculate total value
    if record.unit_cost:
        record.total_value = record.unit_cost * new_quantity

    # Update timestamps
    from datetime import datetime, timezone
    record.last_count_date = datetime.now(timezone.utc)

    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="UPDATE",
        entity_type="inventory",
        entity_id=record.id,
        user=current_user,
        changes={
            "old": {"quantity": old_quantity},
            "new": {"quantity": float(new_quantity)},
            "difference": float(new_quantity) - old_quantity
        },
        request=request
    )

    return {
        "message": "Inventory count updated successfully",
        "old_quantity": old_quantity,
        "new_quantity": float(new_quantity),
        "difference": float(new_quantity) - old_quantity
    }


# Inventory Transaction Endpoints

class InventoryTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    master_item_id: int
    master_item_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    transaction_type: str
    transaction_date: datetime
    quantity_change: float
    unit_of_measure: Optional[str] = None
    quantity_before: Optional[float] = None
    quantity_after: Optional[float] = None
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None
    pos_sale_id: Optional[int] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


# Temporarily disabled
# @router.get("/transactions/item/{master_item_id}", response_model=List[InventoryTransactionResponse])
# async def get_item_transaction_history(
#     master_item_id: int,
#     skip: int = 0,
#     limit: int = 100,
#     location_id: Optional[int] = Query(None, description="Filter by location ID"),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     """Get transaction history for a specific item"""
#     return await get_inventory_transactions(
#         skip=skip,
#         limit=limit,
#         location_id=location_id,
#         master_item_id=master_item_id,
#         transaction_type=None,
#         start_date=None,
#         end_date=None,
#         db=db,
#         current_user=current_user
#     )
