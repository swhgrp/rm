"""
Pydantic schemas for authentication
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserResponse(BaseModel):
    """User response schema"""
    id: int
    username: str
    email: str
    full_name: str
    is_admin: bool
    is_active: bool
    nextcloud_username: Optional[str] = None
    has_nextcloud_credentials: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NextcloudCredentialsSetup(BaseModel):
    """Schema for setting up Nextcloud credentials"""
    nextcloud_username: str
    nextcloud_password: str


class NextcloudCredentialsUpdate(BaseModel):
    """Schema for updating Nextcloud credentials"""
    nextcloud_username: Optional[str] = None
    nextcloud_password: Optional[str] = None


class SetupResponse(BaseModel):
    """Response after credential setup"""
    success: bool
    message: str
    nextcloud_username: Optional[str] = None
