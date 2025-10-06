"""
POS Integration schemas
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class POSConfigurationBase(BaseModel):
    provider: str = "clover"
    merchant_id: Optional[str] = None
    api_key: Optional[str] = None
    access_token: Optional[str] = None
    api_environment: str = "production"
    auto_sync_enabled: bool = False
    sync_frequency_minutes: int = 60
    auto_deduct_inventory: bool = False
    is_active: bool = True


class POSConfigurationCreate(POSConfigurationBase):
    location_id: int


class POSConfigurationUpdate(BaseModel):
    provider: Optional[str] = None
    merchant_id: Optional[str] = None
    api_key: Optional[str] = None
    access_token: Optional[str] = None
    api_environment: Optional[str] = None
    auto_sync_enabled: Optional[bool] = None
    sync_frequency_minutes: Optional[int] = None
    auto_deduct_inventory: Optional[bool] = None
    is_active: Optional[bool] = None


class POSConfigurationResponse(POSConfigurationBase):
    id: int
    location_id: int
    last_sync_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Mask sensitive fields in response
    api_key: Optional[str] = None
    access_token: Optional[str] = None

    class Config:
        from_attributes = True


class POSConnectionTest(BaseModel):
    """Response from connection test"""
    success: bool
    message: str
    merchant_id: Optional[str] = None
    merchant_name: Optional[str] = None


class POSSyncRequest(BaseModel):
    """Request to sync sales from POS"""
    start_date: Optional[str] = None  # ISO date string
    end_date: Optional[str] = None
    limit: int = 100
