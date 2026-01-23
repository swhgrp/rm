"""SQLAlchemy models for Forms Service"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, BigInteger, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from forms.database import Base


# PostgreSQL ENUM types (must match migration)
PGFormCategory = ENUM('hr_employment', 'safety_compliance', 'operations', name='formcategory', create_type=False)
PGSubmissionStatus = ENUM('draft', 'submitted', 'pending_signature', 'pending_review', 'approved', 'rejected', 'archived', name='submissionstatus', create_type=False)
PGSignatureType = ENUM('employee', 'manager', 'witness', 'hr_representative', name='signaturetype', create_type=False)
PGSignatureMethod = ENUM('drawn', 'typed', 'uploaded', name='signaturemethod', create_type=False)
PGWorkflowStatus = ENUM('in_progress', 'completed', 'cancelled', name='workflowstatus', create_type=False)
PGAuditAction = ENUM('created', 'viewed', 'edited', 'signed', 'status_changed', 'exported', 'printed', 'workflow_advanced', 'archived', name='auditaction', create_type=False)


# ==================== Enums ====================

class FormCategory(str, PyEnum):
    HR_EMPLOYMENT = "hr_employment"
    SAFETY_COMPLIANCE = "safety_compliance"
    OPERATIONS = "operations"


class SubmissionStatus(str, PyEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_SIGNATURE = "pending_signature"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class SignatureType(str, PyEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    WITNESS = "witness"
    HR_REPRESENTATIVE = "hr_representative"


class SignatureMethod(str, PyEnum):
    DRAWN = "drawn"
    TYPED = "typed"
    UPLOADED = "uploaded"


class WorkflowStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AuditAction(str, PyEnum):
    CREATED = "created"
    VIEWED = "viewed"
    EDITED = "edited"
    SIGNED = "signed"
    STATUS_CHANGED = "status_changed"
    EXPORTED = "exported"
    PRINTED = "printed"
    WORKFLOW_ADVANCED = "workflow_advanced"
    ARCHIVED = "archived"


# ==================== Models ====================

class Workflow(Base):
    """Workflow definitions"""
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    steps = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer)
    updated_by = Column(Integer)

    templates = relationship("FormTemplate", back_populates="workflow")
    instances = relationship("WorkflowInstance", back_populates="workflow")


class FormTemplate(Base):
    """Form template definitions"""
    __tablename__ = "form_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    category = Column(PGFormCategory, nullable=False, index=True)
    description = Column(Text)
    schema = Column(JSONB, nullable=False)
    ui_schema = Column(JSONB)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, default=True, nullable=False)
    requires_signature = Column(Boolean, default=False, nullable=False)
    requires_manager_signature = Column(Boolean, default=False, nullable=False)
    retention_days = Column(Integer)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer)
    updated_by = Column(Integer)

    workflow = relationship("Workflow", back_populates="templates")
    submissions = relationship("FormSubmission", back_populates="template")

    __table_args__ = (
        Index("ix_form_templates_active", "is_active", postgresql_where=(is_active == True)),
    )


class FormSubmission(Base):
    """Form submissions"""
    __tablename__ = "form_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("form_templates.id"), nullable=False, index=True)
    template_version = Column(Integer, nullable=False)
    location_id = Column(Integer, nullable=False, index=True)
    subject_employee_id = Column(Integer, index=True)
    submitted_by_employee_id = Column(Integer, nullable=False, index=True)
    data = Column(JSONB, nullable=False)
    status = Column(PGSubmissionStatus, default='draft', nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True))
    reference_number = Column(String(50), unique=True, index=True)
    related_submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id"))
    archived_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer)
    updated_by = Column(Integer)

    template = relationship("FormTemplate", back_populates="submissions")
    related_submission = relationship("FormSubmission", remote_side=[id])
    signatures = relationship("Signature", back_populates="submission", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="submission", cascade="all, delete-orphan")
    workflow_instance = relationship("WorkflowInstance", back_populates="submission", uselist=False, cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="submission")

    __table_args__ = (
        Index("ix_form_submissions_created_desc", created_at.desc()),
    )


class Signature(Base):
    """Electronic signatures"""
    __tablename__ = "signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    signature_type = Column(PGSignatureType, nullable=False)
    signature_data = Column(Text, nullable=False)
    signature_method = Column(PGSignatureMethod, nullable=False)
    ip_address = Column(INET)
    user_agent = Column(Text)
    signed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    submission = relationship("FormSubmission", back_populates="signatures")


class WorkflowInstance(Base):
    """Active workflow instances"""
    __tablename__ = "workflow_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    current_step = Column(Integer, default=0, nullable=False)
    status = Column(PGWorkflowStatus, default='in_progress', nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    workflow = relationship("Workflow", back_populates="instances")
    submission = relationship("FormSubmission", back_populates="workflow_instance")
    step_history = relationship("WorkflowStepHistory", back_populates="workflow_instance", cascade="all, delete-orphan")


class WorkflowStepHistory(Base):
    """Workflow step completion history"""
    __tablename__ = "workflow_step_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_instance_id = Column(UUID(as_uuid=True), ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    assigned_to_employee_id = Column(Integer, nullable=False)
    action_taken = Column(String(50))
    comments = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    workflow_instance = relationship("WorkflowInstance", back_populates="step_history")


class Attachment(Base):
    """File attachments"""
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(UUID(as_uuid=True), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer)

    submission = relationship("FormSubmission", back_populates="attachments")


class AuditLog(Base):
    """Audit trail for compliance"""
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="SET NULL"), index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("form_templates.id", ondelete="SET NULL"), index=True)
    employee_id = Column(Integer, index=True)
    action = Column(PGAuditAction, nullable=False, index=True)
    details = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(Text)
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    submission = relationship("FormSubmission", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_log_performed_desc", performed_at.desc()),
    )


class NotificationPreference(Base):
    """User notification preferences"""
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(Integer, nullable=False, unique=True)
    email_enabled = Column(Boolean, default=True, nullable=False)
    digest_mode = Column(Boolean, default=False, nullable=False)
    notify_on_submission = Column(Boolean, default=True, nullable=False)
    notify_on_signature_request = Column(Boolean, default=True, nullable=False)
    notify_on_workflow_complete = Column(Boolean, default=True, nullable=False)
    notify_on_escalation = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SignatureRequest(Base):
    """Pending signature requests"""
    __tablename__ = "signature_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_employee_id = Column(Integer, nullable=False, index=True)
    signature_type = Column(PGSignatureType, nullable=False)
    is_fulfilled = Column(Boolean, default=False, nullable=False)
    fulfilled_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    token = Column(String(255), unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer)
