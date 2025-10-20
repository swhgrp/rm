"""
Pydantic schemas for Department model
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DepartmentBase(BaseModel):
    """Base Department schema"""
    name: str
    description: Optional[str] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    """Schema for creating a new department"""
    pass


class DepartmentUpdate(BaseModel):
    """Schema for updating a department (all fields optional)"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class Department(DepartmentBase):
    """Schema for returning department data"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
