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


class ClientUpdate(BaseModel):
    """Schema for updating client - all fields optional"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    org: Optional[str] = None
    notes: Optional[str] = None


class ClientResponse(ClientBase):
    """Schema for client response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    event_count: Optional[int] = None
