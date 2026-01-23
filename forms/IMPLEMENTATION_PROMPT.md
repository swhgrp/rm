# Forms Service Implementation Prompt

## Project Overview

Build a comprehensive Forms service for SW Hospitality Group's restaurant management platform. This service handles digital form creation, submission, signatures, workflow routing, and compliance documentation across 6 restaurant locations.

**Technology Stack:**
- Backend: FastAPI with Python 3.11
- Database: PostgreSQL 15 with JSONB (async with asyncpg)
- Frontend: Jinja2 templates + htmx for admin interface
- Form Rendering: react-jsonschema-form with custom widgets
- PDF Generation: WeasyPrint
- Signature Capture: signature_pad.js
- Background Tasks: APScheduler (consistent with other services)
- Containerization: Docker

**Service Location:** `/opt/restaurant-system/forms`

**Service Port:** 8000 (internal), Nginx routes `/forms/` to this service

**External Port Mapping:** 8007:8000 (for standalone development)

**API Prefix:** `/api/` (not `/api/v1/`)

**Network:** `restaurant-network` (external)

**Authentication:** Portal SSO with `PORTAL_SECRET_KEY`

---

## Directory Structure

```
/opt/restaurant-system/forms/
├── src/
│   └── forms/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── auth.py
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── templates.py
│       │   ├── submissions.py
│       │   ├── signatures.py
│       │   ├── workflows.py
│       │   ├── attachments.py
│       │   ├── dashboard.py
│       │   └── reports.py
│       └── services/
│           ├── __init__.py
│           ├── hr_client.py
│           ├── inventory_client.py
│           ├── files_client.py
│           ├── pdf_generator.py
│           ├── workflow_engine.py
│           ├── notification_service.py
│           ├── audit_service.py
│           └── scheduler.py
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── templates/
│   ├── admin/
│   │   ├── base.html
│   │   ├── templates_list.html
│   │   ├── template_builder.html
│   │   ├── submissions_list.html
│   │   ├── submission_detail.html
│   │   └── dashboard.html
│   ├── print/
│   │   ├── base.css
│   │   ├── generic.html
│   │   ├── first-report-of-injury.html
│   │   ├── incident-report.html
│   │   └── ... (one per form type)
│   └── email/
│       ├── signature_request.html
│       ├── workflow_assignment.html
│       └── digest.html
├── static/
│   ├── css/
│   ├── js/
│   │   ├── signature-widget.js
│   │   └── form-renderer.js
│   └── img/
├── form_schemas/
│   ├── exit-interview/
│   │   ├── schema.json
│   │   └── ui_schema.json
│   ├── first-report-of-injury/
│   │   ├── schema.json
│   │   └── ui_schema.json
│   └── ... (one folder per form type)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_templates.py
│   ├── test_submissions.py
│   ├── test_signatures.py
│   ├── test_workflows.py
│   └── test_reports.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── .env.example
└── README.md
```

---

## Configuration

### config.py

