"""
Waste Record Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class WasteRecordBase(BaseModel):
    location_id: int
    master_item_id: int
    quantity_wasted: float = Field(gt=0, description="Quantity wasted (must be positive)")
    unit_of_measure: Optional[str] = Field(None, description="Unit of measure for the wasted quantity")
    reason_code: str = Field(description="Reason for waste: spoiled, damaged, expired, theft, overproduction, other")
    description: Optional[str] = None
    waste_date: datetime


class WasteRecordCreate(WasteRecordBase):
    pass


class WasteRecordUpdate(BaseModel):
    quantity_wasted: Optional[float] = Field(None, gt=0)
    unit_of_measure: Optional[str] = None
    reason_code: Optional[str] = None
    description: Optional[str] = None
    waste_date: Optional[datetime] = None


class WasteRecordInDB(WasteRecordBase):
    id: int
    inventory_id: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    recorded_by: int
    recorded_at: datetime

    class Config:
        from_attributes = True


class WasteRecordWithDetails(WasteRecordInDB):
    """Waste record with related entity details"""
    location_name: Optional[str] = None
    item_name: Optional[str] = None
    item_unit: Optional[str] = None
    recorded_by_name: Optional[str] = None


class WasteRecordList(BaseModel):
    """Simplified waste record for list view"""
    id: int
    location_id: int
    location_name: Optional[str] = None
    master_item_id: int
    item_name: Optional[str] = None
    quantity_wasted: float
    unit: Optional[str] = None
    total_cost: Optional[Decimal] = None
    reason_code: str
    waste_date: datetime
    recorded_by_name: Optional[str] = None

    class Config:
        from_attributes = True
