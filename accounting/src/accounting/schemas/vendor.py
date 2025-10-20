"""
Vendor schemas for API
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class VendorBase(BaseModel):
    vendor_name: str = Field(..., min_length=1, max_length=200, description="Vendor/Supplier name")
    vendor_code: Optional[str] = Field(None, max_length=50, description="Short code/abbreviation")

    # Contact information
    contact_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    fax: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=200)

    # Address information
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100, description="Default: United States")

    # Tax information
    tax_id: Optional[str] = Field(None, max_length=50, description="EIN/SSN for 1099 reporting")
    is_1099_vendor: bool = Field(False, description="Subject to 1099 reporting")

    # Payment terms
    payment_terms: Optional[str] = Field(None, max_length=50, description="e.g., 'Net 30', 'Net 15'")
    credit_limit: Optional[int] = Field(None, description="Credit limit in dollars")

    # Account information
    account_number: Optional[str] = Field(None, max_length=100, description="Our account # with vendor")

    # Notes
    notes: Optional[str] = None


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    vendor_name: Optional[str] = Field(None, min_length=1, max_length=200)
    vendor_code: Optional[str] = Field(None, max_length=50)
    contact_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    fax: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=200)
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    tax_id: Optional[str] = Field(None, max_length=50)
    is_1099_vendor: Optional[bool] = None
    payment_terms: Optional[str] = Field(None, max_length=50)
    credit_limit: Optional[int] = None
    account_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VendorResponse(VendorBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
