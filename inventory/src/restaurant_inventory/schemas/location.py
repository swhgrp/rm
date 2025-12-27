"""
Location schemas for request/response models

Inventory is the source of truth for locations.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LocationBase(BaseModel):
    """Base location fields"""
    code: Optional[str] = None  # Short code like "400", "500"
    name: str  # DBA name like "Seaside Grill"
    legal_name: Optional[str] = None  # Legal business name
    ein: Optional[str] = None  # Employer Identification Number
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    manager_name: Optional[str] = None
    is_active: bool = True


class LocationCreate(LocationBase):
    """Create location request"""
    code: str  # Required for new locations


class LocationUpdate(BaseModel):
    """Update location request - all fields optional"""
    code: Optional[str] = None
    name: Optional[str] = None
    legal_name: Optional[str] = None
    ein: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None
    manager_name: Optional[str] = None
    is_active: Optional[bool] = None


class LocationResponse(LocationBase):
    """Location response with all fields"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
