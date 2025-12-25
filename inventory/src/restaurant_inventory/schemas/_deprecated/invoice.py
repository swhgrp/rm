"""
Invoice Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from restaurant_inventory.models.invoice import InvoiceStatus


# InvoiceItem schemas
class InvoiceItemBase(BaseModel):
    line_number: Optional[int] = None
    description: str
    vendor_sku: Optional[str] = None
    quantity: float
    unit: Optional[str] = None
    pack_size: Optional[str] = None  # e.g., "Case - 6", "Case - 24", "Each"
    unit_price: float
    line_total: float


class InvoiceItemCreate(InvoiceItemBase):
    master_item_id: Optional[int] = None
    mapping_confidence: Optional[float] = None
    mapping_method: Optional[str] = None


class InvoiceItemUpdate(BaseModel):
    description: Optional[str] = None
    vendor_sku: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    pack_size: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None
    vendor_item_id: Optional[int] = None
    master_item_id: Optional[int] = None
    unit_of_measure_id: Optional[int] = None
    mapping_method: Optional[str] = None


class UOMSummary(BaseModel):
    id: int
    name: str
    abbreviation: str

    class Config:
        from_attributes = True


class MasterItemSummary(BaseModel):
    id: int
    name: str
    category: Optional[str] = None

    class Config:
        from_attributes = True


class VendorItemSummary(BaseModel):
    id: int
    vendor_product_name: str
    vendor_sku: Optional[str] = None
    pack_size: Optional[str] = None
    conversion_factor: Optional[float] = None
    purchase_unit: Optional[UOMSummary] = None

    class Config:
        from_attributes = True


class InvoiceItemInDB(InvoiceItemBase):
    id: int
    invoice_id: int
    vendor_item_id: Optional[int] = None
    vendor_item: Optional[VendorItemSummary] = None
    master_item_id: Optional[int] = None
    master_item: Optional[MasterItemSummary] = None
    mapping_confidence: Optional[float] = None
    mapping_method: Optional[str] = None
    unit_of_measure_id: Optional[int] = None
    unit_of_measure: Optional[UOMSummary] = None
    last_price: Optional[float] = None
    price_change_pct: Optional[float] = None
    is_anomaly: Optional[str] = None
    mapped_by_id: Optional[int] = None
    mapped_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Invoice schemas
class InvoiceBase(BaseModel):
    vendor_id: Optional[int] = None
    location_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    filename: str
    file_path: str
    file_type: str


class InvoiceUpdate(BaseModel):
    vendor_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[InvoiceStatus] = None


class InvoiceInDB(InvoiceBase):
    id: int
    filename: str
    file_path: str
    file_type: str
    status: InvoiceStatus
    parsed_data: Optional[dict] = None
    confidence_score: Optional[float] = None
    anomalies: Optional[List[dict]] = None
    uploaded_by_id: Optional[int] = None
    reviewed_by_id: Optional[int] = None
    approved_by_id: Optional[int] = None
    uploaded_at: datetime
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    updated_at: datetime
    items: List[InvoiceItemInDB] = []

    class Config:
        from_attributes = True


class InvoiceWithDetails(InvoiceInDB):
    """Invoice with vendor and user details"""
    vendor_name: Optional[str] = None
    location_name: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    approved_by_name: Optional[str] = None


class InvoiceList(BaseModel):
    """Invoice list item (without full details)"""
    id: int
    filename: str
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    total: Optional[float] = None
    status: InvoiceStatus
    uploaded_at: datetime
    uploaded_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceParseRequest(BaseModel):
    """Request to parse an invoice"""
    invoice_id: int


class InvoiceParseResponse(BaseModel):
    """Response from invoice parsing"""
    success: bool
    message: str
    invoice_id: int
    confidence_score: Optional[float] = None
    items_parsed: Optional[int] = None
    items_mapped: Optional[int] = None


class InvoiceApproveRequest(BaseModel):
    """Request to approve an invoice"""
    notes: Optional[str] = None


class InvoiceRejectRequest(BaseModel):
    """Request to reject an invoice"""
    reason: str
