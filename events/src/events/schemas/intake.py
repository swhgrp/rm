"""Public intake form schemas"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime


class IntakeClientData(BaseModel):
    """Client data from intake form"""
    name: str = Field(..., min_length=1)
    email: EmailStr
    phone: Optional[str] = None
    org: Optional[str] = None


class IntakeEventData(BaseModel):
    """Event data from intake form"""
    title: str = Field(..., min_length=1)
    event_type: str
    date: str  # Date string from form
    start_at: datetime
    end_at: datetime
    guest_count: Optional[int] = None
    venue_id: str  # UUID as string
    setup_start_at: Optional[datetime] = None
    teardown_end_at: Optional[datetime] = None
    menu_json: Optional[Dict[str, Any]] = None
    requirements_json: Optional[Dict[str, Any]] = None
    budget_estimate: Optional[float] = None


class PublicIntakeRequest(BaseModel):
    """Schema for public BEO intake request"""
    hcaptcha_token: str = Field(..., description="hCaptcha verification token")
    eventTemplateKey: str = Field(..., description="Template key (e.g., 'wedding_standard')")
    client: IntakeClientData
    event: IntakeEventData


class PublicIntakeResponse(BaseModel):
    """Schema for intake response"""
    success: bool
    event_id: str
    message: str
    reference_number: Optional[str] = None
