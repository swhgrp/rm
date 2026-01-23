"""Pydantic schemas for Forms Service"""
from datetime import datetime
from typing import Optional, List, Any, Dict
from uuid import UUID
from pydantic import BaseModel, Field
from forms.models import (
    FormCategory, SubmissionStatus, SignatureType, SignatureMethod,
    WorkflowStatus, AuditAction
)


# ==================== Workflow Schemas ====================

class WorkflowStepSchema(BaseModel):
    step_number: int
    name: str
    assignee_type: str
    assignee_employee_id: Optional[int] = None
    assignee_role: Optional[str] = None
    action_required: str
    conditions: Optional[Dict[str, Any]] = None
    escalation_hours: Optional[int] = None
    escalation_to: Optional[str] = None


class WorkflowBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    steps: List[WorkflowStepSchema]
    is_active: bool = True


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    steps: Optional[List[WorkflowStepSchema]] = None
    is_active: Optional[bool] = None


class WorkflowResponse(WorkflowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


# ==================== Template Schemas ====================

class FormTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100)
    category: FormCategory
    description: Optional[str] = None
    schema: Dict[str, Any]
    ui_schema: Optional[Dict[str, Any]] = None
    requires_signature: bool = False
    requires_manager_signature: bool = False
    retention_days: Optional[int] = None
    workflow_id: Optional[UUID] = None


class FormTemplateCreate(FormTemplateBase):
    pass


class FormTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    ui_schema: Optional[Dict[str, Any]] = None
    requires_signature: Optional[bool] = None
    requires_manager_signature: Optional[bool] = None
    retention_days: Optional[int] = None
    workflow_id: Optional[UUID] = None


class FormTemplateResponse(FormTemplateBase):
    id: UUID
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormTemplateSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    category: FormCategory
    description: Optional[str]
    version: int

    class Config:
        from_attributes = True


# ==================== Submission Schemas ====================

class FormSubmissionCreate(BaseModel):
    template_id: UUID
    location_id: int
    subject_employee_id: Optional[int] = None
    data: Dict[str, Any]


class FormSubmissionUpdate(BaseModel):
    data: Dict[str, Any]


class FormSubmissionResponse(BaseModel):
    id: UUID
    template_id: UUID
    template_version: int
    location_id: int
    subject_employee_id: Optional[int]
    submitted_by_employee_id: int
    data: Dict[str, Any]
    status: SubmissionStatus
    submitted_at: Optional[datetime]
    reference_number: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormSubmissionSummary(BaseModel):
    id: UUID
    template_id: UUID
    template_name: Optional[str] = None
    location_id: int
    location_name: Optional[str] = None
    subject_employee_id: Optional[int]
    subject_employee_name: Optional[str] = None
    submitted_by_employee_id: int
    submitted_by_name: Optional[str] = None
    status: SubmissionStatus
    reference_number: Optional[str]
    submitted_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class FormSubmissionDetail(FormSubmissionResponse):
    template: Optional[FormTemplateResponse] = None
    signatures: List["SignatureResponse"] = []
    attachments: List["AttachmentResponse"] = []
    workflow_status: Optional["WorkflowInstanceResponse"] = None


# ==================== Signature Schemas ====================

class SignatureCreate(BaseModel):
    signature_type: SignatureType
    signature_data: str
    signature_method: SignatureMethod


class SignatureResponse(BaseModel):
    id: UUID
    submission_id: UUID
    employee_id: int
    employee_name: Optional[str] = None
    signature_type: SignatureType
    signature_method: SignatureMethod
    signed_at: datetime

    class Config:
        from_attributes = True


class SignatureRequestCreate(BaseModel):
    submission_id: UUID
    requested_employee_id: int
    signature_type: SignatureType
    expires_at: Optional[datetime] = None


class SignatureRequestResponse(BaseModel):
    id: UUID
    submission_id: UUID
    requested_employee_id: int
    signature_type: SignatureType
    is_fulfilled: bool
    fulfilled_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Attachment Schemas ====================

class AttachmentCreate(BaseModel):
    description: Optional[str] = None


class AttachmentResponse(BaseModel):
    id: UUID
    submission_id: UUID
    file_id: UUID
    file_name: str
    file_type: str
    file_size: int
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Workflow Instance Schemas ====================

class WorkflowInstanceResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    submission_id: UUID
    current_step: int
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class WorkflowAdvanceRequest(BaseModel):
    action: str
    comments: Optional[str] = None


class WorkflowStepHistoryResponse(BaseModel):
    id: UUID
    step_number: int
    assigned_to_employee_id: int
    assigned_to_name: Optional[str] = None
    action_taken: Optional[str]
    comments: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==================== Audit Log Schemas ====================

class AuditLogResponse(BaseModel):
    id: UUID
    submission_id: Optional[UUID]
    template_id: Optional[UUID]
    employee_id: Optional[int]
    employee_name: Optional[str] = None
    action: AuditAction
    details: Optional[Dict[str, Any]]
    performed_at: datetime

    class Config:
        from_attributes = True


# ==================== Dashboard Schemas ====================

class DashboardMetrics(BaseModel):
    open_forms: Dict[str, int]
    my_action_items: List[FormSubmissionSummary]
    by_location: Dict[int, Dict[str, int]]
    recent_submissions: List[FormSubmissionSummary]
    alerts: List[Dict[str, Any]]


class TrendData(BaseModel):
    submissions_over_time: List[Dict[str, Any]]
    incidents_by_type: List[Dict[str, Any]]
    avg_resolution_time: Optional[float]


# ==================== Report Schemas ====================

class OSHAReportResponse(BaseModel):
    year: int
    summary: Dict[str, Any]
    cases: List[Dict[str, Any]]
    form_300_data: List[Dict[str, Any]]
    form_300a_data: Dict[str, Any]


# ==================== Notification Schemas ====================

class NotificationPreferenceUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    digest_mode: Optional[bool] = None
    notify_on_submission: Optional[bool] = None
    notify_on_signature_request: Optional[bool] = None
    notify_on_workflow_complete: Optional[bool] = None
    notify_on_escalation: Optional[bool] = None


class NotificationPreferenceResponse(BaseModel):
    id: UUID
    employee_id: int
    email_enabled: bool
    digest_mode: bool
    notify_on_submission: bool
    notify_on_signature_request: bool
    notify_on_workflow_complete: bool
    notify_on_escalation: bool

    class Config:
        from_attributes = True


# ==================== Pagination ====================

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


# Update forward refs
FormSubmissionDetail.model_rebuild()
