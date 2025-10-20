"""
Count Session schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class CountSessionItemBase(BaseModel):
    master_item_id: int
    expected_quantity: Optional[Decimal] = None
    counted_quantity: Optional[Decimal] = None
    notes: Optional[str] = None

class CountSessionItemCreate(CountSessionItemBase):
    pass

class CountSessionItemUpdate(BaseModel):
    counted_quantity: Optional[Decimal] = None
    notes: Optional[str] = None

class CountSessionItemResponse(CountSessionItemBase):
    id: int
    session_id: int
    storage_area_id: Optional[int] = None
    inventory_id: Optional[int] = None
    variance: Optional[Decimal] = None
    variance_percent: Optional[Decimal] = None
    flagged: bool = False
    is_new_item: bool = False
    counted_at: Optional[datetime] = None
    counted_by: Optional[int] = None
    counted_by_name: Optional[str] = None
    storage_area_name: Optional[str] = None
    item_name: Optional[str] = None
    item_category: Optional[str] = None
    item_unit: Optional[str] = None
    item_barcode: Optional[str] = None

    class Config:
        from_attributes = True

class CountSessionBase(BaseModel):
    location_id: int
    storage_area_id: Optional[int] = None  # Legacy, not used
    template_id: Optional[int] = None
    name: Optional[str] = None
    inventory_type: str = "PARTIAL"  # FULL or PARTIAL
    notes: Optional[str] = None

class CountSessionCreate(CountSessionBase):
    pass

class CountSessionUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # IN_PROGRESS, COMPLETED, APPROVED, CANCELLED

class CountSessionResponse(CountSessionBase):
    id: int
    status: str
    inventory_type: str
    locked: bool = False
    started_by: Optional[int] = None
    started_at: datetime
    completed_by: Optional[int] = None
    completed_at: Optional[datetime] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

    # Related data
    storage_area_name: Optional[str] = None
    location_name: Optional[str] = None
    template_name: Optional[str] = None
    started_by_name: Optional[str] = None
    completed_by_name: Optional[str] = None
    approved_by_name: Optional[str] = None

    # Summary stats
    total_items: int = 0
    counted_items: int = 0
    flagged_items: int = 0
    new_items: int = 0

    items: List[CountSessionItemResponse] = []

    class Config:
        from_attributes = True