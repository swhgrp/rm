"""
Pydantic schemas for Position model
"""

from pydantic import BaseModel
from decimal import Decimal
from typing import Optional


class PositionBase(BaseModel):
    """Base Position schema with common fields"""
    title: str
    department_id: Optional[int] = None
    department: Optional[str] = None
    description: Optional[str] = None
    hourly_rate_min: Optional[Decimal] = None
    hourly_rate_max: Optional[Decimal] = None
    is_active: bool = True


class PositionCreate(PositionBase):
    """Schema for creating a new position"""
    pass


class PositionUpdate(BaseModel):
    """Schema for updating a position (all fields optional)"""
    title: Optional[str] = None
    department_id: Optional[int] = None
    department: Optional[str] = None
    description: Optional[str] = None
    hourly_rate_min: Optional[Decimal] = None
    hourly_rate_max: Optional[Decimal] = None
    is_active: Optional[bool] = None


class Position(PositionBase):
    """Schema for returning position data (includes ID)"""
    id: int

    class Config:
        from_attributes = True
