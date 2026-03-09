"""
E-Signature model for tracking signature requests (self-hosted)
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from hr.db.database import Base


class SignatureRequest(Base):
    """Track signature requests for self-hosted e-signing"""
    __tablename__ = "signature_requests"

    id = Column(Integer, primary_key=True, index=True)

    # Legacy Dropbox Sign identifier (kept for history, no longer used)
    dropbox_signature_request_id = Column(String(100), unique=True, nullable=True, index=True)

    # Self-hosted signing token
    signing_token = Column(String(128), unique=True, nullable=True, index=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Link to employee
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

    # Link to template used
    template_id = Column(Integer, ForeignKey("signature_templates.id", ondelete="SET NULL"), nullable=True)

    # Document info
    document_title = Column(String(255), nullable=False)
    document_type = Column(String(100), nullable=False)
    original_file_path = Column(String(500), nullable=True)

    # Status tracking
    status = Column(String(50), default="pending")  # pending, sent, viewed, signed, declined, cancelled

    # Signer info
    signer_email = Column(String(255), nullable=False)
    signer_name = Column(String(255), nullable=False)

    # Signing audit data
    signer_ip = Column(String(45), nullable=True)
    signer_user_agent = Column(Text, nullable=True)
    document_hash = Column(String(64), nullable=True)  # SHA-256 of original PDF
    signed_document_hash = Column(String(64), nullable=True)  # SHA-256 of signed PDF
    signing_data = Column(JSON, nullable=True)  # signature image, typed name, field values

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(Integer, nullable=True)

    # Signed document storage
    signed_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Created by
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Additional metadata
    request_metadata = Column(JSON, nullable=True)

    # Relationships
    employee = relationship("Employee", backref="signature_requests")
    template = relationship("SignatureTemplate", foreign_keys=[template_id])
    signed_document = relationship("Document", foreign_keys=[signed_document_id])
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<SignatureRequest {self.document_title} for Employee {self.employee_id} - {self.status}>"


class SignatureTemplate(Base):
    """Store reusable signature templates"""
    __tablename__ = "signature_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Legacy Dropbox Sign template ID (kept for history)
    dropbox_template_id = Column(String(100), unique=True, nullable=True)

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    document_type = Column(String(100), nullable=False)

    # Configuration
    is_active = Column(Boolean, default=True)

    # File reference (local PDF template)
    template_file_path = Column(String(500), nullable=True)

    # Signature field positions (JSON array)
    # [{"name": "employee_signature", "page": 1, "x": 100, "y": 500, "type": "signature", "width": 150, "height": 40}, ...]
    signature_fields = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Created by
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<SignatureTemplate {self.name}>"
