"""
Count Template schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class CountTemplateItemBase(BaseModel):
    master_item_id: int
    sort_order: int = 0

class CountTemplateItemCreate(CountTemplateItemBase):
    pass

class CountTemplateItemResponse(CountTemplateItemBase):
    id: int
    template_id: int
    item_name: Optional[str] = None
    item_category: Optional[str] = None
    item_unit: Optional[str] = None

    class Config:
        from_attributes = True

class CountTemplateBase(BaseModel):
    storage_area_id: int
    name: str
    description: Optional[str] = None

class CountTemplateCreate(CountTemplateBase):
    item_ids: List[int] = []  # List of master_item_id to include

class CountTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    item_ids: Optional[List[int]] = None

class CountTemplateResponse(CountTemplateBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    storage_area_name: Optional[str] = None
    location_name: Optional[str] = None
    created_by_name: Optional[str] = None
    item_count: int = 0
    items: List[CountTemplateItemResponse] = []

    class Config:
        from_attributes = True