"""Document and email models"""
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class DocumentType(str, enum.Enum):
    """Document type enum"""
    BEO = "beo"
    SUMMARY = "summary"
    INVOICE = "invoice"
    OTHER = "other"


class Document(BaseModel):
    """Document model"""
    __tablename__ = "documents"

    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True)
    doc_type = Column(SQLEnum(DocumentType), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    storage_url = Column(Text, nullable=False)  # S3 URL
    render_params_json = Column(JSONB, nullable=True)  # Parameters used to render this document
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # Relationships
    event = relationship("Event", back_populates="documents")

    def __repr__(self):
        return f"<Document(id={self.id}, doc_type={self.doc_type}, version={self.version})>"


class EmailStatus(str, enum.Enum):
    """Email status enum"""
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class Email(BaseModel):
    """Email model"""
    __tablename__ = "emails"

    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete='CASCADE'), nullable=True, index=True)
    to_list = Column(JSONB, nullable=False)  # ["email1@example.com", "email2@example.com"]
    cc_list = Column(JSONB, nullable=True)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    status = Column(SQLEnum(EmailStatus), default=EmailStatus.QUEUED, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    event = relationship("Event", back_populates="emails")

    def __repr__(self):
        return f"<Email(id={self.id}, subject={self.subject}, status={self.status})>"
