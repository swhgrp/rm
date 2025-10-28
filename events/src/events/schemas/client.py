"""Client and venue schemas"""
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime


class ClientBase(BaseModel):
    """Base client schema"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = None
    org: Optional[str] = None
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    """Schema for creating client"""
    pass


class ClientResponse(ClientBase):
    """Schema for client response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
