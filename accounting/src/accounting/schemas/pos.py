"""
POS Integration Pydantic Schemas
Request/response models for POS API endpoints
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from decimal import Decimal


# ==================== POS Configuration Schemas ====================

class POSConfigurationBase(BaseModel):
    """Base schema for POS configuration"""
    provider: str = Field(default="clover", description="POS provider: clover, square, toast")
    merchant_id: Optional[str] = Field(None, description="POS merchant/location ID")
    access_token: Optional[str] = Field(None, description="API access token")
    api_environment: str = Field(default="production", description="API environment: sandbox or production")
    auto_sync_enabled: bool = Field(default=False, description="Enable automatic daily sync")
    sync_time: str = Field(default="02:00", description="Daily sync time in HH:MM format (24-hour)")
    is_active: bool = Field(default=True, description="Configuration is active")


class POSConfigurationCreate(POSConfigurationBase):
    """Schema for creating POS configuration"""
    area_id: int = Field(..., description="Location/area ID")


class POSConfigurationUpdate(BaseModel):
    """Schema for updating POS configuration"""
    merchant_id: Optional[str] = None
    access_token: Optional[str] = None
    api_environment: Optional[str] = None
    auto_sync_enabled: Optional[bool] = None
    sync_time: Optional[str] = None
    is_active: Optional[bool] = None


class POSConfigurationResponse(POSConfigurationBase):
    """Schema for POS configuration response"""
    id: int
    area_id: int
    last_sync_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== POS Daily Sales Cache Schemas ====================

class POSDailySalesCacheResponse(BaseModel):
    """Schema for daily sales cache response"""
    id: int
    area_id: int
    sale_date: date
    provider: str
    total_sales: Decimal
    total_tax: Decimal
    total_tips: Decimal
    total_discounts: Decimal
    gross_sales: Decimal
    transaction_count: int
    order_types: Optional[Dict[str, Any]] = None
    payment_methods: Optional[Dict[str, Any]] = None
    categories: Optional[Dict[str, Any]] = None  # Changed from List to Dict to match storage format
    synced_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== POS Category GL Mapping Schemas ====================

class POSCategoryGLMappingBase(BaseModel):
    """Base schema for category GL mapping"""
    pos_category: str = Field(..., description="POS category name (e.g., Food, Beverages, Alcohol)")
    revenue_account_id: int = Field(..., description="GL revenue account ID")
    tax_account_id: Optional[int] = Field(None, description="GL sales tax payable account ID")
    discount_account_id: Optional[int] = Field(None, description="GL contra-revenue account for discounts on this category")
    is_active: bool = Field(default=True)


class POSCategoryGLMappingCreate(POSCategoryGLMappingBase):
    """Schema for creating category mapping"""
    area_id: Optional[int] = Field(None, description="Location ID (null for global mapping)")


class POSCategoryGLMappingUpdate(BaseModel):
    """Schema for updating category mapping"""
    revenue_account_id: Optional[int] = None
    tax_account_id: Optional[int] = None
    discount_account_id: Optional[int] = None
    is_active: Optional[bool] = None


class POSCategoryGLMappingResponse(POSCategoryGLMappingBase):
    """Schema for category mapping response"""
    id: int
    area_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== POS Discount Mapping Schemas ====================

class POSDiscountGLMappingBase(BaseModel):
    """Base schema for discount GL mapping"""
    pos_discount_name: str = Field(..., description="POS discount name (e.g., Employee Discount, Happy Hour)")
    discount_account_id: int = Field(..., description="GL account ID for discount (contra-revenue or expense)")
    is_override: bool = Field(default=False, description="True = always use this account regardless of item category")
    is_active: bool = Field(default=True)


class POSDiscountGLMappingCreate(POSDiscountGLMappingBase):
    """Schema for creating discount mapping"""
    area_id: int = Field(..., description="Location ID")


class POSDiscountGLMappingUpdate(BaseModel):
    """Schema for updating discount mapping"""
    pos_discount_name: Optional[str] = None
    discount_account_id: Optional[int] = None
    is_override: Optional[bool] = None
    is_active: Optional[bool] = None


class POSDiscountGLMappingResponse(POSDiscountGLMappingBase):
    """Schema for discount mapping response"""
    id: int
    area_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== POS Payment Mapping Schemas ====================

class POSPaymentGLMappingBase(BaseModel):
    """Base schema for payment type GL mapping"""
    pos_payment_type: str = Field(..., description="POS payment type (e.g., CASH, CREDIT_CARD, GIFT_CARD)")
    deposit_account_id: int = Field(..., description="GL deposit account ID (asset account)")
    is_active: bool = Field(default=True)


class POSPaymentGLMappingCreate(POSPaymentGLMappingBase):
    """Schema for creating payment mapping"""
    area_id: int = Field(..., description="Location ID")


class POSPaymentGLMappingUpdate(BaseModel):
    """Schema for updating payment mapping"""
    pos_payment_type: Optional[str] = None
    deposit_account_id: Optional[int] = None
    is_active: Optional[bool] = None


class POSPaymentGLMappingResponse(POSPaymentGLMappingBase):
    """Schema for payment mapping response"""
    id: int
    area_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== POS Sync Schemas ====================

class POSSyncRequest(BaseModel):
    """Schema for POS sync request"""
    start_date: Optional[date] = Field(None, description="Start date (default: today)")
    end_date: Optional[date] = Field(None, description="End date (default: today)")


class POSSyncResponse(BaseModel):
    """Schema for POS sync response"""
    synced_count: int = Field(..., description="Number of days synced")
    updated_count: int = Field(..., description="Number of days updated")
    error_count: int = Field(..., description="Number of errors")
    errors: List[Dict[str, str]] = Field(default_factory=list)
    date_range: Dict[str, str]


class POSConnectionTestResponse(BaseModel):
    """Schema for connection test response"""
    success: bool
    message: str
    provider: str
    merchant_id: str


# ==================== Daily Sales Import Schemas ====================

class DailySalesImportFromPOSRequest(BaseModel):
    """Schema for importing daily sales from POS cache"""
    area_id: int = Field(..., description="Location ID")
    sale_date: date = Field(..., description="Date to import")
    auto_create_journal_entry: bool = Field(default=True, description="Automatically create journal entry")
    override_existing: bool = Field(default=False, description="Override existing daily sales if present")


class DailySalesImportFromPOSResponse(BaseModel):
    """Schema for daily sales import response"""
    success: bool
    message: str
    daily_sales_id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    total_sales: Decimal
    total_tax: Decimal
    categories_imported: int
