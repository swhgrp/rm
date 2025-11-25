"""Email schemas"""
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class EmailListResponse(BaseModel):
    """Schema for email list (without body for performance)"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: Optional[UUID]
    to_list: List[str]
    cc_list: Optional[List[str]]
    subject: str
    status: str
    sent_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


class EmailResponse(BaseModel):
    """Schema for full email response (with body)"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: Optional[UUID]
    to_list: List[str]
    cc_list: Optional[List[str]]
    subject: str
    body_html: str
    status: str
    sent_at: Optional[datetime]
    provider_message_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
