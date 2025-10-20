"""
Pydantic schemas for document management
"""

from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class DocumentBase(BaseModel):
    document_type: str
    file_name: str
    expiration_date: Optional[date] = None
    notes: Optional[str] = None


class DocumentCreate(DocumentBase):
    employee_id: int
    file_path: str
    file_size: int
    mime_type: str


class DocumentUpdate(BaseModel):
    document_type: Optional[str] = None
    expiration_date: Optional[date] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class Document(DocumentBase):
    id: int
    employee_id: int
    file_path: str
    file_size: int
    mime_type: str
    uploaded_by: Optional[int] = None
    uploaded_at: datetime
    status: str

    class Config:
        from_attributes = True


class DocumentWithEmployee(Document):
    """Document with employee information included"""
    employee_name: str
    employee_number: str

    class Config:
        from_attributes = True


# Document type constants for restaurant HR
DOCUMENT_TYPES = [
    "Food Handler Certificate",
    "Food Manager Certificate",
    "Alcohol Server Permit",
    "TIPS Certification",
    "Background Check",
    "Drug Test Results",
    "ID Copy",
    "Social Security Card",
    "Performance Review",
    "Written Warning",
    "Performance Improvement Plan",
    "Employee Handbook Acknowledgment",
    "Other"
]
