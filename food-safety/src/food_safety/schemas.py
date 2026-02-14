"""Pydantic schemas for Food Safety & Compliance Service"""
from datetime import datetime, date, time
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field
from food_safety.models import (
    UserRole, TemperatureAlertStatus, ChecklistType, ChecklistStatus,
    IncidentType, IncidentStatus, IncidentCategory, CorrectiveActionStatus,
    InspectionType, ViolationSeverity
)


# ==================== User Permission Schemas ====================

class UserPermissionBase(BaseModel):
    hr_user_id: int
    role: UserRole = UserRole.STAFF
    location_ids: Optional[str] = None
    can_manage_templates: bool = False
    can_manage_users: bool = False
    can_view_reports: bool = True
    can_sign_off: bool = False
    is_active: bool = True


class UserPermissionCreate(UserPermissionBase):
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None


class UserPermissionUpdate(BaseModel):
    role: Optional[UserRole] = None
    location_ids: Optional[str] = None
    can_manage_templates: Optional[bool] = None
    can_manage_users: Optional[bool] = None
    can_view_reports: Optional[bool] = None
    can_sign_off: Optional[bool] = None
    is_active: Optional[bool] = None


class UserPermissionResponse(UserPermissionBase):
    id: int
    employee_name: Optional[str]
    employee_email: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


# ==================== Location Schemas ====================

class LocationBase(BaseModel):
    inventory_location_id: int
    name: str = Field(..., max_length=200)
    address: Optional[str] = None
    is_active: bool = True


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    is_active: Optional[bool] = None


