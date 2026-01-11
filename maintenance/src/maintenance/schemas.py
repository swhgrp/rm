"""Pydantic schemas for Maintenance & Equipment Tracking Service"""
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field
from maintenance.models import (
    EquipmentStatus, WorkOrderStatus, WorkOrderPriority, ScheduleFrequency, OwnershipType
)


# ==================== Equipment Category Schemas ====================

class EquipmentCategoryBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None


class EquipmentCategoryCreate(EquipmentCategoryBase):
    pass


class EquipmentCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[int] = None


class EquipmentCategoryResponse(EquipmentCategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EquipmentCategoryWithChildren(EquipmentCategoryResponse):
    subcategories: List["EquipmentCategoryWithChildren"] = []


# ==================== Equipment Schemas ====================

class EquipmentBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    category_id: Optional[int] = None
    location_id: int
    serial_number: Optional[str] = Field(None, max_length=100)
    model_number: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=200)
    status: EquipmentStatus = EquipmentStatus.OPERATIONAL
    purchase_date: Optional[date] = None
    warranty_expiration: Optional[date] = None
    installation_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    # Ownership
    ownership_type: OwnershipType = OwnershipType.OWNED
    owner_name: Optional[str] = Field(None, max_length=200)
    lease_contract_number: Optional[str] = Field(None, max_length=100)
    lease_expiration: Optional[date] = None
    # Additional
    notes: Optional[str] = None
    specifications: Optional[str] = None


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    serial_number: Optional[str] = Field(None, max_length=100)
    model_number: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=200)
    status: Optional[EquipmentStatus] = None
    purchase_date: Optional[date] = None
    warranty_expiration: Optional[date] = None
    installation_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    next_maintenance_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    # Ownership
    ownership_type: Optional[OwnershipType] = None
    owner_name: Optional[str] = Field(None, max_length=200)
    lease_contract_number: Optional[str] = Field(None, max_length=100)
    lease_expiration: Optional[date] = None
    # Additional
    notes: Optional[str] = None
    specifications: Optional[str] = None


class EquipmentResponse(EquipmentBase):
    id: int
    qr_code: str
    last_maintenance_date: Optional[date]
    next_maintenance_date: Optional[date]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


class EquipmentListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category_id: Optional[int]
    category_name: Optional[str] = None
    location_id: int
    location_name: Optional[str] = None
    status: EquipmentStatus
    serial_number: Optional[str]
    next_maintenance_date: Optional[date]
    qr_code: str
    ownership_type: OwnershipType = OwnershipType.OWNED
    owner_name: Optional[str] = None

    class Config:
        from_attributes = True


class EquipmentDetailResponse(EquipmentResponse):
    category: Optional[EquipmentCategoryResponse] = None
    location_name: Optional[str] = None


# ==================== Equipment History Schemas ====================

class EquipmentHistoryBase(BaseModel):
    change_type: str = Field(..., max_length=50)
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    notes: Optional[str] = None


class EquipmentHistoryCreate(EquipmentHistoryBase):
    equipment_id: int
    changed_by: Optional[int] = None


class EquipmentHistoryResponse(EquipmentHistoryBase):
    id: int
    equipment_id: int
    changed_by: Optional[int]
    changed_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Maintenance Schedule Schemas ====================

class MaintenanceScheduleBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    frequency: ScheduleFrequency
    custom_interval_days: Optional[int] = None
    next_due: date
    estimated_duration_minutes: Optional[int] = None
    checklist: Optional[str] = None
    assigned_to: Optional[int] = None
    vendor_id: Optional[int] = None
    is_external: bool = False
    is_active: bool = True


class MaintenanceScheduleCreate(MaintenanceScheduleBase):
    equipment_id: int


class MaintenanceScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    frequency: Optional[ScheduleFrequency] = None
    custom_interval_days: Optional[int] = None
    next_due: Optional[date] = None
    estimated_duration_minutes: Optional[int] = None
    checklist: Optional[str] = None
    assigned_to: Optional[int] = None
    vendor_id: Optional[int] = None
    is_external: Optional[bool] = None
    is_active: Optional[bool] = None


class MaintenanceScheduleResponse(MaintenanceScheduleBase):
    id: int
    equipment_id: int
    last_performed: Optional[date]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaintenanceScheduleWithEquipment(MaintenanceScheduleResponse):
    equipment_name: Optional[str] = None
    equipment_location_id: Optional[int] = None
    location_name: Optional[str] = None


# ==================== Work Order Schemas ====================

class WorkOrderBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    location_id: int
    due_date: Optional[date] = None
    is_external: bool = False


