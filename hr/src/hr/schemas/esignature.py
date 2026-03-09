"""
Pydantic schemas for E-Signature functionality (self-hosted)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr


# ============ Signature Request Schemas ============

class SignatureRequestCreate(BaseModel):
    """Create a new signature request"""
    employee_id: int
    document_type: str  # "new_hire_packet", "policy_update", etc.
    template_id: Optional[int] = None
    custom_message: Optional[str] = None


class SignatureRequestResponse(BaseModel):
    """Signature request response"""
    id: int
    employee_id: int
    document_title: str
    document_type: str
    status: str
    signer_email: str
    signer_name: str
    signing_token: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    signed_document_id: Optional[int] = None
    created_by: Optional[int] = None
    signer_ip: Optional[str] = None
    signer_user_agent: Optional[str] = None
    document_hash: Optional[str] = None
    signed_document_hash: Optional[str] = None

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
    name: str
    page: int  # 1-indexed
    x: int
    y: int
    width: Optional[int] = 150
    height: Optional[int] = 30
    field_type: str = "signature"  # signature, initials, date, text, name


class SignatureTemplateCreate(BaseModel):
    """Create a new signature template"""
    name: str
    description: Optional[str] = None
    document_type: str
    signature_fields: Optional[List[SignatureFieldPosition]] = None


class SignatureTemplateUpdate(BaseModel):
    """Update a signature template"""
    name: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    is_active: Optional[bool] = None
    signature_fields: Optional[List[SignatureFieldPosition]] = None


class SignatureTemplateResponse(BaseModel):
    """Signature template response"""
    id: int
    name: str
    description: Optional[str] = None
    document_type: str
    is_active: bool
    template_file_path: Optional[str] = None
    signature_fields: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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
    signing_url: Optional[str] = None
    message: str


# ============ Signing Submission Schema ============

class SigningSubmission(BaseModel):
    """Data submitted when signer completes signing"""
    signature_image: str  # base64 encoded PNG from canvas
    typed_name: str
    field_values: Optional[Dict[str, Any]] = None  # field_name -> value
    agreed_to_terms: bool = False
