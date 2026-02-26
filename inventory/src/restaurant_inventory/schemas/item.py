"""
Master Item schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from decimal import Decimal


class CountUnitSchema(BaseModel):
    """Schema for count unit data from master_item_count_units table"""
    id: int
    uom_id: int
    uom_name: Optional[str] = None
    uom_abbreviation: Optional[str] = None
    is_primary: bool = False
    conversion_to_primary: float = 1.0
    display_order: int = 0

class MasterItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    # Primary UoM from Hub (source of truth)
    primary_uom_id: Optional[int] = None      # Hub UoM ID
    primary_uom_name: Optional[str] = None    # Cached name for display
    primary_uom_abbr: Optional[str] = None    # Cached abbreviation
    # Legacy - DEPRECATED: Use primary_uom_id instead
    unit_of_measure_id: Optional[int] = None  # Old Inventory UoM ID
    secondary_unit_id: Optional[int] = None
    # Additional count units (Hub UoM IDs)
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
    # Primary UoM from Hub (source of truth)
    primary_uom_id: Optional[int] = None      # Hub UoM ID
    primary_uom_name: Optional[str] = None    # Cached name (auto-fetched from Hub)
    primary_uom_abbr: Optional[str] = None    # Cached abbreviation (auto-fetched)
    # Legacy - DEPRECATED: Use primary_uom_id instead
    unit_of_measure_id: Optional[int] = None  # Old Inventory UoM ID
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
    count_unit_1_id: Optional[int] = None
    count_unit_1_name: Optional[str] = None
    count_unit_1_factor: Optional[float] = None
    count_unit_2_id: Optional[int] = None
    count_unit_2_name: Optional[str] = None
    count_unit_2_factor: Optional[float] = None
    count_unit_3_id: Optional[int] = None
    count_unit_3_name: Optional[str] = None
    count_unit_3_factor: Optional[float] = None
    # Last price paid from vendor items
    last_price_paid: Optional[float] = None
    last_price_unit: Optional[str] = None
    # Primary count unit from master_item_count_units (Hub UoM architecture)
    primary_count_unit_id: Optional[int] = None
    primary_count_unit_name: Optional[str] = None
    primary_count_unit_abbr: Optional[str] = None
    # All count units for advanced UI (populated manually, excluded from ORM)
    count_units: Optional[List[Any]] = None

    model_config = {
        "from_attributes": True,
        # Exclude count_units from ORM conversion since it's a relationship
        # that needs manual serialization
    }

    @classmethod
    def from_orm(cls, obj):
        """Override to handle count_units manually"""
        # Get all fields except count_units
        data = {}
        for field_name in cls.model_fields:
            if field_name == 'count_units':
                data['count_units'] = None  # Will be populated manually if needed
            else:
                try:
                    data[field_name] = getattr(obj, field_name, None)
                except Exception:
                    data[field_name] = None
        return cls(**data)
