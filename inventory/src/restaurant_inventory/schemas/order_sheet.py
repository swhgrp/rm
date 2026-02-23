"""
Order Sheet schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class OrderSheetItemResponse(BaseModel):
    id: int
    order_sheet_id: int
    hub_vendor_item_id: int
    par_level: Optional[int] = None
    on_hand: Optional[int] = None
    to_order: Optional[int] = None
    unit_abbr: Optional[str] = None
    notes: Optional[str] = None
    item_name: Optional[str] = None
    vendor_sku: Optional[str] = None
    vendor_name: Optional[str] = None
    item_category: Optional[str] = None

    class Config:
        from_attributes = True


class OrderSheetItemUpdate(BaseModel):
    id: int
    on_hand: Optional[int] = None
    to_order: Optional[int] = None
    notes: Optional[str] = None


class OrderSheetCreate(BaseModel):
    template_id: int
    name: Optional[str] = None
    notes: Optional[str] = None


class OrderSheetUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    items: Optional[List[OrderSheetItemUpdate]] = None


class OrderSheetSendRequest(BaseModel):
    emails: List[str]


class OrderSheetResponse(BaseModel):
    id: int
    template_id: int
    location_id: int
    name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_by: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    sent_to_emails: Optional[str] = None
    sent_at: Optional[datetime] = None
    template_name: Optional[str] = None
    location_name: Optional[str] = None
    created_by_name: Optional[str] = None
    total_items: int = 0
    items_entered: int = 0
    total_to_order: int = 0
    items: List[OrderSheetItemResponse] = []

    class Config:
        from_attributes = True
