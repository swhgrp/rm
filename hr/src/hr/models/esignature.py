"""
E-Signature model for tracking Dropbox Sign signature requests
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from hr.db.database import Base


class SignatureRequest(Base):
    """Track signature requests sent via Dropbox Sign"""
    __tablename__ = "signature_requests"

    id = Column(Integer, primary_key=True, index=True)

    # Dropbox Sign identifiers
    dropbox_signature_request_id = Column(String(100), unique=True, nullable=False, index=True)

    # Link to employee
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

    # Document info
    document_title = Column(String(255), nullable=False)
    document_type = Column(String(100), nullable=False)  # "new_hire_packet", "policy_update", etc.

    # Status tracking
    status = Column(String(50), default="pending")  # pending, sent, viewed, signed, declined, cancelled

    # Signer info
    signer_email = Column(String(255), nullable=False)
    signer_name = Column(String(255), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)

    # Signed document storage
    signed_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Created by
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Additional metadata (renamed from 'metadata' which is reserved in SQLAlchemy)
    request_metadata = Column(JSON, nullable=True)  # Store template fields, custom data

    # Relationships
    employee = relationship("Employee", backref="signature_requests")
    signed_document = relationship("Document", foreign_keys=[signed_document_id])
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<SignatureRequest {self.document_title} for Employee {self.employee_id} - {self.status}>"


class SignatureTemplate(Base):
    """Store reusable signature templates"""
    __tablename__ = "signature_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Dropbox Sign template ID
    dropbox_template_id = Column(String(100), unique=True, nullable=True)

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    document_type = Column(String(100), nullable=False)  # "new_hire_packet", "handbook", etc.

    # Configuration
    is_active = Column(Boolean, default=True)

    # File reference (local PDF template)
    template_file_path = Column(String(500), nullable=True)

    # Signature field positions (JSON array)
    # [{"name": "employee_signature", "page": 1, "x": 100, "y": 500, "type": "signature"}, ...]
    signature_fields = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Created by
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<SignatureTemplate {self.name}>"
