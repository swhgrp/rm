"""
Database models for HR Management System
"""

from hr.models.employee import Employee, employee_locations
from hr.models.position import Position
from hr.models.employee_position import EmployeePosition
from hr.models.document import Document
from hr.models.user import User, user_locations
from hr.models.location import Location
from hr.models.department import Department
from hr.models.role import Role
from hr.models.permission import Permission
from hr.models.role_permission import RolePermission
from hr.models.user_role import UserRole
from hr.models.settings import SystemSettings
from hr.models.esignature import SignatureRequest, SignatureTemplate
from hr.models.hr_forms import (
    CorrectiveAction, FirstReportOfInjury,
    DisciplinaryLevel, FinalWarningType, CorrectiveActionSubject,
    FormStatus, InjuryBodyPart, InjuryType
)

__all__ = [
    "Employee",
    "employee_locations",
    "Position",
    "EmployeePosition",
    "Document",
    "User",
    "user_locations",
    "Location",
    "Department",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "SystemSettings",
    "SignatureRequest",
    "SignatureTemplate",
    "CorrectiveAction",
    "FirstReportOfInjury",
    "DisciplinaryLevel",
    "FinalWarningType",
    "CorrectiveActionSubject",
    "FormStatus",
    "InjuryBodyPart",
    "InjuryType"
]
