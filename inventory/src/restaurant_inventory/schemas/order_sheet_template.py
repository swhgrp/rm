"""
Order Sheet Template schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class OrderSheetTemplateItemCreate(BaseModel):
    hub_vendor_item_id: int
    par_level: int = 0
    sort_order: int = 0
    # Snapshot fields (populated by frontend from hub vendor item data)
    item_name: Optional[str] = None
    vendor_sku: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    unit_abbr: Optional[str] = None


class OrderSheetTemplateItemResponse(BaseModel):
    id: int
    template_id: int
    hub_vendor_item_id: int
    par_level: int
    sort_order: int
    item_name: Optional[str] = None
    vendor_sku: Optional[str] = None
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    unit_abbr: Optional[str] = None

    class Config:
        from_attributes = True


class OrderSheetTemplateCreate(BaseModel):
    location_id: int
    name: str
    description: Optional[str] = None
    is_active: bool = True
    items: List[OrderSheetTemplateItemCreate] = []


class OrderSheetTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    items: Optional[List[OrderSheetTemplateItemCreate]] = None


class OrderSheetTemplateResponse(BaseModel):
    id: int
    location_id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    location_name: Optional[str] = None
    created_by_name: Optional[str] = None
    item_count: int = 0
    items: List[OrderSheetTemplateItemResponse] = []

    class Config:
        from_attributes = True
