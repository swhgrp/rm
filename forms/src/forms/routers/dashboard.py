"""Dashboard API Router"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from forms.database import get_db
from forms.auth import get_current_user
from forms.models import (
    FormSubmission, FormTemplate, WorkflowInstance, SignatureRequest,
    SubmissionStatus, WorkflowStatus
)
from forms.schemas import DashboardMetrics, FormSubmissionSummary, TrendData

router = APIRouter()


@router.get("/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get dashboard metrics for current user."""
    user_id = user.get("id")
    user_role = user.get("role")
    user_locations = user.get("locations", [])

    # Build location filter
    location_filter = []
    if location_id:
        location_filter.append(FormSubmission.location_id == location_id)
    elif user_role not in ["admin", "superadmin"] and user_locations:
        location_filter.append(FormSubmission.location_id.in_(user_locations))

    # Open forms by status
    open_statuses = [
        SubmissionStatus.DRAFT,
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.PENDING_SIGNATURE,
        SubmissionStatus.PENDING_REVIEW
    ]

    open_forms = {}
    for status in open_statuses:
        query = select(func.count()).select_from(FormSubmission).where(
            FormSubmission.status == status
        )
        if location_filter:
            query = query.where(and_(*location_filter))
        result = await db.execute(query)
        open_forms[status.value] = result.scalar() or 0

    # My action items (signatures + workflow tasks)
    action_items = []

    # Pending signature requests
    sig_requests = await db.execute(
        select(SignatureRequest)
        .where(
            SignatureRequest.requested_employee_id == user_id,
            SignatureRequest.is_fulfilled == False
        )
        .limit(10)
    )
    for req in sig_requests.scalars().all():
        sub_result = await db.execute(
            select(FormSubmission)
            .options(selectinload(FormSubmission.template))
            .where(FormSubmission.id == req.submission_id)
        )
        submission = sub_result.scalar_one_or_none()
        if submission:
            action_items.append(FormSubmissionSummary(
                id=submission.id,
                template_id=submission.template_id,
                template_name=submission.template.name if submission.template else None,
                location_id=submission.location_id,
                subject_employee_id=submission.subject_employee_id,
                submitted_by_employee_id=submission.submitted_by_employee_id,
                status=submission.status,
                reference_number=submission.reference_number,
                submitted_at=submission.submitted_at,
                created_at=submission.created_at
            ))

    # Count by location
    by_location = {}
    location_query = select(
        FormSubmission.location_id,
        FormSubmission.status,
        func.count()
    ).group_by(
        FormSubmission.location_id,
        FormSubmission.status
    )
    if user_role not in ["admin", "superadmin"] and user_locations:
        location_query = location_query.where(FormSubmission.location_id.in_(user_locations))

    location_result = await db.execute(location_query)
    for loc_id, status, count in location_result.all():
        if loc_id not in by_location:
            by_location[loc_id] = {}
        by_location[loc_id][status.value] = count

    # Recent submissions
    recent_query = select(FormSubmission).options(
        selectinload(FormSubmission.template)
    ).order_by(FormSubmission.created_at.desc()).limit(10)

    if location_filter:
        recent_query = recent_query.where(and_(*location_filter))

    recent_result = await db.execute(recent_query)
    recent_submissions = []
    for sub in recent_result.scalars().all():
        recent_submissions.append(FormSubmissionSummary(
            id=sub.id,
            template_id=sub.template_id,
            template_name=sub.template.name if sub.template else None,
            location_id=sub.location_id,
            subject_employee_id=sub.subject_employee_id,
            submitted_by_employee_id=sub.submitted_by_employee_id,
            status=sub.status,
            reference_number=sub.reference_number,
            submitted_at=sub.submitted_at,
            created_at=sub.created_at
        ))

    # Alerts (overdue signatures, stale workflows)
    alerts = []

    # Check for expired signature requests
    expired_sigs = await db.execute(
        select(func.count()).select_from(SignatureRequest).where(
            SignatureRequest.is_fulfilled == False,
            SignatureRequest.expires_at < datetime.utcnow()
        )
    )
    expired_count = expired_sigs.scalar() or 0
    if expired_count > 0:
        alerts.append({
            "type": "warning",
            "message": f"{expired_count} signature requests have expired",
            "count": expired_count
        })

    # Check for stale workflows (in progress for > 7 days)
    stale_date = datetime.utcnow() - timedelta(days=7)
    stale_workflows = await db.execute(
        select(func.count()).select_from(WorkflowInstance).where(
            WorkflowInstance.status == WorkflowStatus.IN_PROGRESS,
            WorkflowInstance.started_at < stale_date
        )
    )
    stale_count = stale_workflows.scalar() or 0
    if stale_count > 0:
        alerts.append({
            "type": "info",
            "message": f"{stale_count} workflows have been in progress for over 7 days",
            "count": stale_count
        })

    return DashboardMetrics(
        open_forms=open_forms,
        my_action_items=action_items,
        by_location=by_location,
        recent_submissions=recent_submissions,
        alerts=alerts
    )


@router.get("/trends", response_model=TrendData)
async def get_trend_data(
    days: int = Query(30, ge=7, le=365),
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get trend data for charts."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Build location filter
    location_filter = []
    if location_id:
        location_filter.append(FormSubmission.location_id == location_id)

    # Submissions over time (by day)
    submissions_query = select(
        func.date_trunc('day', FormSubmission.created_at).label('date'),
        func.count().label('count')
    ).where(
        FormSubmission.created_at >= start_date
    ).group_by(
        func.date_trunc('day', FormSubmission.created_at)
    ).order_by(
        func.date_trunc('day', FormSubmission.created_at)
    )

    if location_filter:
        submissions_query = submissions_query.where(and_(*location_filter))

    result = await db.execute(submissions_query)
    submissions_over_time = [
        {"date": row.date.isoformat() if row.date else None, "count": row.count}
        for row in result.all()
    ]

    # Submissions by template (for incident types)
    template_query = select(
        FormTemplate.name,
        func.count()
    ).join(
        FormSubmission, FormSubmission.template_id == FormTemplate.id
    ).where(
        FormSubmission.created_at >= start_date
    ).group_by(
        FormTemplate.name
    ).order_by(
        func.count().desc()
    ).limit(10)

    if location_filter:
        template_query = template_query.where(and_(*location_filter))

    template_result = await db.execute(template_query)
    incidents_by_type = [
        {"type": row[0], "count": row[1]}
        for row in template_result.all()
    ]

    # Average resolution time (submitted to approved)
    resolution_query = select(
        func.avg(
            func.extract('epoch', FormSubmission.updated_at) -
            func.extract('epoch', FormSubmission.submitted_at)
        )
    ).where(
        FormSubmission.status == SubmissionStatus.APPROVED,
        FormSubmission.submitted_at.isnot(None),
        FormSubmission.created_at >= start_date
    )

    if location_filter:
        resolution_query = resolution_query.where(and_(*location_filter))

    resolution_result = await db.execute(resolution_query)
    avg_seconds = resolution_result.scalar()
    avg_resolution_hours = (avg_seconds / 3600) if avg_seconds else None

    return TrendData(
        submissions_over_time=submissions_over_time,
        incidents_by_type=incidents_by_type,
        avg_resolution_time=avg_resolution_hours
    )
