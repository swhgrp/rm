"""Event Template schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class EventTemplateBase(BaseModel):
    """Base event template schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Template identifier (e.g., 'wedding_standard')")
    event_type: str = Field(..., min_length=1, max_length=100, description="Event type (e.g., 'Wedding', 'Corporate Event')")
    form_schema_json: Optional[Dict[str, Any]] = Field(None, description="Custom form fields for intake")
    default_tasks_json: Optional[Dict[str, Any]] = Field(None, description="Task definitions with checklist items")
    default_menu_json: Optional[Dict[str, Any]] = Field(None, description="Default menu structure")
    default_financials_json: Optional[Dict[str, Any]] = Field(None, description="Default pricing (base_price, per_guest, deposit_percent, tax_rate)")
    email_rules_json: Optional[Dict[str, Any]] = Field(None, description="Email notification rules (on_created, on_confirmed, etc.)")
    doc_templates_json: Optional[Dict[str, Any]] = Field(None, description="Document template keys")


class EventTemplateCreate(EventTemplateBase):
    """Schema for creating event template"""
    pass


class EventTemplateUpdate(BaseModel):
    """Schema for updating event template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    event_type: Optional[str] = Field(None, min_length=1, max_length=100)
    form_schema_json: Optional[Dict[str, Any]] = None
    default_tasks_json: Optional[Dict[str, Any]] = None
    default_menu_json: Optional[Dict[str, Any]] = None
    default_financials_json: Optional[Dict[str, Any]] = None
    email_rules_json: Optional[Dict[str, Any]] = None
    doc_templates_json: Optional[Dict[str, Any]] = None


class EventTemplateResponse(EventTemplateBase):
    """Schema for event template response"""
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None

    class Config:
        from_attributes = True
