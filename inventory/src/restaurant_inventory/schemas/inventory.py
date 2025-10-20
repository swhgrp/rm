"""
Inventory schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

class InventoryBase(BaseModel):
    location_id: Optional[int] = None  # Optional: can be inferred from storage_area_id
    storage_area_id: Optional[int] = None
    master_item_id: int
    current_quantity: Decimal = 0
    unit_cost: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None
    max_level: Optional[Decimal] = None

class InventoryCreate(InventoryBase):
    pass

class InventoryUpdate(BaseModel):
    current_quantity: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None
    max_level: Optional[Decimal] = None

class InventoryResponse(InventoryBase):
    id: int
    total_value: Optional[Decimal] = None
    last_count_date: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    # Related data
    location_name: Optional[str] = None
    storage_area_name: Optional[str] = None
    item_name: Optional[str] = None
    item_category: Optional[str] = None
    item_unit: Optional[str] = None

    class Config:
        from_attributes = True
