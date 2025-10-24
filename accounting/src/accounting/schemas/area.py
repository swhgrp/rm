"""
Area schemas for location/department management
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class AreaBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="DBA/Operating name")
    code: str = Field(..., min_length=1, max_length=20, description="Short identifier code")
    description: Optional[str] = None

    # Legal entity information
    legal_name: Optional[str] = Field(None, max_length=200, description="Legal business name")
    ein: Optional[str] = Field(None, max_length=20, description="Employer Identification Number")
    entity_type: Optional[str] = Field(None, max_length=50, description="LLC, Corporation, etc.")

    # Address information
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100, description="Default: United States")

    # Contact information
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)

    # GL Account Configuration
    safe_account_id: Optional[int] = Field(None, description="GL account for safe transactions")


class AreaCreate(AreaBase):
    pass


class AreaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = None
    is_active: Optional[bool] = None

    # Legal entity information
    legal_name: Optional[str] = Field(None, max_length=200)
    ein: Optional[str] = Field(None, max_length=20)
    entity_type: Optional[str] = Field(None, max_length=50)

    # Address information
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)

    # Contact information
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=200)

    # GL Account Configuration
    safe_account_id: Optional[int] = None


class AreaResponse(AreaBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
