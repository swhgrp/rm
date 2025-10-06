"""
Transfer schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal
from restaurant_inventory.models.transfer import TransferStatus

class TransferBase(BaseModel):
    from_location_id: int
    to_location_id: int
    master_item_id: int
    quantity: Decimal
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    reason: Optional[str] = None

class TransferCreate(TransferBase):
    pass

class TransferUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[TransferStatus] = None

class TransferResponse(TransferBase):
    id: int
    status: TransferStatus
    total_value: Optional[Decimal] = None
    requested_by: int
    approved_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Related data
    from_location_name: Optional[str] = None
    to_location_name: Optional[str] = None
    item_name: Optional[str] = None
    requester_name: Optional[str] = None
    approver_name: Optional[str] = None

    class Config:
        from_attributes = True