```python
"""Configuration settings for Forms Service"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database (async for FastAPI, sync for Alembic)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://forms:forms@forms-db:5432/forms"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://forms:forms@forms-db:5432/forms"
    )

    # Service URLs
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-app:8000")
    HR_SERVICE_URL: str = os.getenv("HR_SERVICE_URL", "http://hr-app:8000")
    HUB_SERVICE_URL: str = os.getenv("HUB_SERVICE_URL", "http://integration-hub:8000")
    FILES_SERVICE_URL: str = os.getenv("FILES_SERVICE_URL", "http://files-app:8000")
    PORTAL_URL: str = os.getenv("PORTAL_URL", "http://portal-app:8000")

    # Application
    APP_NAME: str = "Forms Service"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    BASE_URL: str = os.getenv("BASE_URL", "https://rm.swhgrp.com")

    # Authentication
    SECRET_KEY: str = os.getenv("SECRET_KEY", "forms-secret-key-change-in-production")
    PORTAL_SECRET_KEY: str = os.getenv("PORTAL_SECRET_KEY", "")
    ALGORITHM: str = "HS256"

    # File uploads
    MAX_FILE_SIZE: int = 10485760  # 10MB
    ALLOWED_FILE_TYPES: list = ["image/jpeg", "image/png", "image/heic", "application/pdf"]

    # Scheduler
    ESCALATION_CHECK_INTERVAL_MINUTES: int = 15
    RETENTION_CHECK_HOUR: int = 2  # 2 AM
    DIGEST_HOUR: int = 7  # 7 AM

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

### database.py

```python
"""Database configuration and session management"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from forms.config import settings

# Async engine for FastAPI
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync engine for Alembic migrations
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

---

## Authentication

### auth.py

```python
"""Portal SSO authentication"""
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
import httpx
import logging

from forms.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_current_user(request: Request):
    """Validate session with Portal service."""
    session_token = request.cookies.get("session_token")

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.PORTAL_URL}/api/auth/validate",
                json={"token": session_token},
                headers={"X-Service-Key": settings.PORTAL_SECRET_KEY}
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid session"
                )

            return response.json()["user"]
    except httpx.RequestError as e:
        logger.error(f"Portal auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )


async def require_admin(user: dict = Depends(get_current_user)):
    """Require admin role."""
    if user.get("role") not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


async def require_manager(user: dict = Depends(get_current_user)):
    """Require manager or higher role."""
    if user.get("role") not in ["manager", "gm", "admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required"
        )
    return user
```

---

## Database Models

### models.py

```python
"""SQLAlchemy models for Forms Service"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Enum, BigInteger, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from forms.database import Base


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
    category = Column(Enum(FormCategory), nullable=False, index=True)
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
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.DRAFT, nullable=False, index=True)
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
    signature_type = Column(Enum(SignatureType), nullable=False)
    signature_data = Column(Text, nullable=False)
    signature_method = Column(Enum(SignatureMethod), nullable=False)
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
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.IN_PROGRESS, nullable=False, index=True)
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
    action = Column(Enum(AuditAction), nullable=False, index=True)
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
```

### Workflow Steps JSONB Structure

```json
{
  "steps": [
    {
      "step_number": 1,
      "name": "Manager Review",
      "assignee_type": "submitter_manager",
      "assignee_employee_id": null,
      "assignee_role": null,
      "action_required": "review",
      "conditions": {
        "if": [{">=": [{"var": "injury_severity"}, 3]}, true, false]
      },
      "escalation_hours": 48,
      "escalation_to": "location_gm"
    }
  ]
}
```

---

## Pydantic Schemas

### schemas.py

```python
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


