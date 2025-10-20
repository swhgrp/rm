"""
Role schemas for user management
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from accounting.schemas.permission import PermissionInRole


class AreaInRole(BaseModel):
    """Simplified area info for role responses"""
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    area_ids: Optional[List[int]] = []
    permission_ids: Optional[List[int]] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    area_ids: Optional[List[int]] = None
    permission_ids: Optional[List[int]] = None


class RoleResponse(RoleBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    areas: List[AreaInRole] = []
    permissions: List[PermissionInRole] = []

    class Config:
        from_attributes = True