class WorkOrderCreate(WorkOrderBase):
    equipment_id: Optional[int] = None
    schedule_id: Optional[int] = None
    reported_by: Optional[int] = None
    assigned_to: Optional[int] = None
    vendor_id: Optional[int] = None
    estimated_cost: Optional[Decimal] = None


class WorkOrderUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    priority: Optional[WorkOrderPriority] = None
    status: Optional[WorkOrderStatus] = None
    location_id: Optional[int] = None
    assigned_to: Optional[str] = None  # Name of assignee (string)
    is_external: Optional[bool] = None
    vendor_id: Optional[int] = None
    due_date: Optional[date] = None
    completed_date: Optional[date] = None
    resolution_notes: Optional[str] = None
    root_cause: Optional[str] = None
    estimated_cost: Optional[Decimal] = None
    actual_cost: Optional[Decimal] = None
    labor_hours: Optional[Decimal] = None


class LogCompletedWork(BaseModel):
    """Schema for logging work that has already been completed"""
    title: str = Field(..., max_length=200)
    location_id: int
    resolution_notes: str
    completed_date: date
    equipment_id: Optional[int] = None
    description: Optional[str] = None
    root_cause: Optional[str] = None
    actual_cost: Optional[Decimal] = None
    labor_hours: Optional[Decimal] = None
    assigned_to: Optional[str] = None


class WorkOrderResponse(WorkOrderBase):
    id: int
    equipment_id: Optional[int]
    schedule_id: Optional[int]
    status: WorkOrderStatus
    reported_by: Optional[int]
    assigned_to: Optional[int]
    vendor_id: Optional[int]
    reported_date: datetime
    started_date: Optional[datetime]
    completed_date: Optional[datetime]
    resolution_notes: Optional[str]
    root_cause: Optional[str]
    estimated_cost: Optional[Decimal]
    actual_cost: Optional[Decimal]
    labor_hours: Optional[Decimal]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkOrderListResponse(BaseModel):
    id: int
    title: str
    equipment_id: Optional[int]
    equipment_name: Optional[str] = None
    location_id: int
    location_name: Optional[str] = None
    priority: WorkOrderPriority
    status: WorkOrderStatus
    assigned_to: Optional[int]
    assigned_to_name: Optional[str] = None
    reported_date: datetime
    due_date: Optional[date]

    class Config:
        from_attributes = True


class WorkOrderDetailResponse(WorkOrderResponse):
    equipment_name: Optional[str] = None
    location_name: Optional[str] = None
    reported_by_name: Optional[str] = None
    assigned_to_name: Optional[str] = None
    vendor_name: Optional[str] = None
    comments: List["WorkOrderCommentResponse"] = []
    parts_used: List["WorkOrderPartResponse"] = []


# ==================== Work Order Comment Schemas ====================

class WorkOrderCommentBase(BaseModel):
    comment: str
    is_internal: bool = False


class WorkOrderCommentCreate(WorkOrderCommentBase):
    work_order_id: int
    user_id: Optional[int] = None


class WorkOrderCommentResponse(WorkOrderCommentBase):
    id: int
    work_order_id: int
    user_id: Optional[int]
    user_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Work Order Part Schemas ====================

class WorkOrderPartBase(BaseModel):
    part_name: str = Field(..., max_length=200)
    part_number: Optional[str] = Field(None, max_length=100)
    quantity: Decimal
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None


class WorkOrderPartCreate(WorkOrderPartBase):
    work_order_id: int


class WorkOrderPartResponse(WorkOrderPartBase):
    id: int
    work_order_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Vendor Schemas ====================

class VendorBase(BaseModel):
    name: str = Field(..., max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    service_types: Optional[str] = None
    contract_number: Optional[str] = Field(None, max_length=100)
    contract_expiration: Optional[date] = None
    is_active: bool = True
    notes: Optional[str] = None


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    service_types: Optional[str] = None
    contract_number: Optional[str] = Field(None, max_length=100)
    contract_expiration: Optional[date] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class VendorResponse(VendorBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Dashboard Schemas ====================

class DashboardStats(BaseModel):
    total_equipment: int
    equipment_by_status: dict
    open_work_orders: int
    work_orders_by_priority: dict
    overdue_maintenance: int
    upcoming_maintenance_7_days: int
    recent_work_orders: List[WorkOrderListResponse]


class MaintenanceDueItem(BaseModel):
    schedule_id: int
    schedule_name: str
    equipment_id: int
    equipment_name: str
    location_id: int
    location_name: Optional[str] = None
    next_due: date
    days_until_due: int
    frequency: ScheduleFrequency


# Update forward references
EquipmentCategoryWithChildren.model_rebuild()
WorkOrderDetailResponse.model_rebuild()
