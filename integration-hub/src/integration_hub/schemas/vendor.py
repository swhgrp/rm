"""
Pydantic schemas for Vendor operations
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class VendorBase(BaseModel):
    """Base vendor schema"""
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    payment_terms: Optional[str] = None
    tax_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class VendorCreate(VendorBase):
    """Schema for creating a new vendor"""
    push_to_inventory: bool = True
    push_to_accounting: bool = True


class VendorUpdate(BaseModel):
    """Schema for updating a vendor"""
    name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    payment_terms: Optional[str] = None
    tax_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    send_to_inventory: Optional[bool] = None
    send_to_accounting: Optional[bool] = None


class VendorResponse(VendorBase):
    """Schema for vendor response"""
    id: int
    send_to_inventory: bool = True
    send_to_accounting: bool = True
    inventory_vendor_id: Optional[int] = None
    accounting_vendor_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VendorSyncStatus(BaseModel):
    """Schema for vendor sync status"""
    hub_vendor_id: int
    inventory_synced: bool
    inventory_vendor_id: Optional[int] = None
    accounting_synced: bool
    accounting_vendor_id: Optional[int] = None
    errors: list[str] = []
