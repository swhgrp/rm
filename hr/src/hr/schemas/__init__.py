"""
Pydantic schemas for HR Management System
"""

from hr.schemas.position import Position, PositionCreate, PositionUpdate
from hr.schemas.employee import Employee, EmployeeCreate, EmployeeUpdate
from hr.schemas.role import (
    RoleBase, RoleCreate, RoleUpdate, RoleResponse, RoleWithPermissions,
    PermissionBase, PermissionResponse,
    UserRoleAssignment, UserRoleResponse
)
from hr.schemas.location import (
    LocationBase, LocationCreate, LocationUpdate, LocationResponse,
    UserLocationAssignment, UserLocationResponse
)

__all__ = [
    "Position", "PositionCreate", "PositionUpdate",
    "Employee", "EmployeeCreate", "EmployeeUpdate",
    "RoleBase", "RoleCreate", "RoleUpdate", "RoleResponse", "RoleWithPermissions",
    "PermissionBase", "PermissionResponse",
    "UserRoleAssignment", "UserRoleResponse",
    "LocationBase", "LocationCreate", "LocationUpdate", "LocationResponse",
    "UserLocationAssignment", "UserLocationResponse"
]
