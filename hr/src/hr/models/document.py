"""
Document model for employee file management
"""

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from hr.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

    # Document Info
    document_type = Column(String, nullable=False, index=True)  # I-9, W-4, Contract, Certification, etc.
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_size = Column(Integer)  # bytes
    mime_type = Column(String)

    # Metadata
    uploaded_by = Column(Integer, nullable=True)  # User ID who uploaded
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Expiration Tracking
    expiration_date = Column(Date, nullable=True)
    status = Column(String, default="Current")  # Current, Expiring Soon, Expired, Archived

    # Notes
    notes = Column(Text, nullable=True)

    # Relationship
    employee = relationship("Employee", backref="documents")

    def __repr__(self):
        return f"<Document {self.file_name} ({self.document_type}) for Employee {self.employee_id}>"
