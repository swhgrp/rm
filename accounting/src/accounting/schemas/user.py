"""
User schemas for authentication
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class RoleInUser(BaseModel):
    """Simplified role info for user responses"""
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str
    is_admin: bool = False
    role_id: Optional[int] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role_id: Optional[int] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    role_id: Optional[int] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    role: Optional[RoleInUser] = None

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserResponse
    message: str = "Login successful"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
