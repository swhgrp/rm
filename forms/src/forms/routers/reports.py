"""Reports API Router"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from forms.database import get_db
from forms.auth import get_current_user, require_manager
from forms.models import FormSubmission, FormTemplate, AuditLog, FormCategory, AuditAction
from forms.schemas import AuditLogResponse, OSHAReportResponse

router = APIRouter()


@router.get("/osha/{year}", response_model=OSHAReportResponse)
async def get_osha_report(
    year: int,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_manager)
):
    """Generate OSHA 300/300A report data for a year."""
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)

    # Get injury-related templates
    injury_templates = await db.execute(
        select(FormTemplate).where(
            FormTemplate.slug.in_([
                "first-report-of-injury",
                "incident-report",
                "workers-comp-claim"
            ])
        )
    )
    template_ids = [t.id for t in injury_templates.scalars().all()]

    # Build query for injury submissions
    query = select(FormSubmission).options(
        selectinload(FormSubmission.template)
    ).where(
        FormSubmission.template_id.in_(template_ids),
        FormSubmission.created_at >= start_date,
        FormSubmission.created_at <= end_date
    )

    if location_id:
        query = query.where(FormSubmission.location_id == location_id)

    result = await db.execute(query)
    submissions = result.scalars().all()

    # Process submissions into OSHA format
    cases = []
    for sub in submissions:
        data = sub.data or {}
        cases.append({
            "case_number": sub.reference_number,
            "employee_name": data.get("employee_name", "Unknown"),
            "job_title": data.get("job_title", ""),
            "date_of_injury": data.get("date_of_injury") or sub.created_at.strftime("%Y-%m-%d"),
            "where_event_occurred": data.get("location_of_incident", ""),
            "description": data.get("description_of_injury", ""),
            "injury_type": data.get("injury_type", ""),
            "body_part_affected": data.get("body_part", ""),
            "days_away_from_work": data.get("days_away", 0),
            "days_restricted": data.get("days_restricted", 0),
            "death": data.get("resulted_in_death", False)
        })

    # Summary statistics
    total_cases = len(cases)
    deaths = sum(1 for c in cases if c.get("death"))
    days_away_cases = sum(1 for c in cases if c.get("days_away_from_work", 0) > 0)
    restricted_cases = sum(1 for c in cases if c.get("days_restricted", 0) > 0)
    other_recordable = total_cases - deaths - days_away_cases - restricted_cases

    summary = {
        "total_cases": total_cases,
        "deaths": deaths,
        "days_away_from_work_cases": days_away_cases,
        "job_transfer_restriction_cases": restricted_cases,
        "other_recordable_cases": other_recordable,
        "total_days_away": sum(c.get("days_away_from_work", 0) for c in cases),
        "total_days_restricted": sum(c.get("days_restricted", 0) for c in cases)
    }

    # Form 300 data (log of injuries)
    form_300_data = cases

    # Form 300A data (summary)
    form_300a_data = {
        "year": year,
        "establishment_name": "SW Hospitality Group",
        "location_id": location_id,
        "naics_code": "722511",  # Full-Service Restaurants
        "annual_average_employees": 0,  # TODO: Get from HR service
        "total_hours_worked": 0,  # TODO: Calculate from HR
        **summary
    }

    return OSHAReportResponse(
        year=year,
        summary=summary,
        cases=cases,
        form_300_data=form_300_data,
        form_300a_data=form_300a_data
    )


@router.get("/audit-log", response_model=List[AuditLogResponse])
async def get_audit_log(
    submission_id: Optional[str] = None,
    template_id: Optional[str] = None,
    employee_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_manager)
):
    """Get audit log entries with filters."""
    from uuid import UUID

    query = select(AuditLog)

    filters = []

    if submission_id:
        filters.append(AuditLog.submission_id == UUID(submission_id))

    if template_id:
        filters.append(AuditLog.template_id == UUID(template_id))

    if employee_id:
        filters.append(AuditLog.employee_id == employee_id)

    if action:
        filters.append(AuditLog.action == action)

    if date_from:
        filters.append(AuditLog.performed_at >= date_from)

    if date_to:
        filters.append(AuditLog.performed_at <= date_to)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(AuditLog.performed_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return logs


@router.get("/submission-counts")
async def get_submission_counts(
    group_by: str = Query("template", enum=["template", "location", "status", "month"]),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get submission counts grouped by various dimensions."""
    filters = []

    if date_from:
        filters.append(FormSubmission.created_at >= date_from)
    if date_to:
        filters.append(FormSubmission.created_at <= date_to)
    if location_id:
        filters.append(FormSubmission.location_id == location_id)

    if group_by == "template":
        query = select(
            FormTemplate.name,
            func.count()
        ).join(
            FormSubmission, FormSubmission.template_id == FormTemplate.id
        ).group_by(FormTemplate.name)

    elif group_by == "location":
        query = select(
            FormSubmission.location_id,
            func.count()
        ).group_by(FormSubmission.location_id)

    elif group_by == "status":
        query = select(
            FormSubmission.status,
            func.count()
        ).group_by(FormSubmission.status)

    elif group_by == "month":
        query = select(
            func.date_trunc('month', FormSubmission.created_at).label('month'),
            func.count()
        ).group_by(func.date_trunc('month', FormSubmission.created_at)).order_by('month')

    else:
        return {"error": "Invalid group_by parameter"}

    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query)
    rows = result.all()

    if group_by == "month":
        return [{"month": row[0].isoformat() if row[0] else None, "count": row[1]} for row in rows]
    elif group_by == "status":
        return [{group_by: row[0].value if row[0] else None, "count": row[1]} for row in rows]
    else:
        return [{group_by: row[0], "count": row[1]} for row in rows]


@router.get("/export/csv")
async def export_submissions_csv(
    template_id: Optional[str] = None,
    location_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_manager)
):
    """Export submissions as CSV."""
    from uuid import UUID
    import csv
    import io

    query = select(FormSubmission).options(
        selectinload(FormSubmission.template)
    )

    filters = []
    if template_id:
        filters.append(FormSubmission.template_id == UUID(template_id))
    if location_id:
        filters.append(FormSubmission.location_id == location_id)
    if date_from:
        filters.append(FormSubmission.created_at >= date_from)
    if date_to:
        filters.append(FormSubmission.created_at <= date_to)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(FormSubmission.created_at.desc())

    result = await db.execute(query)
    submissions = result.scalars().all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Reference Number",
        "Template",
        "Location ID",
        "Status",
        "Created At",
        "Submitted At",
        "Data (JSON)"
    ])

    # Rows
    for sub in submissions:
        import json
        writer.writerow([
            sub.reference_number,
            sub.template.name if sub.template else "",
            sub.location_id,
            sub.status.value,
            sub.created_at.isoformat() if sub.created_at else "",
            sub.submitted_at.isoformat() if sub.submitted_at else "",
            json.dumps(sub.data) if sub.data else ""
        ])

    csv_content = output.getvalue()
    output.close()

    filename = f"submissions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
