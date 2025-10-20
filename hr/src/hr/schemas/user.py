"""
Schemas for HR user management and authentication
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List


class RoleInUser(BaseModel):
    """Simplified role info for user responses"""
    id: int
    name: str

    class Config:
        from_attributes = True


class LocationInUser(BaseModel):
    """Simplified location info for user responses"""
    id: int
    name: str

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)
    is_admin: bool = False


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role_id: Optional[int] = None
    location_ids: Optional[List[int]] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=100)


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    roles: List[RoleInUser] = []
    assigned_locations: List[LocationInUser] = []

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user: UserResponse
    message: str = "Login successful"


class ChangePasswordRequest(BaseModel):
    """Request to change user password"""
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=100)
