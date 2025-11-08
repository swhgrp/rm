"""Email history API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from events.core.database import get_db
from events.core.deps import require_auth
from events.models.document import Email, EmailStatus
from events.schemas.email import EmailResponse
from events.models.user import User

router = APIRouter()


@router.get("/", response_model=List[EmailResponse])
async def list_emails(
    event_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    days: int = Query(default=30, description="Number of days to look back"),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List email history with optional filters

    - **event_id**: Filter by event
    - **status**: Filter by status (queued, sent, failed)
    - **days**: Number of days to look back (default: 30)
    - **limit**: Maximum number of results (default: 100, max: 500)
    """
    from sqlalchemy import desc

    query = db.query(Email)

    # Filter by event
    if event_id:
        query = query.filter(Email.event_id == event_id)

    # Filter by status
    if status_filter:
        try:
            status_enum = EmailStatus(status_filter.lower())
            query = query.filter(Email.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: queued, sent, failed"
            )

    # Filter by date range
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    query = query.filter(Email.created_at >= cutoff_date)

    # Order by most recent first
    query = query.order_by(desc(Email.created_at))

    # Apply limit
    emails = query.limit(limit).all()

    return emails


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get email details by ID"""
    email = db.query(Email).filter(Email.id == email_id).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    return email


@router.post("/{email_id}/resend", response_model=EmailResponse)
async def resend_email(
    email_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Resend a failed email

    Only emails with status 'failed' can be resent.
    """
    email = db.query(Email).filter(Email.id == email_id).first()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )

    if email.status != EmailStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resend failed emails"
        )

    # Reset email status to queued
    email.status = EmailStatus.QUEUED
    email.error_message = None
    email.provider_message_id = None

    db.commit()
    db.refresh(email)

    # TODO: Trigger email sending service
    # For now, just mark as queued and return

    return email


@router.get("/stats/summary")
async def get_email_stats(
    days: int = Query(default=30, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get email statistics

    - **days**: Number of days to analyze (default: 30)

    Returns counts by status for the specified time period.
    """
    from sqlalchemy import func

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Query email counts by status
    stats = db.query(
        Email.status,
        func.count(Email.id).label('count')
    ).filter(
        Email.created_at >= cutoff_date
    ).group_by(Email.status).all()

    # Convert to dictionary
    result = {
        "total": 0,
        "queued": 0,
        "sent": 0,
        "failed": 0,
        "days": days
    }

    for stat in stats:
        status_str = stat.status.value if hasattr(stat.status, 'value') else str(stat.status)
        result[status_str] = stat.count
        result["total"] += stat.count

    return result
