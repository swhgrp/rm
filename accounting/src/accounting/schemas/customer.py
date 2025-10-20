"""
Customer schemas for API
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal


class CustomerBase(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=200, description="Customer name")
    customer_code: Optional[str] = Field(None, max_length=50, description="Short code/abbreviation")
    customer_type: Optional[str] = Field(None, max_length=50, description="Catering, Events, Corporate, etc.")

    # Contact information
    contact_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    mobile: Optional[str] = Field(None, max_length=20)
    fax: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=200)

    # Address information
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100, description="Default: United States")

    # Billing information
    billing_email: Optional[str] = Field(None, max_length=100)
    billing_contact: Optional[str] = Field(None, max_length=200)

    # Tax information
    tax_exempt: bool = Field(False, description="Is customer tax exempt")
    tax_exempt_id: Optional[str] = Field(None, max_length=50, description="Tax exemption certificate #")
    tax_rate: Optional[Decimal] = Field(None, description="Override tax rate")

    # Payment terms
    payment_terms: Optional[str] = Field(None, max_length=50, description="e.g., 'Net 30', 'Net 15'")
    credit_limit: Optional[Decimal] = Field(None, description="Credit limit in dollars")

    # Pricing
    discount_percentage: Optional[Decimal] = Field(None, description="Default discount %")

    # Notes
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = Field(None, min_length=1, max_length=200)
    customer_code: Optional[str] = Field(None, max_length=50)
    customer_type: Optional[str] = Field(None, max_length=50)
    contact_name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    mobile: Optional[str] = Field(None, max_length=20)
    fax: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=200)
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    billing_email: Optional[str] = Field(None, max_length=100)
    billing_contact: Optional[str] = Field(None, max_length=200)
    tax_exempt: Optional[bool] = None
    tax_exempt_id: Optional[str] = Field(None, max_length=50)
    tax_rate: Optional[Decimal] = None
    payment_terms: Optional[str] = Field(None, max_length=50)
    credit_limit: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
