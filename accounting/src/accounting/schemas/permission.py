"""
Permission schemas for access control
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class PermissionBase(BaseModel):
    module: str = Field(..., min_length=1, max_length=50, description="Module name (e.g., 'general_ledger')")
    action: str = Field(..., min_length=1, max_length=20, description="Action (e.g., 'view', 'create', 'edit')")
    name: str = Field(..., min_length=1, max_length=100, description="Permission name (e.g., 'general_ledger:view')")
    description: Optional[str] = None


class PermissionResponse(PermissionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PermissionInRole(BaseModel):
    """Simplified permission info for role responses"""
    id: int
    module: str
    action: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
