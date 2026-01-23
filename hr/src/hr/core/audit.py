"""
Audit logging utilities for tracking sensitive data access
"""

from sqlalchemy.orm import Session
from typing import Optional, List, Set
from hr.models.audit_log import AuditLog
from fastapi import Request


# Sensitive fields that should be audited
SENSITIVE_FIELDS = {
    "phone_number",
    "street_address",
    "city",
    "state",
    "zip_code",
    "emergency_contact_name",
    "emergency_contact_phone",
    "emergency_contact_relationship",
    "date_of_birth",
}


def format_field_name(field_name: str) -> str:
    """
    Format a field name for human-readable display.
    Converts snake_case to Title Case.

    Examples:
        street_address -> Street Address
        phone_number -> Phone Number
        date_of_birth -> Date of Birth
    """
    return field_name.replace("_", " ").title()


def format_field_list(fields: List[str]) -> str:
    """
    Format a list of field names for display.

    Examples:
        ["street_address", "phone_number"] -> "Street Address, Phone Number"
    """
    return ", ".join(format_field_name(f) for f in fields)


def log_sensitive_access(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    field_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    request: Optional[Request] = None,
    notes: Optional[str] = None
):
    """
    Log access to sensitive employee data.

    Args:
        db: Database session
        entity_type: Type of entity (e.g., "employee")
        entity_id: ID of the entity
        action: Action performed ("view", "create", "update", "delete")
        user_id: ID of user performing action
        username: Username of user performing action
        field_name: Specific field accessed (for sensitive fields)
        old_value: Previous value (for updates) - will be masked in log
        new_value: New value (for creates/updates) - will be masked in log
        request: FastAPI request object for IP and user agent
        notes: Additional notes
    """
    # Extract IP and user agent from request if provided
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    # Mask values if they're sensitive - only log that they were changed, not the actual values
    masked_old = "***REDACTED***" if old_value else None
    masked_new = "***REDACTED***" if new_value else None

    audit_entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        field_name=field_name,
        user_id=user_id,
        username=username,
        timestamp=None,  # Will use server default
        ip_address=ip_address,
        user_agent=user_agent,
        old_value=masked_old,
        new_value=masked_new,
        notes=notes
    )

    db.add(audit_entry)
    db.commit()


def log_employee_view(
    db: Session,
    employee_id: int,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None,
    viewed_sensitive_fields: bool = False,
    sensitive_fields_accessed: Optional[List[str]] = None
):
    """
    Log when an employee record is viewed.

    Args:
        db: Database session
        employee_id: ID of employee viewed
        user_id: ID of user viewing
        username: Username of user viewing
        request: FastAPI request object
        viewed_sensitive_fields: Whether sensitive fields were accessed
        sensitive_fields_accessed: List of specific sensitive field names that were viewed
    """
    if sensitive_fields_accessed:
        # Log specific fields that were viewed
        fields_display = format_field_list(sensitive_fields_accessed)
        notes = f"Viewed: {fields_display}"
    elif viewed_sensitive_fields:
        notes = "Viewed sensitive fields"
    else:
        notes = "Viewed basic info"

    log_sensitive_access(
        db=db,
        entity_type="employee",
        entity_id=employee_id,
        action="view",
        user_id=user_id,
        username=username,
        request=request,
        notes=notes
    )


def log_employee_update(
    db: Session,
    employee_id: int,
    updated_fields: dict,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None
):
    """
    Log when an employee record is updated.

    Args:
        db: Database session
        employee_id: ID of employee updated
        updated_fields: Dictionary of fields that were updated
        user_id: ID of user updating
        username: Username of user updating
        request: FastAPI request object
    """
    # Check if any sensitive fields were updated
    sensitive_updated = set(updated_fields.keys()) & SENSITIVE_FIELDS

    if sensitive_updated:
        # Log each sensitive field update separately with formatted name
        for field in sensitive_updated:
            formatted_name = format_field_name(field)
            log_sensitive_access(
                db=db,
                entity_type="employee",
                entity_id=employee_id,
                action="update",
                field_name=formatted_name,
                user_id=user_id,
                username=username,
                old_value="changed",
                new_value="changed",
                request=request,
                notes=f"Updated: {formatted_name}"
            )
    else:
        # Log general update with formatted field names
        formatted_fields = format_field_list(list(updated_fields.keys()))
        log_sensitive_access(
            db=db,
            entity_type="employee",
            entity_id=employee_id,
            action="update",
            user_id=user_id,
            username=username,
            request=request,
            notes=f"Updated: {formatted_fields}"
        )


def log_employee_create(
    db: Session,
    employee_id: int,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None
):
    """
    Log when an employee record is created.

    Args:
        db: Database session
        employee_id: ID of employee created
        user_id: ID of user creating
        username: Username of user creating
        request: FastAPI request object
    """
    log_sensitive_access(
        db=db,
        entity_type="employee",
        entity_id=employee_id,
        action="create",
        user_id=user_id,
        username=username,
        request=request,
        notes="Employee record created"
    )


def log_employee_delete(
    db: Session,
    employee_id: int,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None
):
    """
    Log when an employee record is deleted.

    Args:
        db: Database session
        employee_id: ID of employee deleted
        user_id: ID of user deleting
        username: Username of user deleting
        request: FastAPI request object
    """
    log_sensitive_access(
        db=db,
        entity_type="employee",
        entity_id=employee_id,
        action="delete",
        user_id=user_id,
        username=username,
        request=request,
        notes="Employee record deleted"
    )
