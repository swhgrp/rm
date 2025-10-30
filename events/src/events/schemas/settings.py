"""Settings schemas"""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class LocationBase(BaseModel):
    """Base location schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    sort_order: int = 0


class LocationCreate(LocationBase):
    """Create location schema"""
    pass


class LocationUpdate(BaseModel):
    """Update location schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class LocationResponse(LocationBase):
    """Location response schema"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventTypeBase(BaseModel):
    """Base event type schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    sort_order: int = 0


class EventTypeCreate(EventTypeBase):
    """Create event type schema"""
    pass


class EventTypeUpdate(BaseModel):
    """Update event type schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class EventTypeResponse(EventTypeBase):
    """Event type response schema"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BeverageServiceBase(BaseModel):
    """Base beverage service schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    sort_order: int = 0


class BeverageServiceCreate(BeverageServiceBase):
    """Create beverage service schema"""
    pass


class BeverageServiceUpdate(BaseModel):
    """Update beverage service schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class BeverageServiceResponse(BeverageServiceBase):
    """Beverage service response schema"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MealTypeBase(BaseModel):
    """Base meal type schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True
    sort_order: int = 0


class MealTypeCreate(MealTypeBase):
    """Create meal type schema"""
    pass


class MealTypeUpdate(BaseModel):
    """Update meal type schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class MealTypeResponse(MealTypeBase):
    """Meal type response schema"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