# Update forward refs
FormSubmissionDetail.model_rebuild()
```

---

## Main Application

### main.py

```python
"""Main FastAPI application for Forms Service"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from forms.config import settings
from forms.database import init_db
from forms.routers import templates, submissions, signatures, workflows, attachments, dashboard, reports
from forms.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Forms Service...")
    await init_db()
    start_scheduler()
    logger.info("Forms Service started successfully")
    yield
    logger.info("Shutting down Forms Service...")
    stop_scheduler()


app = FastAPI(
    title="Forms Service",
    description="Digital forms, signatures, and workflow management for SW Hospitality Group",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/forms",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates_jinja = Jinja2Templates(directory="templates")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Routers - /api/ prefix (not /api/v1/)
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(submissions.router, prefix="/api/submissions", tags=["Submissions"])
app.include_router(signatures.router, prefix="/api/signatures", tags=["Signatures"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["Attachments"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "forms"}


@app.get("/")
async def root():
    return {"service": "Forms Service", "version": "1.0.0", "docs": "/forms/docs"}
```

---

## API Endpoints

All endpoints use `/api/` prefix (not `/api/v1/`).

### Templates API (`/api/templates`)

```python
# GET /api/templates - List all active templates
# GET /api/templates/{template_id} - Get full template with schema
# POST /api/templates - Create new template (admin only)
# PUT /api/templates/{template_id} - Update template (creates new version)
# GET /api/templates/{template_id}/versions - List all versions
# POST /api/templates/{template_id}/duplicate - Copy template
# DELETE /api/templates/{template_id} - Soft delete (is_active=false)
```

### Submissions API (`/api/submissions`)

```python
# GET /api/submissions - List with filters (template_id, location_id, status, date_from, date_to, search, page, per_page)
# GET /api/submissions/{submission_id} - Get full submission with signatures, attachments, workflow
# POST /api/submissions - Create new (starts as draft), generates reference_number
# PUT /api/submissions/{submission_id} - Update draft only
# POST /api/submissions/{submission_id}/submit - Submit for processing
# GET /api/submissions/{submission_id}/pdf - Generate PDF
# POST /api/submissions/{submission_id}/archive - Archive (approved/rejected only)
# GET /api/submissions/{submission_id}/audit-log - Get audit trail
```

### Signatures API (`/api/signatures`)

```python
# GET /api/submissions/{submission_id}/signatures - List signatures
# POST /api/submissions/{submission_id}/signatures - Add signature
# GET /api/signatures/pending - Forms pending current user's signature
# DELETE /api/submissions/{submission_id}/signatures/{signature_id} - Remove (admin only)
```

### Workflows API (`/api/workflows`)

```python
# GET /api/workflows - List all (admin only)
# GET /api/workflows/{workflow_id} - Get with steps
# POST /api/workflows - Create (admin only)
# PUT /api/workflows/{workflow_id} - Update
# GET /api/submissions/{submission_id}/workflow - Get instance status
# POST /api/submissions/{submission_id}/workflow/advance - Advance step
```

### Attachments API (`/api/attachments`)

```python
# GET /api/submissions/{submission_id}/attachments - List
# POST /api/submissions/{submission_id}/attachments - Upload (max 10MB)
# GET /api/attachments/{attachment_id} - Get metadata and download URL
# DELETE /api/attachments/{attachment_id} - Remove (draft only)
```

### Dashboard API (`/api/dashboard`)

```python
# GET /api/dashboard - Metrics for current user
# GET /api/dashboard/trends - Trend data for charts
```

### Reports API (`/api/reports`)

```python
# GET /api/reports/osha - OSHA Form 300/300A/301 data
# GET /api/reports/incidents - Incident trends
# GET /api/reports/disciplinary - Disciplinary summary
# GET /api/reports/export - Export to CSV/Excel
```

---

## Background Tasks with APScheduler

### services/scheduler.py

```python
"""Background task scheduler using APScheduler"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from forms.config import settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def check_escalations():
    """Check for overdue workflow steps and escalate."""
    logger.info("Checking for workflow escalations...")
    # Query overdue steps and escalate


async def process_retention():
    """Archive submissions past retention period."""
    logger.info("Processing retention policies...")
    # Find and archive old submissions


async def send_notification_digest():
    """Send daily digest of non-urgent notifications."""
    logger.info("Sending notification digests...")
    # Bundle and send digest emails


def start_scheduler():
    """Start background task scheduler"""
    if not scheduler.running:
        # Escalations every 15 minutes
        scheduler.add_job(
            check_escalations,
            IntervalTrigger(minutes=settings.ESCALATION_CHECK_INTERVAL_MINUTES),
            id='check_escalations',
            replace_existing=True
        )

        # Retention daily at 2 AM
        scheduler.add_job(
            process_retention,
            CronTrigger(hour=settings.RETENTION_CHECK_HOUR, minute=0),
            id='process_retention',
            replace_existing=True
        )

        # Digests daily at 7 AM
        scheduler.add_job(
            send_notification_digest,
            CronTrigger(hour=settings.DIGEST_HOUR, minute=0),
            id='send_notification_digest',
            replace_existing=True
        )

        scheduler.start()
        logger.info("Scheduler started: escalations, retention, digests")


