"""
Audit logging utilities
"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from fastapi import Request
from restaurant_inventory.models.audit_log import AuditLog
from restaurant_inventory.models.user import User


def log_audit_event(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    user: Optional[User] = None,
    changes: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> AuditLog:
    """
    Create an audit log entry

    Args:
        db: Database session
        action: Action performed (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, etc.)
        entity_type: Type of entity affected (user, location, item, inventory, transfer, etc.)
        entity_id: ID of the affected entity
        user: User performing the action
        changes: Dictionary of changes (e.g., {"old": {...}, "new": {...}})
        request: FastAPI request object for extracting IP and user agent

    Returns:
        Created AuditLog instance
    """

    # Extract request metadata
    ip_address = None
    user_agent = None
    if request:
        # Get IP address (handle proxies)
        ip_address = request.client.host if request.client else None
        # Check for forwarded IP
        if "x-forwarded-for" in request.headers:
            ip_address = request.headers["x-forwarded-for"].split(",")[0].strip()

        # Get user agent
        user_agent = request.headers.get("user-agent")
        if user_agent and len(user_agent) > 255:
            user_agent = user_agent[:255]

    # Create audit log entry
    audit_entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent
    )

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    return audit_entry


def create_change_dict(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a changes dictionary showing what changed between old and new data

    Args:
        old_data: Dictionary of old values
        new_data: Dictionary of new values

    Returns:
        Dictionary with "old" and "new" keys containing only changed fields
    """
    changes = {"old": {}, "new": {}}

    all_keys = set(old_data.keys()) | set(new_data.keys())

    for key in all_keys:
        old_val = old_data.get(key)
        new_val = new_data.get(key)

        if old_val != new_val:
            changes["old"][key] = old_val
            changes["new"][key] = new_val

    return changes if changes["old"] or changes["new"] else None