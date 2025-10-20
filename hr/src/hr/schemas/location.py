"""
Schemas for location management
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class LocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    phone: Optional[str] = None
    manager_name: Optional[str] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    phone: Optional[str] = None
    manager_name: Optional[str] = None
    is_active: Optional[bool] = None


class LocationResponse(LocationBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserLocationAssignment(BaseModel):
    """Schema for assigning locations to a user"""
    location_ids: list[int] = Field(..., description="List of location IDs to assign. Empty list = access to all locations")


class UserLocationResponse(BaseModel):
    """Schema for user location assignment response"""
    user_id: int
    username: str
    assigned_locations: list[LocationResponse]
    has_restrictions: bool  # True if specific locations assigned, False if access to all

    class Config:
        from_attributes = True
