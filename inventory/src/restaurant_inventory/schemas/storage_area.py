"""
Storage Area schemas for API validation
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class StorageAreaBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class StorageAreaCreate(StorageAreaBase):
    location_id: int


class StorageAreaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class StorageAreaResponse(StorageAreaBase):
    id: int
    location_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True