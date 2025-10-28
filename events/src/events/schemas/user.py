"""User and role schemas"""
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import List, Optional
from uuid import UUID
from datetime import datetime


class RoleResponse(BaseModel):
    """Schema for role response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    full_name: str
    department: Optional[str] = None


class UserResponse(UserBase):
    """Schema for user response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    source: str
    roles: List[RoleResponse] = []
    created_at: datetime
