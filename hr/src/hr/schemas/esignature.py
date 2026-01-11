"""
Pydantic schemas for E-Signature functionality
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr


# ============ Signature Request Schemas ============

class SignatureRequestCreate(BaseModel):
    """Create a new signature request"""
    employee_id: int
    document_type: str  # "new_hire_packet", "policy_update", etc.
    template_id: Optional[int] = None  # Use stored template
    custom_message: Optional[str] = None  # Custom email message


class SignatureRequestResponse(BaseModel):
    """Signature request response"""
    id: int
    dropbox_signature_request_id: str
    employee_id: int
    document_title: str
    document_type: str
    status: str
    signer_email: str
    signer_name: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    signed_document_id: Optional[int] = None
    created_by: Optional[int] = None

    class Config:
        from_attributes = True


class SignatureRequestWithEmployee(SignatureRequestResponse):
    """Signature request with employee details"""
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None


class SignatureRequestList(BaseModel):
    """List of signature requests"""
    items: List[SignatureRequestResponse]
    total: int


# ============ Signature Template Schemas ============

class SignatureFieldPosition(BaseModel):
    """Position of a signature field in a document"""
    name: str  # Field identifier
    page: int  # Page number (1-indexed)
    x: int  # X position
    y: int  # Y position
    width: Optional[int] = 150
    height: Optional[int] = 30
    field_type: str = "signature"  # signature, initials, date, text


class SignatureTemplateCreate(BaseModel):
    """Create a new signature template"""
    name: str
    description: Optional[str] = None
    document_type: str
    dropbox_template_id: Optional[str] = None
    signature_fields: Optional[List[SignatureFieldPosition]] = None


class SignatureTemplateUpdate(BaseModel):
    """Update a signature template"""
    name: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    dropbox_template_id: Optional[str] = None
    is_active: Optional[bool] = None
    signature_fields: Optional[List[SignatureFieldPosition]] = None


class SignatureTemplateResponse(BaseModel):
    """Signature template response"""
    id: int
    name: str
    description: Optional[str] = None
    document_type: str
    dropbox_template_id: Optional[str] = None
    is_active: bool
    template_file_path: Optional[str] = None
    signature_fields: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ Webhook Schemas ============

class DropboxSignWebhookEvent(BaseModel):
    """Dropbox Sign webhook event"""
    event: Dict[str, Any]


class SignatureEventData(BaseModel):
    """Parsed signature event data"""
    event_type: str  # signature_request_sent, signature_request_viewed, signature_request_signed, etc.
    signature_request_id: str
    signer_email: Optional[str] = None
    event_time: Optional[datetime] = None


# ============ Send Request Schemas ============

class SendSignatureRequest(BaseModel):
    """Request to send a document for signature"""
    employee_id: int
    template_id: Optional[int] = None
    document_type: str = "new_hire_packet"
    title: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None


class SendSignatureResponse(BaseModel):
    """Response after sending signature request"""
    success: bool
    signature_request_id: Optional[int] = None
    dropbox_signature_request_id: Optional[str] = None
    message: str
    signing_url: Optional[str] = None  # For embedded signing (if needed later)
