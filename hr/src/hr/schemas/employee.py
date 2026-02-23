"""
Pydantic schemas for Employee model
"""

from pydantic import BaseModel, EmailStr
from datetime import date
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from hr.schemas.location import LocationResponse


class EmployeeBase(BaseModel):
    """Base Employee schema with common fields"""
    employee_number: str
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

    # Address
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    # Emergency Contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None

    # Employment
    hire_date: Optional[date] = None
    employment_status: str = "Active"
    employee_type: str = "Part-Time"
    starting_pay_rate: Optional[Decimal] = None
    position_id: Optional[int] = None  # Optional for existing employees

    # Termination Details
    termination_type: Optional[str] = None  # "Voluntary" or "Involuntary"
    termination_reason: Optional[str] = None
    final_decision_date: Optional[date] = None
    authorized_by: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    """Schema for creating a new employee"""
    # Override optional fields to make them required for new employees
    date_of_birth: date
    phone_number: str
    street_address: str
    city: str
    state: str
    zip_code: str
    position_id: int  # Required for new hires

    location_ids: Optional[List[int]] = []  # List of location IDs to assign
    create_inventory_user: bool = False  # For Phase 5 integration


class EmployeeUpdate(BaseModel):
    """Schema for updating an employee (all fields optional)"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None

    hire_date: Optional[date] = None
    employment_status: Optional[str] = None
    employee_type: Optional[str] = None
    starting_pay_rate: Optional[Decimal] = None
    position_id: Optional[int] = None
    termination_date: Optional[date] = None

    # Termination Details
    termination_type: Optional[str] = None
    termination_reason: Optional[str] = None
    final_decision_date: Optional[date] = None
    authorized_by: Optional[str] = None

    # Location assignments
    location_ids: Optional[List[int]] = None


class Employee(EmployeeBase):
    """Schema for returning employee data (includes ID and dates)"""
    id: int
    termination_date: Optional[date] = None
    inventory_user_id: Optional[int] = None
    clover_employee_id: Optional[str] = None
    assigned_locations: List['LocationResponse'] = []

    class Config:
        from_attributes = True


# Import LocationResponse to resolve forward reference
from hr.schemas.location import LocationResponse
Employee.model_rebuild()
