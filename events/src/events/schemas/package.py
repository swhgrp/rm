"""Event Package schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class PricingType(str, Enum):
    """Pricing type for packages"""
    FLAT_RATE = "flat_rate"      # Fixed price (e.g., carving station $570)
    PER_PERSON = "per_person"    # Per guest (e.g., buffet $18/person)
    PER_PIECE = "per_piece"      # Per item (e.g., hors d'oeuvres $4/piece)
    HOURLY = "hourly"            # Per hour (e.g., bartender $45/hour)


class ServiceRequirement(BaseModel):
    """Service staff requirement for a package"""
    role: str = Field(..., description="Role name (e.g., Bartender, Attendant)")
    hourly_rate: float = Field(..., description="Hourly rate for the service")
    min_hours: Optional[int] = Field(None, description="Minimum hours required")
    description: Optional[str] = Field(None, description="Description of service")


class PackageAddon(BaseModel):
    """Optional add-on for a package"""
    name: str = Field(..., description="Add-on name (e.g., Add Shrimp, Premium Spirits)")
    price: float = Field(..., description="Price for the add-on")
    pricing_type: PricingType = Field(PricingType.PER_PERSON, description="How add-on is priced")
    description: Optional[str] = Field(None, description="Description of add-on")


class PriceComponents(BaseModel):
    """Price components for a package"""
    # Primary pricing
    pricing_type: PricingType = Field(PricingType.FLAT_RATE, description="Primary pricing method")
    base_price: Optional[float] = Field(None, description="Base/flat price (optional for per-person only packages)")
    per_unit_price: Optional[float] = Field(None, description="Price per person/piece/hour depending on pricing_type")

    # Portion info (for catering)
    portion_size: Optional[str] = Field(None, description="Portion size (e.g., 5oz, 3-4oz)")
    serves_count: Optional[int] = Field(None, description="Number of guests served (for flat rate items)")

    # Service requirements
    service_requirements: Optional[List[ServiceRequirement]] = Field(None, description="Required service staff")

    # Add-ons/Upgrades
    addons: Optional[List[PackageAddon]] = Field(None, description="Optional add-ons")

    # Legacy/additional fees
    setup_fee: Optional[float] = Field(None, description="Setup/breakdown fee")
    overtime_rate: Optional[float] = Field(None, description="Hourly overtime rate")

    # Tax and gratuity
    tax_rate: Optional[float] = Field(None, description="Tax rate (as decimal, e.g., 0.07 for 7%)")
    gratuity_rate: Optional[float] = Field(None, description="Service charge rate (as decimal, e.g., 0.21 for 21%)")

    # Description
    description: Optional[str] = Field(None, description="Pricing description/what's included")


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
    pricing_type: Optional[str] = None
    base_price: Optional[float] = None
    per_unit_price: Optional[float] = None
    portion_size: Optional[str] = None
    serves_count: Optional[int] = None
    has_addons: bool = False
    has_service_requirements: bool = False
    created_at: datetime

    class Config:
        from_attributes = True
