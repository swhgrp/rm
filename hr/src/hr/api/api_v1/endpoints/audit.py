"""
Audit Log API endpoints
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from hr.db.database import get_db
from hr.models.audit_log import AuditLog
from hr.models.user import User
from hr.api.auth import require_auth
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)


router = APIRouter()


class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    field_name: Optional[str]
    user_id: Optional[int]
    username: Optional[str]
    timestamp: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[AuditLogResponse])
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List audit logs with optional filtering.
    Requires authentication. Only admins or managers can view audit logs.
    """
    # TODO: Add role-based access control - only admins/managers should see audit logs
    # For now, any authenticated user can view

    query = db.query(AuditLog)

    # Apply filters
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    # Order by most recent first
    query = query.order_by(desc(AuditLog.timestamp))

    # Pagination
    audit_logs = query.offset(skip).limit(limit).all()

    return audit_logs


@router.get("/stats")
def get_audit_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get audit log statistics.
    """
    from sqlalchemy import func, distinct

    total_logs = db.query(func.count(AuditLog.id)).scalar()
    total_users = db.query(func.count(distinct(AuditLog.user_id))).scalar()

    # Count by action
    action_counts = db.query(
        AuditLog.action,
        func.count(AuditLog.id)
    ).group_by(AuditLog.action).all()

    # Recent activity (last 7 days)
    from datetime import timedelta
    seven_days_ago = get_now() - timedelta(days=7)
    recent_logs = db.query(func.count(AuditLog.id)).filter(
        AuditLog.timestamp >= seven_days_ago
    ).scalar()

    return {
        "total_logs": total_logs,
        "total_users": total_users,
        "action_counts": {action: count for action, count in action_counts},
        "recent_activity": recent_logs
    }