class LocationResponse(LocationBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Shift Schemas ====================

class ShiftBase(BaseModel):
    name: str = Field(..., max_length=100)
    start_time: time
    end_time: time
    is_active: bool = True


class ShiftCreate(ShiftBase):
    location_id: int


class ShiftUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_active: Optional[bool] = None


class ShiftResponse(ShiftBase):
    id: int
    location_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Equipment Temperature Threshold Override Schemas ====================

class EquipmentTempThresholdBase(BaseModel):
    """Local temperature threshold override for equipment from Maintenance service"""
    maintenance_equipment_id: int
    equipment_name: str = Field(..., max_length=200)
    equipment_type: Optional[str] = Field(None, max_length=100)
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: str = "F"
    alert_on_violation: bool = True
    is_active: bool = True


class EquipmentTempThresholdCreate(EquipmentTempThresholdBase):
    location_id: int


class EquipmentTempThresholdUpdate(BaseModel):
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: Optional[str] = None
    alert_on_violation: Optional[bool] = None
    is_active: Optional[bool] = None


class EquipmentTempThresholdResponse(EquipmentTempThresholdBase):
    id: int
    location_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaintenanceEquipmentResponse(BaseModel):
    """Equipment data returned from Maintenance service"""
    id: int
    name: str
    location_id: int
    category_name: Optional[str] = None
    equipment_type: Optional[str] = None
    status: str = "operational"
    serial_number: Optional[str] = None
    model_number: Optional[str] = None
    manufacturer: Optional[str] = None
    qr_code: Optional[str] = None
    min_temp: Optional[float] = None
    max_temp: Optional[float] = None
    temp_unit: str = "F"
    has_override: bool = False


# ==================== Temperature Threshold Schemas ====================

class TemperatureThresholdBase(BaseModel):
    equipment_type: str = Field(..., max_length=100)
    min_temp: Decimal
    max_temp: Decimal
    temp_unit: str = "F"
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    alert_on_violation: bool = True


class TemperatureThresholdCreate(TemperatureThresholdBase):
    pass


class TemperatureThresholdUpdate(BaseModel):
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: Optional[str] = None
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    alert_on_violation: Optional[bool] = None


class TemperatureThresholdResponse(TemperatureThresholdBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Temperature Log Schemas ====================

class TemperatureLogBase(BaseModel):
    equipment_id: int  # References maintenance_equipment_id
    temperature: Decimal
    temp_unit: str = "F"
    shift_id: Optional[int] = None
    notes: Optional[str] = None


class TemperatureLogCreate(TemperatureLogBase):
    logged_by: int
    corrective_action: Optional[str] = None


class TemperatureLogResponse(BaseModel):
    id: int
    maintenance_equipment_id: int
    equipment_name: str
    location_id: int
    temperature: Decimal
    temp_unit: str
    min_threshold: Optional[Decimal]
    max_threshold: Optional[Decimal]
    is_within_range: bool
    alert_status: Optional[TemperatureAlertStatus]
    alert_acknowledged_by: Optional[int]
    alert_acknowledged_at: Optional[datetime]
    alert_notes: Optional[str]
    corrective_action: Optional[str]
    logged_by: int
    logged_at: datetime
    shift_id: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


class TemperatureLogWithDetails(TemperatureLogResponse):
    location_name: Optional[str] = None
    logged_by_name: Optional[str] = None


class TemperatureAlertAcknowledge(BaseModel):
    acknowledged_by: int
    notes: Optional[str] = None
    corrective_action: Optional[str] = None


# ==================== Checklist Template Schemas ====================

class ChecklistItemBase(BaseModel):
    text: str = Field(..., max_length=500)
    description: Optional[str] = None
    response_type: str = Field(..., max_length=50)  # "yes_no", "pass_fail", "numeric", "text", "temperature"
    min_value: Optional[str] = Field(None, max_length=50)
    max_value: Optional[str] = Field(None, max_length=50)
    is_required: bool = True
    sort_order: int = 0
    section: Optional[str] = Field(None, max_length=100)
    requires_corrective_action: bool = True


class ChecklistItemCreate(ChecklistItemBase):
    pass


class ChecklistItemResponse(ChecklistItemBase):
    id: int
    template_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChecklistTemplateBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    checklist_type: ChecklistType
    frequency: str = Field(..., max_length=50)
    requires_manager_signoff: bool = False
    is_active: bool = True


class ChecklistTemplateCreate(ChecklistTemplateBase):
    location_id: Optional[int] = None
    shift_id: Optional[int] = None
    items: List[ChecklistItemCreate] = []


class ChecklistTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    checklist_type: Optional[ChecklistType] = None
    location_id: Optional[int] = None
    shift_id: Optional[int] = None
    frequency: Optional[str] = Field(None, max_length=50)
    requires_manager_signoff: Optional[bool] = None
    is_active: Optional[bool] = None
    items: Optional[List[ChecklistItemCreate]] = None


class ChecklistTemplateResponse(ChecklistTemplateBase):
    id: int
    location_id: Optional[int]
    shift_id: Optional[int]
    item_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


class ChecklistTemplateWithItems(ChecklistTemplateResponse):
    items: List[ChecklistItemResponse] = []
    location_name: Optional[str] = None


# ==================== Checklist Submission Schemas ====================

class ChecklistResponseBase(BaseModel):
    item_id: int
    response_value: Optional[str] = Field(None, max_length=500)
    is_passing: Optional[bool] = None
    corrective_action: Optional[str] = None
    notes: Optional[str] = None


class ChecklistResponseCreate(ChecklistResponseBase):
    responded_by: Optional[int] = None


class ChecklistResponseDetail(ChecklistResponseBase):
    id: int
    submission_id: int
    created_at: datetime
    responded_by: Optional[int]
    item_text: Optional[str] = None

    class Config:
        from_attributes = True


class ChecklistSubmissionBase(BaseModel):
    template_id: int
    location_id: int
    submission_date: date
    shift_id: Optional[int] = None
    notes: Optional[str] = None


class ChecklistSubmissionCreate(ChecklistSubmissionBase):
    responses: List[ChecklistResponseCreate] = []


class ChecklistSubmissionUpdate(BaseModel):
    notes: Optional[str] = None
    responses: Optional[List[ChecklistResponseCreate]] = None


class ChecklistSubmissionComplete(BaseModel):
    completed_by: int
    responses: List[ChecklistResponseCreate]
    notes: Optional[str] = None


class ChecklistSubmissionResponse(ChecklistSubmissionBase):
    id: int
    status: ChecklistStatus
    completed_by: Optional[int]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    template_name: Optional[str] = None

    class Config:
        from_attributes = True


class ChecklistSubmissionWithDetails(ChecklistSubmissionResponse):
    template_name: Optional[str] = None
    location_name: Optional[str] = None
    completed_by_name: Optional[str] = None
    responses: List[ChecklistResponseDetail] = []


# ==================== Manager Signoff Schemas ====================

class ManagerSignoffCreate(BaseModel):
    signed_off_by: int
    is_approved: bool
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


class ManagerSignoffResponse(BaseModel):
    id: int
    submission_id: int
    signed_off_by: int
    signed_off_at: datetime
    is_approved: bool
    rejection_reason: Optional[str]
    notes: Optional[str]
    signed_off_by_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Incident Schemas ====================

class IncidentBase(BaseModel):
    location_id: int
    category: Optional[IncidentCategory] = IncidentCategory.FOOD_SAFETY
    incident_type: IncidentType
    title: str = Field(..., max_length=300)
    description: str
    incident_date: date
    incident_time: Optional[str] = Field(None, max_length=10)
    severity: str = Field(..., max_length=20)  # "low", "medium", "high", "critical"
    product_involved: Optional[str] = Field(None, max_length=200)
    area_involved: Optional[str] = Field(None, max_length=200)
    extra_data: Optional[dict] = None


class IncidentCreate(IncidentBase):
    reported_by: Optional[int] = None


class IncidentUpdate(BaseModel):
    incident_type: Optional[IncidentType] = None
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    incident_date: Optional[date] = None
    incident_time: Optional[str] = Field(None, max_length=10)
    status: Optional[IncidentStatus] = None
    severity: Optional[str] = Field(None, max_length=20)
    product_involved: Optional[str] = Field(None, max_length=200)
    area_involved: Optional[str] = Field(None, max_length=200)
    investigation_notes: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None
    extra_data: Optional[dict] = None


class IncidentInvestigate(BaseModel):
    investigated_by: int
    investigation_notes: str
    root_cause: Optional[str] = None


class IncidentResolve(BaseModel):
    resolved_by: int
    resolution_notes: str


class IncidentResponse(IncidentBase):
    id: int
    incident_number: str
    status: IncidentStatus
    reported_by: int
    reported_at: datetime
    investigated_by: Optional[int]
    investigation_notes: Optional[str]
    root_cause: Optional[str]
    resolved_by: Optional[int]
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IncidentWithDetails(IncidentResponse):
    location_name: Optional[str] = None
    reported_by_name: Optional[str] = None
    investigated_by_name: Optional[str] = None
    resolved_by_name: Optional[str] = None
    corrective_actions: List["CorrectiveActionResponse"] = []


# ==================== Corrective Action Schemas ====================

class CorrectiveActionBase(BaseModel):
    action_description: str
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None


class CorrectiveActionCreate(CorrectiveActionBase):
    incident_id: Optional[int] = None
    inspection_violation_id: Optional[int] = None


class CorrectiveActionUpdate(BaseModel):
    action_description: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None
    status: Optional[CorrectiveActionStatus] = None


class CorrectiveActionComplete(BaseModel):
    completed_by: int
    completion_notes: Optional[str] = None


class CorrectiveActionVerify(BaseModel):
    verified_by: int
    verification_notes: Optional[str] = None


class CorrectiveActionResponse(CorrectiveActionBase):
    id: int
    incident_id: Optional[int]
    inspection_violation_id: Optional[int]
    status: CorrectiveActionStatus
    completed_by: Optional[int]
    completed_at: Optional[datetime]
    completion_notes: Optional[str]
    verified_by: Optional[int]
    verified_at: Optional[datetime]
    verification_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    assigned_to_name: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Inspection Schemas ====================

class InspectionViolationBase(BaseModel):
    code: Optional[str] = Field(None, max_length=50)
    description: str
    severity: ViolationSeverity
    area: Optional[str] = Field(None, max_length=100)
    correction_deadline: Optional[date] = None
    notes: Optional[str] = None


class InspectionViolationCreate(InspectionViolationBase):
    pass


class InspectionViolationResponse(InspectionViolationBase):
    id: int
    inspection_id: int
    is_corrected: bool
    corrected_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    corrective_actions: List[CorrectiveActionResponse] = []

    class Config:
        from_attributes = True


class InspectionBase(BaseModel):
    location_id: int
    inspection_type: InspectionType
    inspection_date: date
    inspector_name: Optional[str] = Field(None, max_length=200)
    inspector_agency: Optional[str] = Field(None, max_length=200)
    score: Optional[Decimal] = None
    grade: Optional[str] = Field(None, max_length=10)
    passed: Optional[bool] = None
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    notes: Optional[str] = None
    report_url: Optional[str] = Field(None, max_length=500)


class InspectionCreate(InspectionBase):
    recorded_by: Optional[int] = None
    violations: List[InspectionViolationCreate] = []


class InspectionUpdate(BaseModel):
    inspection_type: Optional[InspectionType] = None
    inspection_date: Optional[date] = None
    inspector_name: Optional[str] = Field(None, max_length=200)
    inspector_agency: Optional[str] = Field(None, max_length=200)
    score: Optional[Decimal] = None
    grade: Optional[str] = Field(None, max_length=10)
    passed: Optional[bool] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    notes: Optional[str] = None
    report_url: Optional[str] = Field(None, max_length=500)


class InspectionResponse(InspectionBase):
    id: int
    recorded_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InspectionWithViolations(InspectionResponse):
    location_name: Optional[str] = None
    violations: List[InspectionViolationResponse] = []


# ==================== HACCP Schemas ====================

class CriticalControlPointBase(BaseModel):
    ccp_number: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    process_step: str = Field(..., max_length=200)
    hazard_description: str
    critical_limits: str
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: str = "F"
    max_time_minutes: Optional[int] = None
    monitoring_procedure: str
    monitoring_frequency: str = Field(..., max_length=100)
    corrective_action_procedure: str
    verification_procedure: Optional[str] = None
    records_required: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class CriticalControlPointCreate(CriticalControlPointBase):
    pass


class CriticalControlPointUpdate(BaseModel):
    ccp_number: Optional[str] = Field(None, max_length=20)
    name: Optional[str] = Field(None, max_length=200)
    process_step: Optional[str] = Field(None, max_length=200)
    hazard_description: Optional[str] = None
    critical_limits: Optional[str] = None
    min_temp: Optional[Decimal] = None
    max_temp: Optional[Decimal] = None
    temp_unit: Optional[str] = None
    max_time_minutes: Optional[int] = None
    monitoring_procedure: Optional[str] = None
    monitoring_frequency: Optional[str] = Field(None, max_length=100)
    corrective_action_procedure: Optional[str] = None
    verification_procedure: Optional[str] = None
    records_required: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CriticalControlPointResponse(CriticalControlPointBase):
    id: int
    haccp_plan_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HACCPPlanBase(BaseModel):
    location_id: int
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    version: str = "1.0"
    effective_date: date
    review_date: Optional[date] = None
    is_active: bool = True


class HACCPPlanCreate(HACCPPlanBase):
    created_by: Optional[int] = None
    critical_control_points: List[CriticalControlPointCreate] = []


class HACCPPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=20)
    effective_date: Optional[date] = None
    review_date: Optional[date] = None
    is_active: Optional[bool] = None


class HACCPPlanApprove(BaseModel):
    approved_by: int


class HACCPPlanResponse(HACCPPlanBase):
    id: int
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


class HACCPPlanWithCCPs(HACCPPlanResponse):
    location_name: Optional[str] = None
    critical_control_points: List[CriticalControlPointResponse] = []


# ==================== Dashboard Schemas ====================

class DashboardStats(BaseModel):
    total_equipment: int
    temperature_alerts_today: int
    checklists_due_today: int
    checklists_completed_today: int
    open_incidents: int
    pending_corrective_actions: int
    recent_temperatures: List[TemperatureLogWithDetails]
    pending_signoffs: List[ChecklistSubmissionWithDetails]


class DashboardAlerts(BaseModel):
    temperature_alerts: List[TemperatureLogWithDetails]
    overdue_checklists: List[ChecklistSubmissionWithDetails]
    open_incidents: List[IncidentWithDetails]
    overdue_corrective_actions: List[CorrectiveActionResponse]


# ==================== Report Schemas ====================

class TemperatureReportSummary(BaseModel):
    total_readings: int
    alerts_count: int
    compliance_rate: float  # Percentage within range
    avg_temperature: Optional[float] = None
    equipment_breakdown: List[dict] = []  # equipment_id, name, readings, alerts


class TemperatureReportTrend(BaseModel):
    date: str  # ISO format date
    readings_count: int
    alerts_count: int
    avg_temperature: Optional[float] = None


class TemperatureReportDetail(BaseModel):
    id: int
    equipment_name: Optional[str] = None
    location_name: Optional[str] = None
    temperature: float
    temp_unit: str = "F"
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None
    is_within_range: bool
    alert_status: Optional[str] = None
    logged_at: datetime
    logged_by: Optional[int] = None


class TemperatureReportResponse(BaseModel):
    summary: TemperatureReportSummary
    trends: List[TemperatureReportTrend]
    details: List[TemperatureReportDetail]
    filters_applied: dict


class ChecklistReportSummary(BaseModel):
    total_submissions: int
    completed_count: int
    pending_signoff_count: int
    completion_rate: float  # Percentage
    pass_rate: float  # Percentage of items passed
    by_template: List[dict] = []  # template_id, name, submissions, completion_rate


class ChecklistReportTrend(BaseModel):
    date: str
    submissions: int
    completed: int
    pending: int


class ChecklistReportDetail(BaseModel):
    id: int
    template_name: Optional[str] = None
    location_name: Optional[str] = None
    submission_date: date
    status: str
    completed_by: Optional[int] = None
    completed_at: Optional[datetime] = None
    items_total: int = 0
    items_passed: int = 0
    items_failed: int = 0


class ChecklistReportResponse(BaseModel):
    summary: ChecklistReportSummary
    trends: List[ChecklistReportTrend]
    details: List[ChecklistReportDetail]
    filters_applied: dict


class InspectionReportSummary(BaseModel):
    total_inspections: int
    passed_count: int
    failed_count: int
    average_score: Optional[float] = None
    violations_by_severity: dict = {}  # critical, major, minor counts
    pending_corrections: int = 0
    follow_ups_required: int = 0


class InspectionReportTrend(BaseModel):
    date: str
    inspections_count: int
    average_score: Optional[float] = None
    violations_count: int = 0


class InspectionReportDetail(BaseModel):
    id: int
    location_name: Optional[str] = None
    inspection_type: str
    inspection_date: date
    inspector_name: Optional[str] = None
    score: Optional[float] = None
    grade: Optional[str] = None
    passed: Optional[bool] = None
    violations_count: int = 0
    critical_violations: int = 0
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None


class InspectionReportResponse(BaseModel):
    summary: InspectionReportSummary
    trends: List[InspectionReportTrend]
    details: List[InspectionReportDetail]
    filters_applied: dict


class IncidentReportSummary(BaseModel):
    total_incidents: int
    open_count: int
    resolved_count: int
    closed_count: int
    by_type: dict = {}  # incident_type -> count
    by_severity: dict = {}  # severity -> count
    avg_resolution_hours: Optional[float] = None
    pending_corrective_actions: int = 0


class IncidentReportTrend(BaseModel):
    date: str
    incidents_count: int
    resolved_count: int


class IncidentReportDetail(BaseModel):
    id: int
    incident_number: str
    title: str
    location_name: Optional[str] = None
    incident_type: str
    severity: str
    status: str
    incident_date: date
    reported_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_hours: Optional[float] = None


class IncidentReportResponse(BaseModel):
    summary: IncidentReportSummary
    trends: List[IncidentReportTrend]
    details: List[IncidentReportDetail]
    filters_applied: dict


# Update forward references
IncidentWithDetails.model_rebuild()
