"""
Upload Job model - Tracks async invoice upload processing
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from integration_hub.db.database import Base
import enum


class UploadJobStatus(str, enum.Enum):
    """Status values for upload jobs"""
    PENDING = "pending"           # Job created, waiting to start
    PROCESSING = "processing"     # Currently parsing PDF
    COMPLETED = "completed"       # Successfully parsed, ready for review
    FAILED = "failed"             # Parsing failed


class UploadJob(Base):
    """Tracks async invoice upload and parsing jobs"""
    __tablename__ = "upload_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Job identification
    job_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID

    # File information
    original_filename = Column(String(500), nullable=False)
    pdf_path = Column(String(1000), nullable=False)

    # Processing status
    status = Column(String(20), default=UploadJobStatus.PENDING.value, nullable=False, index=True)
    progress_message = Column(String(500), nullable=True)  # Current step description
    progress_percent = Column(Integer, default=0)  # 0-100

    # Results (populated on completion)
    parsed_data = Column(JSON, nullable=True)  # Full parsed invoice data
    error_message = Column(Text, nullable=True)  # Error details if failed

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<UploadJob(id={self.id}, job_id={self.job_id}, status={self.status})>"
