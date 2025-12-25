"""
Pydantic schemas for Vendor Items
"""

from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from datetime import datetime


class VendorItemBase(BaseModel):
    vendor_id: int
    master_item_id: Optional[int] = None  # Nullable - vendor items can be imported without master item link
    vendor_sku: Optional[str] = None
    vendor_product_name: str
    vendor_description: Optional[str] = None
    purchase_unit_id: int
    pack_size: Optional[str] = None
    conversion_factor: Decimal = Field(..., description="How many master item units = 1 purchase unit")
    conversion_unit_id: Optional[int] = None
    unit_price: Optional[Decimal] = None
    minimum_order_quantity: Optional[Decimal] = None
    lead_time_days: Optional[int] = None
    notes: Optional[str] = None
    is_active: bool = True
    is_preferred: bool = False


class VendorItemCreate(VendorItemBase):
    pass


class VendorItemUpdate(BaseModel):
    vendor_id: Optional[int] = None
    master_item_id: Optional[int] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: Optional[str] = None
    vendor_description: Optional[str] = None
    purchase_unit_id: Optional[int] = None
    pack_size: Optional[str] = None
    conversion_factor: Optional[Decimal] = None
    conversion_unit_id: Optional[int] = None
    unit_price: Optional[Decimal] = None
    minimum_order_quantity: Optional[Decimal] = None
    lead_time_days: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_preferred: Optional[bool] = None


class VendorItemResponse(VendorItemBase):
    id: int
    last_price: Optional[Decimal] = None
    price_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Populated from joins
    vendor_name: Optional[str] = None
    master_item_name: Optional[str] = None
    purchase_unit_name: Optional[str] = None
    purchase_unit_abbr: Optional[str] = None
    conversion_unit_name: Optional[str] = None

    class Config:
        from_attributes = True


class VendorItemWithDetails(VendorItemResponse):
    """Extended response with full master item and vendor details"""
    master_item_category: Optional[str] = None
    master_item_unit_name: Optional[str] = None
    cost_per_master_unit: Optional[Decimal] = None  # Calculated: unit_price / conversion_factor

    class Config:
        from_attributes = True
