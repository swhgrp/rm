"""
Master Item schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

class MasterItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    unit_of_measure_id: Optional[int] = None
    secondary_unit_id: Optional[int] = None
    # Additional count units
    count_unit_2_id: Optional[int] = None
    count_unit_3_id: Optional[int] = None
    # Legacy fields for backward compatibility
    unit_of_measure: Optional[str] = None
    secondary_unit: Optional[str] = None
    units_per_secondary: Optional[Decimal] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    barcode_type: Optional[str] = None
    vendor: Optional[str] = None
    par_level: Optional[Decimal] = None
    is_active: bool = True
    is_key_item: bool = False

class MasterItemCreate(MasterItemBase):
    current_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None

class MasterItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit_of_measure_id: Optional[int] = None
    secondary_unit_id: Optional[int] = None
    # Additional count units
    count_unit_2_id: Optional[int] = None
    count_unit_3_id: Optional[int] = None
    # Legacy fields
    unit_of_measure: Optional[str] = None
    secondary_unit: Optional[str] = None
    units_per_secondary: Optional[Decimal] = None
    current_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    barcode_type: Optional[str] = None
    vendor: Optional[str] = None
    par_level: Optional[Decimal] = None
    is_active: Optional[bool] = None
    is_key_item: Optional[bool] = None

class MasterItemResponse(MasterItemBase):
    id: int
    current_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None
    last_cost_update: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Include unit names for display
    unit_name: Optional[str] = None
    secondary_unit_name: Optional[str] = None
    count_unit_2_name: Optional[str] = None
    count_unit_3_name: Optional[str] = None
    # Last price paid from vendor items
    last_price_paid: Optional[float] = None
    last_price_unit: Optional[str] = None

    class Config:
        from_attributes = True
