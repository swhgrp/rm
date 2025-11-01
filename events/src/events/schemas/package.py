"""Event Package schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class PriceComponents(BaseModel):
    """Price components for a package"""
    base_price: float = Field(..., description="Base price for the package")
    per_guest_price: float = Field(0, description="Price per guest")
    setup_fee: Optional[float] = Field(None, description="Setup/breakdown fee")
    overtime_rate: Optional[float] = Field(None, description="Hourly overtime rate")
    tax_rate: Optional[float] = Field(None, description="Tax rate (as decimal, e.g., 0.08 for 8%)")
    gratuity_rate: Optional[float] = Field(None, description="Gratuity rate (as decimal)")
    description: Optional[str] = Field(None, description="Pricing description")


class EventPackageBase(BaseModel):
    """Base event package schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Package name")
    event_type: str = Field(..., description="Event type this package is for")
    price_components: Optional[PriceComponents] = Field(None, description="Pricing breakdown")


class EventPackageCreate(EventPackageBase):
    """Schema for creating an event package"""
    pass


class EventPackageUpdate(BaseModel):
    """Schema for updating an event package"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    event_type: Optional[str] = None
    price_components: Optional[PriceComponents] = None


class EventPackageResponse(EventPackageBase):
    """Schema for event package response"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventPackageListItem(BaseModel):
    """Simplified event package for list views"""
    id: UUID
    name: str
    event_type: str
    base_price: Optional[float] = None
    per_guest_price: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
