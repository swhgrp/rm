"""Email schemas"""
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class EmailResponse(BaseModel):
    """Schema for email response"""
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