def stop_scheduler():
    """Stop scheduler gracefully"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
```

---

## Service Clients

### services/hr_client.py

```python
"""HR service client"""
import httpx
from typing import Optional, Dict, List
from datetime import datetime
import logging

from forms.config import settings

logger = logging.getLogger(__name__)
CACHE_TTL = 300


class HRClient:
    def __init__(self):
        self.base_url = settings.HR_SERVICE_URL
        self._cache: Dict[int, dict] = {}
        self._timestamps: Dict[int, datetime] = {}

    async def get_employee(self, employee_id: int) -> Optional[dict]:
        if self._is_valid(employee_id):
            return self._cache[employee_id]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/employees/{employee_id}")
                response.raise_for_status()
                employee = response.json()
                self._cache[employee_id] = employee
                self._timestamps[employee_id] = datetime.now()
                return employee
        except Exception as e:
            logger.error(f"HR client error: {e}")
            return None

    async def get_employee_manager(self, employee_id: int) -> Optional[dict]:
        employee = await self.get_employee(employee_id)
        if employee and employee.get("manager_id"):
            return await self.get_employee(employee["manager_id"])
        return None

    async def get_location_hr_rep(self, location_id: int) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/locations/{location_id}/hr-representative")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"HR client error: {e}")
            return None

    async def search_employees(self, query: str, location_id: int = None) -> List[dict]:
        try:
            params = {"search": query}
            if location_id:
                params["location_id"] = location_id
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/employees", params=params)
                response.raise_for_status()
                return response.json().get("items", [])
        except Exception as e:
            logger.error(f"HR client error: {e}")
            return []

    def _is_valid(self, employee_id: int) -> bool:
        if employee_id not in self._timestamps:
            return False
        return (datetime.now() - self._timestamps[employee_id]).total_seconds() < CACHE_TTL


hr_client = HRClient()
```

### services/inventory_client.py

```python
"""Inventory service client"""
import httpx
from typing import Optional, List
import logging

from forms.config import settings

logger = logging.getLogger(__name__)


class InventoryClient:
    def __init__(self):
        self.base_url = settings.INVENTORY_SERVICE_URL

    async def get_locations(self) -> List[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/locations/_sync")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Inventory client error: {e}")
            return []

    async def get_location(self, location_id: int) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/locations/{location_id}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Inventory client error: {e}")
            return None


inventory_client = InventoryClient()
```

### services/files_client.py

```python
"""Files service client"""
import httpx
from typing import Optional
import logging

from forms.config import settings

logger = logging.getLogger(__name__)


class FilesClient:
    def __init__(self):
        self.base_url = settings.FILES_SERVICE_URL

    async def upload_file(self, file_content: bytes, filename: str, content_type: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"file": (filename, file_content, content_type)}
                response = await client.post(f"{self.base_url}/api/files", files=files)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Files client error: {e}")
            return None

    async def get_download_url(self, file_id: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/files/{file_id}/url")
                response.raise_for_status()
                return response.json().get("url")
        except Exception as e:
            logger.error(f"Files client error: {e}")
            return None

    async def delete_file(self, file_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(f"{self.base_url}/api/files/{file_id}")
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Files client error: {e}")
            return False


files_client = FilesClient()
```

### services/audit_service.py

```python
"""Audit logging service"""
from uuid import UUID
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from forms.models import AuditLog, AuditAction


async def log_audit(
    db: AsyncSession,
    action: AuditAction,
    submission_id: Optional[UUID] = None,
    template_id: Optional[UUID] = None,
    employee_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> AuditLog:
    """Log an audit event"""
    entry = AuditLog(
        action=action,
        submission_id=submission_id,
        template_id=template_id,
        employee_id=employee_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.add(entry)
    await db.commit()
    return entry
```

### services/pdf_generator.py

```python
"""PDF generation with WeasyPrint"""
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime
from typing import List
import logging

logger = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "templates" / "print"


class PDFGenerator:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        self.base_css_path = TEMPLATES_DIR / "base.css"
        self.env.filters['format_date'] = lambda v: v.strftime('%m/%d/%Y') if v else ''
        self.env.filters['format_datetime'] = lambda v: v.strftime('%m/%d/%Y %I:%M %p') if v else ''

    async def generate_submission_pdf(
        self, submission, template, signatures: List = None, include_signatures: bool = True
    ) -> bytes:
        template_name = f"{template.slug}.html"
        if not (TEMPLATES_DIR / template_name).exists():
            template_name = "generic.html"

        jinja_template = self.env.get_template(template_name)
        html_content = jinja_template.render(
            submission=submission,
            template=template,
            signatures=signatures if include_signatures else [],
            generated_at=datetime.now().isoformat()
        )

        html = HTML(string=html_content, base_url=str(TEMPLATES_DIR))
        stylesheets = [CSS(filename=str(self.base_css_path))] if self.base_css_path.exists() else []
        return html.write_pdf(stylesheets=stylesheets)
```

### services/workflow_engine.py

```python
"""Workflow execution engine"""
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from forms.models import (
    Workflow, WorkflowInstance, WorkflowStepHistory,
    FormSubmission, WorkflowStatus, SubmissionStatus
)
from forms.services.hr_client import hr_client
from forms.services.inventory_client import inventory_client

logger = logging.getLogger(__name__)


class WorkflowEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_workflow(self, submission_id: UUID, workflow_id: UUID) -> UUID:
        result = await self.db.execute(select(Workflow).where(Workflow.id == workflow_id))
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        instance = WorkflowInstance(
            workflow_id=workflow_id,
            submission_id=submission_id,
            current_step=0,
            status=WorkflowStatus.IN_PROGRESS
        )
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)

        steps = workflow.steps.get("steps", [])
        if steps:
            await self._execute_step(instance, steps[0])

        return instance.id

    async def advance_workflow(
        self, submission_id: UUID, employee_id: int, action: str, comments: Optional[str] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.submission_id == submission_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("No workflow instance found")

        result = await self.db.execute(select(Workflow).where(Workflow.id == instance.workflow_id))
        workflow = result.scalar_one_or_none()
        steps = workflow.steps.get("steps", [])

        # Record completion
        step_history = WorkflowStepHistory(
            workflow_instance_id=instance.id,
            step_number=instance.current_step,
            assigned_to_employee_id=employee_id,
            action_taken=action,
            comments=comments,
            completed_at=datetime.utcnow()
        )
        self.db.add(step_history)

        if action == 'rejected':
            await self._handle_rejection(instance)
            return {'status': 'rejected'}

        next_step = instance.current_step + 1
        if next_step >= len(steps):
            await self._complete_workflow(instance)
            return {'status': 'completed'}

        instance.current_step = next_step
        await self.db.commit()
        await self._execute_step(instance, steps[next_step])
        return {'status': 'advanced', 'step': next_step}

    async def _execute_step(self, instance: WorkflowInstance, step: dict):
        assignee = await self._resolve_assignee(instance, step)
        if assignee:
            history = WorkflowStepHistory(
                workflow_instance_id=instance.id,
                step_number=step['step_number'],
                assigned_to_employee_id=assignee.get('id')
            )
            self.db.add(history)
            await self.db.commit()
            logger.info(f"Assigned step {step['step_number']} to {assignee.get('id')}")

    async def _resolve_assignee(self, instance: WorkflowInstance, step: dict) -> Optional[dict]:
        result = await self.db.execute(
            select(FormSubmission).where(FormSubmission.id == instance.submission_id)
        )
        submission = result.scalar_one_or_none()
        assignee_type = step.get('assignee_type')

        if assignee_type == 'submitter_manager':
            return await hr_client.get_employee_manager(submission.submitted_by_employee_id)
        elif assignee_type == 'location_gm':
            location = await inventory_client.get_location(submission.location_id)
            if location and location.get('manager_id'):
                return await hr_client.get_employee(location['manager_id'])
        elif assignee_type == 'hr_representative':
            return await hr_client.get_location_hr_rep(submission.location_id)
        elif assignee_type == 'specific_employee':
            return await hr_client.get_employee(step.get('assignee_employee_id'))
        return None

    async def _complete_workflow(self, instance: WorkflowInstance):
        instance.status = WorkflowStatus.COMPLETED
        instance.completed_at = datetime.utcnow()
        result = await self.db.execute(
            select(FormSubmission).where(FormSubmission.id == instance.submission_id)
        )
        submission = result.scalar_one_or_none()
        if submission:
            submission.status = SubmissionStatus.APPROVED
        await self.db.commit()

    async def _handle_rejection(self, instance: WorkflowInstance):
        instance.status = WorkflowStatus.CANCELLED
        instance.completed_at = datetime.utcnow()
        result = await self.db.execute(
            select(FormSubmission).where(FormSubmission.id == instance.submission_id)
        )
        submission = result.scalar_one_or_none()
        if submission:
            submission.status = SubmissionStatus.REJECTED
        await self.db.commit()
```

---

## Docker Configuration

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY templates/ ./templates/
COPY static/ ./static/
COPY form_schemas/ ./form_schemas/

ENV PYTHONPATH=/app/src

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "forms.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  forms-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: forms-service
    restart: unless-stopped
    ports:
      - "8007:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://forms:forms@forms-db:5432/forms
      - DATABASE_URL_SYNC=postgresql://forms:forms@forms-db:5432/forms
      - DEBUG=false
      - TZ=America/New_York
      - PYTHONPATH=/app/src
      - INVENTORY_SERVICE_URL=http://inventory-app:8000
      - HR_SERVICE_URL=http://hr-app:8000
      - HUB_SERVICE_URL=http://integration-hub:8000
      - FILES_SERVICE_URL=http://files-app:8000
      - PORTAL_URL=http://portal-app:8000
      - PORTAL_SECRET_KEY=${PORTAL_SECRET_KEY}
      - BASE_URL=https://rm.swhgrp.com
    depends_on:
      forms-db:
        condition: service_healthy
    networks:
      - restaurant-network
    volumes:
      - ./src:/app/src:ro
      - ./templates:/app/templates:ro
      - ./static:/app/static:ro
      - ./form_schemas:/app/form_schemas:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  forms-db:
    image: postgres:15-alpine
    container_name: forms-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=forms
      - POSTGRES_PASSWORD=forms
      - POSTGRES_DB=forms
      - TZ=America/New_York
    volumes:
      - forms_postgres_data:/var/lib/postgresql/data
    networks:
      - restaurant-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U forms"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  restaurant-network:
    external: true

volumes:
  forms_postgres_data:
```

### requirements.txt

```
# FastAPI
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6

# Database
sqlalchemy==2.0.25
asyncpg==0.29.0
alembic==1.13.1
psycopg2-binary==2.9.9

# Validation
pydantic==2.5.3
pydantic-settings==2.1.0
email-validator==2.1.0

# HTTP client
httpx==0.26.0

# Auth
python-jose[cryptography]==3.3.0
bcrypt==4.1.2

# PDF
weasyprint==60.2
jinja2==3.1.3

# Background tasks
apscheduler==3.10.4

# Utilities
python-dateutil==2.8.2
qrcode[pil]==7.4.2
pillow==10.2.0
json-logic-qubit==0.9.1

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
```

### .env.example

```bash
# Application
DEBUG=false
SECRET_KEY=change-this-to-secure-random-key

# Database
DATABASE_URL=postgresql+asyncpg://forms:forms@forms-db:5432/forms
DATABASE_URL_SYNC=postgresql://forms:forms@forms-db:5432/forms

# Portal SSO
PORTAL_SECRET_KEY=your-portal-secret-key

# Service URLs
INVENTORY_SERVICE_URL=http://inventory-app:8000
HR_SERVICE_URL=http://hr-app:8000
HUB_SERVICE_URL=http://integration-hub:8000
FILES_SERVICE_URL=http://files-app:8000
PORTAL_URL=http://portal-app:8000

# External
BASE_URL=https://rm.swhgrp.com
```

---

## Alembic Configuration

### alembic.ini

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql://forms:forms@localhost:5432/forms

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### alembic/env.py

```python
from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from sqlalchemy.engine import Connection
from alembic import context

import sys
sys.path.insert(0, 'src')
from forms.database import Base
from forms.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.DATABASE_URL_SYNC, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## Nginx Configuration

Add to existing Nginx config:

```nginx
# Forms Service
location /forms/ {
    proxy_pass http://forms-service:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Longer timeout for PDF generation
    proxy_read_timeout 120s;
    proxy_connect_timeout 120s;
}
```

---

## Form Templates to Create

**HR & Employment:**
1. Exit Interview
2. Performance Review/Evaluation
3. Verbal Warning Documentation
4. Written Warning Acknowledgment
5. Final Written Warning
6. Suspension Notice
7. Training Completion Acknowledgment
8. Corrective/Disciplinary Action

**Safety & Compliance:**
9. First Report of Injury/Illness
10. Incident Report (general)
11. Witness Statement
12. Food Allergy Incident Report
13. Slip/Trip/Fall Report
14. Return to Work/Fitness for Duty
15. Workers' Comp Follow-up
16. Hazard Identification Report
17. Near-Miss Report
18. Safety Committee Meeting Notes

**Operations:**
19. Cash Handling Discrepancy
20. Register Over/Short Documentation
21. Customer Complaint Log
22. Property Damage Report
23. Tip Distribution Acknowledgment
24. Manager on Duty Log
25. Equipment Malfunction Report
26. Vendor Delivery Issue Report

---

## Example Form Schema

### form_schemas/first-report-of-injury/schema.json

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["injury_date", "injury_time", "location_id", "body_part", "injury_type", "description"],
  "properties": {
    "injury_date": {
      "type": "string",
      "format": "date",
      "title": "Date of Injury/Illness"
    },
    "injury_time": {
      "type": "string",
      "format": "time",
      "title": "Time of Injury/Illness"
    },
    "location_id": {
      "type": "integer",
      "title": "Location"
    },
    "specific_location": {
      "type": "string",
      "title": "Specific Location (e.g., kitchen, walk-in, dining room)",
      "maxLength": 255
    },
    "body_part": {
      "type": "string",
      "title": "Body Part Affected",
      "enum": ["head", "neck", "shoulder", "arm", "elbow", "wrist", "hand", "finger", "back_upper", "back_lower", "chest", "abdomen", "hip", "leg", "knee", "ankle", "foot", "toe", "multiple", "other"]
    },
    "body_part_other": {
      "type": "string",
      "title": "Other Body Part",
      "maxLength": 100
    },
    "injury_type": {
      "type": "string",
      "title": "Type of Injury/Illness",
      "enum": ["cut_laceration", "burn", "sprain_strain", "fracture", "contusion", "slip_fall", "repetitive_motion", "chemical_exposure", "allergic_reaction", "food_illness", "other"]
    },
    "injury_type_other": {
      "type": "string",
      "title": "Other Injury Type",
      "maxLength": 100
    },
    "description": {
      "type": "string",
      "title": "Describe how the injury/illness occurred",
      "maxLength": 2000
    },
    "task_at_time": {
      "type": "string",
      "title": "What task was the employee performing?",
      "maxLength": 500
    },
    "equipment_involved": {
      "type": "string",
      "title": "Equipment/materials involved",
      "maxLength": 500
    },
    "witnesses": {
      "type": "array",
      "title": "Witnesses",
      "items": {
        "type": "object",
        "properties": {
          "employee_id": {"type": "integer"},
          "name": {"type": "string"},
          "statement_attached": {"type": "boolean"}
        }
      }
    },
    "treatment_given": {
      "type": "string",
      "title": "First Aid/Treatment Given",
      "enum": ["none", "first_aid_onsite", "clinic_visit", "er_visit", "hospitalized"]
    },
    "treatment_description": {
      "type": "string",
      "title": "Describe treatment provided",
      "maxLength": 1000
    },
    "medical_provider": {
      "type": "string",
      "title": "Medical Provider/Facility Name",
      "maxLength": 255
    },
    "returned_to_work": {
      "type": "boolean",
      "title": "Did employee return to work same day?"
    },
    "work_restrictions": {
      "type": "boolean",
      "title": "Are there work restrictions?"
    },
    "restriction_details": {
      "type": "string",
      "title": "Describe restrictions",
      "maxLength": 1000
    },
    "osha_recordable": {
      "type": "boolean",
      "title": "Is this OSHA recordable?"
    },
    "osha_classification": {
      "type": "string",
      "title": "OSHA Classification",
      "enum": ["death", "days_away", "restricted_duty", "medical_treatment", "other_recordable"]
    },
    "days_away_from_work": {
      "type": "integer",
      "title": "Days Away From Work",
      "minimum": 0
    },
    "days_restricted_duty": {
      "type": "integer",
      "title": "Days on Restricted Duty",
      "minimum": 0
    },
    "supervisor_notified": {
      "type": "boolean",
      "title": "Was supervisor notified immediately?"
    },
    "supervisor_name": {
      "type": "string",
      "title": "Supervisor Name",
      "maxLength": 255
    },
    "corrective_actions": {
      "type": "string",
      "title": "Corrective actions taken or recommended",
      "maxLength": 2000
    },
    "additional_notes": {
      "type": "string",
      "title": "Additional Notes",
      "maxLength": 2000
    }
  }
}
```

### form_schemas/first-report-of-injury/ui_schema.json

```json
{
  "ui:order": [
    "injury_date", "injury_time", "location_id", "specific_location",
    "body_part", "body_part_other", "injury_type", "injury_type_other",
    "description", "task_at_time", "equipment_involved", "witnesses",
    "treatment_given", "treatment_description", "medical_provider",
    "returned_to_work", "work_restrictions", "restriction_details",
    "osha_recordable", "osha_classification", "days_away_from_work", "days_restricted_duty",
    "supervisor_notified", "supervisor_name", "corrective_actions", "additional_notes"
  ],
  "ui:sections": [
    {"title": "Incident Information", "fields": ["injury_date", "injury_time", "location_id", "specific_location"]},
    {"title": "Injury Details", "fields": ["body_part", "body_part_other", "injury_type", "injury_type_other", "description", "task_at_time", "equipment_involved"]},
    {"title": "Witnesses", "fields": ["witnesses"]},
    {"title": "Treatment", "fields": ["treatment_given", "treatment_description", "medical_provider"]},
    {"title": "Return to Work", "fields": ["returned_to_work", "work_restrictions", "restriction_details"]},
    {"title": "OSHA Recording", "fields": ["osha_recordable", "osha_classification", "days_away_from_work", "days_restricted_duty"]},
    {"title": "Follow-up", "fields": ["supervisor_notified", "supervisor_name", "corrective_actions", "additional_notes"]}
  ],
  "location_id": {"ui:widget": "LocationSelect"},
  "witnesses": {"items": {"employee_id": {"ui:widget": "EmployeeSelect"}}},
  "description": {"ui:widget": "textarea", "ui:options": {"rows": 4}},
  "corrective_actions": {"ui:widget": "textarea", "ui:options": {"rows": 4}},
  "body_part_other": {"ui:hidden": {"unless": {"body_part": "other"}}},
  "injury_type_other": {"ui:hidden": {"unless": {"injury_type": "other"}}},
  "restriction_details": {"ui:hidden": {"unless": {"work_restrictions": true}}},
  "osha_classification": {"ui:hidden": {"unless": {"osha_recordable": true}}},
  "days_away_from_work": {"ui:hidden": {"unless": {"osha_classification": ["days_away"]}}},
  "days_restricted_duty": {"ui:hidden": {"unless": {"osha_classification": ["restricted_duty"]}}}
}
```

---

## Implementation Order

1. **Phase 1: Core Infrastructure**
   - Database models and migrations
   - Basic CRUD for templates and submissions
   - Portal SSO authentication
   - Health check endpoint

2. **Phase 2: Signatures & PDF**
   - Signature capture widget
   - Signature storage and validation
   - PDF generation with WeasyPrint

3. **Phase 3: Workflows**
   - Workflow engine
   - APScheduler tasks
   - Notification service

4. **Phase 4: Dashboard & Reports**
   - Dashboard metrics
   - OSHA reporting
   - Export functionality

5. **Phase 5: Form Schemas**
   - Create all 26 form schemas
   - Print templates

---

## Testing Requirements

- Unit tests for all API endpoints
- Integration tests for workflow engine
- Test signature validation
- Test PDF generation
- Minimum 80% code coverage
