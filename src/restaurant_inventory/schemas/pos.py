"""
POS Integration schemas
"""

from pydantic import BaseModel
from typing import Optional, List
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


class POSSyncResponse(BaseModel):
    """Response from sales sync operation"""
    success: bool
    message: str
    orders_synced: int = 0
    orders_skipped: int = 0
    errors: Optional[list] = None


class POSSaleItemResponse(BaseModel):
    """POS sale line item response"""
    id: int
    pos_item_id: Optional[str] = None
    item_name: str
    category: Optional[str] = None
    recipe_id: Optional[int] = None
    quantity: float
    unit_price: float
    total_price: float
    modifiers: Optional[str] = None
    notes: Optional[str] = None
    recipe_cost: Optional[float] = None
    profit_margin: Optional[float] = None

    class Config:
        from_attributes = True


class POSSaleResponse(BaseModel):
    """POS sale response"""
    id: int
    pos_provider: str
    pos_order_id: str
    order_number: Optional[str] = None
    order_date: datetime
    subtotal: float
    tax: float
    tip: float
    discount: float
    total: float
    customer_name: Optional[str] = None
    order_type: Optional[str] = None
    table_number: Optional[str] = None
    status: str
    inventory_deducted: bool
    location_id: Optional[int] = None
    line_items: List[POSSaleItemResponse] = []
    created_at: datetime
    synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class POSItemMappingBase(BaseModel):
    """Base schema for POS item mapping"""
    pos_provider: str
    pos_item_id: str
    pos_item_name: str
    recipe_id: Optional[int] = None
    master_item_id: Optional[int] = None
    portion_multiplier: float = 1.0
    location_id: Optional[int] = None
    is_active: bool = True


class POSItemMappingCreate(POSItemMappingBase):
    """Create POS item mapping"""
    pass


class POSItemMappingUpdate(BaseModel):
    """Update POS item mapping"""
    recipe_id: Optional[int] = None
    master_item_id: Optional[int] = None
    portion_multiplier: Optional[float] = None
    is_active: Optional[bool] = None


class POSItemMappingResponse(POSItemMappingBase):
    """POS item mapping response"""
    id: int
    recipe_name: Optional[str] = None
    master_item_name: Optional[str] = None
    times_sold: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UnmappedPOSItem(BaseModel):
    """Unmapped POS item that needs mapping"""
    pos_item_id: str
    item_name: str
    category: Optional[str] = None
    times_sold: int
    total_quantity: float
    total_revenue: float
    first_sold: datetime
    last_sold: datetime

