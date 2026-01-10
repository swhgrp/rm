"""Reports router for Food Safety Service"""
import csv
import logging
from io import StringIO, BytesIO
from datetime import date, datetime, timedelta
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case

from food_safety.database import get_db
from food_safety.models import (
    TemperatureLog, Location,
    ChecklistTemplate, ChecklistSubmission, ChecklistResponse, ChecklistStatus,
    Inspection, InspectionViolation, InspectionType, ViolationSeverity,
    Incident, CorrectiveAction, IncidentType, IncidentStatus, CorrectiveActionStatus
)
from food_safety.schemas import (
    TemperatureReportSummary, TemperatureReportTrend, TemperatureReportDetail, TemperatureReportResponse,
    ChecklistReportSummary, ChecklistReportTrend, ChecklistReportDetail, ChecklistReportResponse,
    InspectionReportSummary, InspectionReportTrend, InspectionReportDetail, InspectionReportResponse,
    IncidentReportSummary, IncidentReportTrend, IncidentReportDetail, IncidentReportResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== Helper Functions ====================

def get_location_map(locations: List) -> dict:
    """Create a map of location_id to location_name"""
    return {loc.id: loc.name for loc in locations}


async def get_all_locations(db: AsyncSession) -> List:
    """Get all active locations"""
    result = await db.execute(select(Location).where(Location.is_active == True))
    return result.scalars().all()


# ==================== Temperature Report ====================

@router.get("/temperature", response_model=TemperatureReportResponse)
async def get_temperature_report(
    start_date: date = Query(..., description="Start date for report"),
    end_date: date = Query(..., description="End date for report"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    equipment_id: Optional[int] = Query(None, description="Filter by equipment"),
    db: AsyncSession = Depends(get_db)
):
    """Generate temperature log report with summary, trends, and details"""

    # Build base filter
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    base_filter = and_(
        TemperatureLog.logged_at >= start_dt,
        TemperatureLog.logged_at <= end_dt
    )
    if location_id:
        base_filter = and_(base_filter, TemperatureLog.location_id == location_id)
    if equipment_id:
        base_filter = and_(base_filter, TemperatureLog.maintenance_equipment_id == equipment_id)

    # Get locations for mapping
    locations = await get_all_locations(db)
    loc_map = get_location_map(locations)

    # Summary statistics
    summary_query = select(
        func.count(TemperatureLog.id).label('total'),
        func.sum(case((TemperatureLog.alert_status.isnot(None), 1), else_=0)).label('alerts'),
        func.sum(case((TemperatureLog.is_within_range == True, 1), else_=0)).label('within_range'),
        func.avg(TemperatureLog.temperature).label('avg_temp')
    ).where(base_filter)

    summary_result = await db.execute(summary_query)
    summary_row = summary_result.first()

    total = summary_row.total or 0
    alerts = int(summary_row.alerts or 0)
    within_range = int(summary_row.within_range or 0)
    compliance_rate = (within_range / total * 100) if total > 0 else 100.0
    avg_temp = float(summary_row.avg_temp) if summary_row.avg_temp else None

    # Equipment breakdown
    equipment_query = select(
        TemperatureLog.maintenance_equipment_id,
        TemperatureLog.equipment_name,
        func.count(TemperatureLog.id).label('readings'),
        func.sum(case((TemperatureLog.alert_status.isnot(None), 1), else_=0)).label('alerts')
    ).where(base_filter).group_by(
        TemperatureLog.maintenance_equipment_id,
        TemperatureLog.equipment_name
    )

    equipment_result = await db.execute(equipment_query)
    equipment_breakdown = [
        {
            "equipment_id": row.maintenance_equipment_id,
            "name": row.equipment_name,
            "readings": row.readings,
            "alerts": int(row.alerts or 0)
        }
        for row in equipment_result.all()
    ]

    summary = TemperatureReportSummary(
        total_readings=total,
        alerts_count=alerts,
        compliance_rate=round(compliance_rate, 1),
        avg_temperature=round(avg_temp, 1) if avg_temp else None,
        equipment_breakdown=equipment_breakdown
    )

    # Trends by day
    trends_query = select(
        func.date(TemperatureLog.logged_at).label('log_date'),
        func.count(TemperatureLog.id).label('readings'),
        func.sum(case((TemperatureLog.alert_status.isnot(None), 1), else_=0)).label('alerts'),
        func.avg(TemperatureLog.temperature).label('avg_temp')
    ).where(base_filter).group_by(
        func.date(TemperatureLog.logged_at)
    ).order_by(func.date(TemperatureLog.logged_at))

    trends_result = await db.execute(trends_query)
    trends = [
        TemperatureReportTrend(
            date=str(row.log_date),
            readings_count=row.readings,
            alerts_count=int(row.alerts or 0),
            avg_temperature=round(float(row.avg_temp), 1) if row.avg_temp else None
        )
        for row in trends_result.all()
    ]

    # Details (limit to most recent 500)
    details_query = select(TemperatureLog).where(base_filter).order_by(
        TemperatureLog.logged_at.desc()
    ).limit(500)

    details_result = await db.execute(details_query)
    details = [
        TemperatureReportDetail(
            id=log.id,
            equipment_name=log.equipment_name,
            location_name=loc_map.get(log.location_id),
            temperature=float(log.temperature),
            temp_unit=log.temp_unit or "F",
            min_threshold=float(log.min_threshold) if log.min_threshold else None,
            max_threshold=float(log.max_threshold) if log.max_threshold else None,
            is_within_range=log.is_within_range,
            alert_status=log.alert_status.value if log.alert_status else None,
            logged_at=log.logged_at,
            logged_by=log.logged_by
        )
        for log in details_result.scalars().all()
    ]

    return TemperatureReportResponse(
        summary=summary,
        trends=trends,
        details=details,
        filters_applied={
            "start_date": str(start_date),
            "end_date": str(end_date),
            "location_id": location_id,
            "equipment_id": equipment_id
        }
    )


@router.get("/temperature/export/csv")
async def export_temperature_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    equipment_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export temperature report as CSV"""
    report = await get_temperature_report(start_date, end_date, location_id, equipment_id, db)

    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'ID', 'Equipment', 'Location', 'Temperature', 'Unit',
        'Min Threshold', 'Max Threshold', 'Within Range', 'Alert Status', 'Logged At'
    ])

    # Data
    for row in report.details:
        writer.writerow([
            row.id,
            row.equipment_name or '',
            row.location_name or '',
            row.temperature,
            row.temp_unit,
            row.min_threshold or '',
            row.max_threshold or '',
            'Yes' if row.is_within_range else 'No',
            row.alert_status or '',
            row.logged_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    output.seek(0)
    filename = f"temperature-report-{start_date}-to-{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== Checklist Report ====================

@router.get("/checklist", response_model=ChecklistReportResponse)
async def get_checklist_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    template_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generate checklist compliance report"""

    base_filter = and_(
        ChecklistSubmission.submission_date >= start_date,
        ChecklistSubmission.submission_date <= end_date
    )
    if location_id:
        base_filter = and_(base_filter, ChecklistSubmission.location_id == location_id)
    if template_id:
        base_filter = and_(base_filter, ChecklistSubmission.template_id == template_id)

    locations = await get_all_locations(db)
    loc_map = get_location_map(locations)

    # Summary statistics
    completed_statuses = [ChecklistStatus.COMPLETED, ChecklistStatus.SIGNED_OFF]

    summary_query = select(
        func.count(ChecklistSubmission.id).label('total'),
        func.sum(case((ChecklistSubmission.status.in_(completed_statuses), 1), else_=0)).label('completed'),
        func.sum(case((ChecklistSubmission.status == ChecklistStatus.PENDING_SIGNOFF, 1), else_=0)).label('pending')
    ).where(base_filter)

    summary_result = await db.execute(summary_query)
    summary_row = summary_result.first()

    total = summary_row.total or 0
    completed = int(summary_row.completed or 0)
    pending = int(summary_row.pending or 0)
    completion_rate = (completed / total * 100) if total > 0 else 0.0

    # Pass/fail rate from responses
    response_query = select(
        func.count(ChecklistResponse.id).label('total'),
        func.sum(case((ChecklistResponse.is_passing == True, 1), else_=0)).label('passed'),
        func.sum(case((ChecklistResponse.is_passing == False, 1), else_=0)).label('failed')
    ).join(ChecklistSubmission).where(
        and_(base_filter, ChecklistResponse.is_passing.isnot(None))
    )

    response_result = await db.execute(response_query)
    response_row = response_result.first()

    total_responses = response_row.total or 0
    passed_responses = int(response_row.passed or 0)
    pass_rate = (passed_responses / total_responses * 100) if total_responses > 0 else 100.0

    # By template breakdown
    template_query = select(
        ChecklistTemplate.id,
        ChecklistTemplate.name,
        func.count(ChecklistSubmission.id).label('submissions'),
        func.sum(case((ChecklistSubmission.status.in_(completed_statuses), 1), else_=0)).label('completed')
    ).join(ChecklistSubmission).where(base_filter).group_by(
        ChecklistTemplate.id, ChecklistTemplate.name
    )

    template_result = await db.execute(template_query)
    by_template = [
        {
            "template_id": row.id,
            "name": row.name,
            "submissions": row.submissions,
            "completion_rate": round((row.completed or 0) / row.submissions * 100, 1) if row.submissions > 0 else 0
        }
        for row in template_result.all()
    ]

    summary = ChecklistReportSummary(
        total_submissions=total,
        completed_count=completed,
        pending_signoff_count=pending,
        completion_rate=round(completion_rate, 1),
        pass_rate=round(pass_rate, 1),
        by_template=by_template
    )

    # Trends by day
    trends_query = select(
        ChecklistSubmission.submission_date,
        func.count(ChecklistSubmission.id).label('submissions'),
        func.sum(case((ChecklistSubmission.status.in_(completed_statuses), 1), else_=0)).label('completed'),
        func.sum(case((ChecklistSubmission.status == ChecklistStatus.PENDING_SIGNOFF, 1), else_=0)).label('pending')
    ).where(base_filter).group_by(
        ChecklistSubmission.submission_date
    ).order_by(ChecklistSubmission.submission_date)

    trends_result = await db.execute(trends_query)
    trends = [
        ChecklistReportTrend(
            date=str(row.submission_date),
            submissions=row.submissions,
            completed=int(row.completed or 0),
            pending=int(row.pending or 0)
        )
        for row in trends_result.all()
    ]

    # Details with response counts
    details_query = select(
        ChecklistSubmission,
        ChecklistTemplate.name.label('template_name'),
        func.count(ChecklistResponse.id).label('total_items'),
        func.sum(case((ChecklistResponse.is_passing == True, 1), else_=0)).label('passed'),
        func.sum(case((ChecklistResponse.is_passing == False, 1), else_=0)).label('failed')
    ).join(ChecklistTemplate).outerjoin(ChecklistResponse).where(base_filter).group_by(
        ChecklistSubmission.id, ChecklistTemplate.name
    ).order_by(ChecklistSubmission.submission_date.desc()).limit(200)

    details_result = await db.execute(details_query)
    details = [
        ChecklistReportDetail(
            id=row.ChecklistSubmission.id,
            template_name=row.template_name,
            location_name=loc_map.get(row.ChecklistSubmission.location_id),
            submission_date=row.ChecklistSubmission.submission_date,
            status=row.ChecklistSubmission.status.value,
            completed_by=row.ChecklistSubmission.completed_by,
            completed_at=row.ChecklistSubmission.completed_at,
            items_total=row.total_items or 0,
            items_passed=int(row.passed or 0),
            items_failed=int(row.failed or 0)
        )
        for row in details_result.all()
    ]

    return ChecklistReportResponse(
        summary=summary,
        trends=trends,
        details=details,
        filters_applied={
            "start_date": str(start_date),
            "end_date": str(end_date),
            "location_id": location_id,
            "template_id": template_id
        }
    )


@router.get("/checklist/export/csv")
async def export_checklist_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    template_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export checklist report as CSV"""
    report = await get_checklist_report(start_date, end_date, location_id, template_id, db)

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'ID', 'Template', 'Location', 'Date', 'Status',
        'Total Items', 'Passed', 'Failed', 'Completed At'
    ])

    for row in report.details:
        writer.writerow([
            row.id,
            row.template_name or '',
            row.location_name or '',
            str(row.submission_date),
            row.status,
            row.items_total,
            row.items_passed,
            row.items_failed,
            row.completed_at.strftime('%Y-%m-%d %H:%M:%S') if row.completed_at else ''
        ])

    output.seek(0)
    filename = f"checklist-report-{start_date}-to-{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== Inspection Report ====================

@router.get("/inspection", response_model=InspectionReportResponse)
async def get_inspection_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    inspection_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generate inspection results report"""

    base_filter = and_(
        Inspection.inspection_date >= start_date,
        Inspection.inspection_date <= end_date
    )
    if location_id:
        base_filter = and_(base_filter, Inspection.location_id == location_id)
    if inspection_type:
        base_filter = and_(base_filter, Inspection.inspection_type == inspection_type)

    locations = await get_all_locations(db)
    loc_map = get_location_map(locations)

    # Summary statistics
    summary_query = select(
        func.count(Inspection.id).label('total'),
        func.sum(case((Inspection.passed == True, 1), else_=0)).label('passed'),
        func.sum(case((Inspection.passed == False, 1), else_=0)).label('failed'),
        func.avg(Inspection.score).label('avg_score'),
        func.sum(case((Inspection.follow_up_required == True, 1), else_=0)).label('follow_ups')
    ).where(base_filter)

    summary_result = await db.execute(summary_query)
    summary_row = summary_result.first()

    total = summary_row.total or 0
    passed = int(summary_row.passed or 0)
    failed = int(summary_row.failed or 0)
    avg_score = float(summary_row.avg_score) if summary_row.avg_score else None
    follow_ups = int(summary_row.follow_ups or 0)

    # Violations by severity
    violations_query = select(
        InspectionViolation.severity,
        func.count(InspectionViolation.id).label('count')
    ).join(Inspection).where(base_filter).group_by(InspectionViolation.severity)

    violations_result = await db.execute(violations_query)
    violations_by_severity = {
        row.severity.value: row.count
        for row in violations_result.all()
    }

    # Pending corrections
    pending_query = select(func.count(InspectionViolation.id)).join(Inspection).where(
        and_(base_filter, InspectionViolation.is_corrected == False)
    )
    pending_result = await db.execute(pending_query)
    pending_corrections = pending_result.scalar() or 0

    summary = InspectionReportSummary(
        total_inspections=total,
        passed_count=passed,
        failed_count=failed,
        average_score=round(avg_score, 1) if avg_score else None,
        violations_by_severity=violations_by_severity,
        pending_corrections=pending_corrections,
        follow_ups_required=follow_ups
    )

    # Trends by month (for inspections, monthly makes more sense)
    trends_query = select(
        Inspection.inspection_date,
        func.count(Inspection.id).label('inspections'),
        func.avg(Inspection.score).label('avg_score')
    ).where(base_filter).group_by(
        Inspection.inspection_date
    ).order_by(Inspection.inspection_date)

    trends_result = await db.execute(trends_query)

    # Also get violation counts per inspection date
    violations_by_date_query = select(
        Inspection.inspection_date,
        func.count(InspectionViolation.id).label('violations')
    ).join(InspectionViolation).where(base_filter).group_by(
        Inspection.inspection_date
    )
    violations_by_date_result = await db.execute(violations_by_date_query)
    violations_by_date = {row.inspection_date: row.violations for row in violations_by_date_result.all()}

    trends = [
        InspectionReportTrend(
            date=str(row.inspection_date),
            inspections_count=row.inspections,
            average_score=round(float(row.avg_score), 1) if row.avg_score else None,
            violations_count=violations_by_date.get(row.inspection_date, 0)
        )
        for row in trends_result.all()
    ]

    # Details with violation counts
    details_query = select(
        Inspection,
        func.count(InspectionViolation.id).label('violations_count'),
        func.sum(case((InspectionViolation.severity == ViolationSeverity.CRITICAL, 1), else_=0)).label('critical')
    ).outerjoin(InspectionViolation).where(base_filter).group_by(
        Inspection.id
    ).order_by(Inspection.inspection_date.desc()).limit(100)

    details_result = await db.execute(details_query)
    details = [
        InspectionReportDetail(
            id=row.Inspection.id,
            location_name=loc_map.get(row.Inspection.location_id),
            inspection_type=row.Inspection.inspection_type.value,
            inspection_date=row.Inspection.inspection_date,
            inspector_name=row.Inspection.inspector_name,
            score=float(row.Inspection.score) if row.Inspection.score else None,
            grade=row.Inspection.grade,
            passed=row.Inspection.passed,
            violations_count=row.violations_count or 0,
            critical_violations=int(row.critical or 0),
            follow_up_required=row.Inspection.follow_up_required or False,
            follow_up_date=row.Inspection.follow_up_date
        )
        for row in details_result.all()
    ]

    return InspectionReportResponse(
        summary=summary,
        trends=trends,
        details=details,
        filters_applied={
            "start_date": str(start_date),
            "end_date": str(end_date),
            "location_id": location_id,
            "inspection_type": inspection_type
        }
    )


@router.get("/inspection/export/csv")
async def export_inspection_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    inspection_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export inspection report as CSV"""
    report = await get_inspection_report(start_date, end_date, location_id, inspection_type, db)

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'ID', 'Location', 'Type', 'Date', 'Inspector',
        'Score', 'Grade', 'Passed', 'Violations', 'Critical', 'Follow-up Required'
    ])

    for row in report.details:
        writer.writerow([
            row.id,
            row.location_name or '',
            row.inspection_type,
            str(row.inspection_date),
            row.inspector_name or '',
            row.score or '',
            row.grade or '',
            'Yes' if row.passed else 'No' if row.passed is False else '',
            row.violations_count,
            row.critical_violations,
            'Yes' if row.follow_up_required else 'No'
        ])

    output.seek(0)
    filename = f"inspection-report-{start_date}-to-{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== Incident Report ====================

@router.get("/incident", response_model=IncidentReportResponse)
async def get_incident_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    incident_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Generate incident summary report"""

    base_filter = and_(
        Incident.incident_date >= start_date,
        Incident.incident_date <= end_date
    )
    if location_id:
        base_filter = and_(base_filter, Incident.location_id == location_id)
    if incident_type:
        base_filter = and_(base_filter, Incident.incident_type == incident_type)
    if severity:
        base_filter = and_(base_filter, Incident.severity == severity)

    locations = await get_all_locations(db)
    loc_map = get_location_map(locations)

    open_statuses = [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.ACTION_REQUIRED]

    # Summary statistics
    summary_query = select(
        func.count(Incident.id).label('total'),
        func.sum(case((Incident.status.in_(open_statuses), 1), else_=0)).label('open'),
        func.sum(case((Incident.status == IncidentStatus.RESOLVED, 1), else_=0)).label('resolved'),
        func.sum(case((Incident.status == IncidentStatus.CLOSED, 1), else_=0)).label('closed')
    ).where(base_filter)

    summary_result = await db.execute(summary_query)
    summary_row = summary_result.first()

    total = summary_row.total or 0
    open_count = int(summary_row.open or 0)
    resolved = int(summary_row.resolved or 0)
    closed = int(summary_row.closed or 0)

    # By type breakdown
    type_query = select(
        Incident.incident_type,
        func.count(Incident.id).label('count')
    ).where(base_filter).group_by(Incident.incident_type)

    type_result = await db.execute(type_query)
    by_type = {row.incident_type.value: row.count for row in type_result.all()}

    # By severity breakdown
    severity_query = select(
        Incident.severity,
        func.count(Incident.id).label('count')
    ).where(base_filter).group_by(Incident.severity)

    severity_result = await db.execute(severity_query)
    by_severity = {row.severity: row.count for row in severity_result.all()}

    # Average resolution time (for resolved incidents)
    resolution_query = select(
        func.avg(
            func.extract('epoch', Incident.resolved_at - Incident.reported_at) / 3600
        )
    ).where(
        and_(base_filter, Incident.resolved_at.isnot(None))
    )
    resolution_result = await db.execute(resolution_query)
    avg_resolution = resolution_result.scalar()

    # Pending corrective actions
    pending_actions_query = select(func.count(CorrectiveAction.id)).join(Incident).where(
        and_(
            base_filter,
            CorrectiveAction.status.in_([CorrectiveActionStatus.PENDING, CorrectiveActionStatus.IN_PROGRESS])
        )
    )
    pending_result = await db.execute(pending_actions_query)
    pending_actions = pending_result.scalar() or 0

    summary = IncidentReportSummary(
        total_incidents=total,
        open_count=open_count,
        resolved_count=resolved,
        closed_count=closed,
        by_type=by_type,
        by_severity=by_severity,
        avg_resolution_hours=round(float(avg_resolution), 1) if avg_resolution else None,
        pending_corrective_actions=pending_actions
    )

    # Trends by day
    trends_query = select(
        Incident.incident_date,
        func.count(Incident.id).label('incidents'),
        func.sum(case((Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED]), 1), else_=0)).label('resolved')
    ).where(base_filter).group_by(
        Incident.incident_date
    ).order_by(Incident.incident_date)

    trends_result = await db.execute(trends_query)
    trends = [
        IncidentReportTrend(
            date=str(row.incident_date),
            incidents_count=row.incidents,
            resolved_count=int(row.resolved or 0)
        )
        for row in trends_result.all()
    ]

    # Details
    details_query = select(Incident).where(base_filter).order_by(
        Incident.incident_date.desc()
    ).limit(200)

    details_result = await db.execute(details_query)
    details = []
    for inc in details_result.scalars().all():
        resolution_hours = None
        if inc.resolved_at and inc.reported_at:
            delta = inc.resolved_at - inc.reported_at
            resolution_hours = round(delta.total_seconds() / 3600, 1)

        details.append(IncidentReportDetail(
            id=inc.id,
            incident_number=inc.incident_number,
            title=inc.title,
            location_name=loc_map.get(inc.location_id),
            incident_type=inc.incident_type.value,
            severity=inc.severity,
            status=inc.status.value,
            incident_date=inc.incident_date,
            reported_at=inc.reported_at,
            resolved_at=inc.resolved_at,
            resolution_hours=resolution_hours
        ))

    return IncidentReportResponse(
        summary=summary,
        trends=trends,
        details=details,
        filters_applied={
            "start_date": str(start_date),
            "end_date": str(end_date),
            "location_id": location_id,
            "incident_type": incident_type,
            "severity": severity
        }
    )


@router.get("/incident/export/csv")
async def export_incident_csv(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    incident_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export incident report as CSV"""
    report = await get_incident_report(start_date, end_date, location_id, incident_type, severity, db)

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Incident #', 'Title', 'Location', 'Type', 'Severity',
        'Status', 'Date', 'Reported At', 'Resolved At', 'Resolution Hours'
    ])

    for row in report.details:
        writer.writerow([
            row.incident_number,
            row.title,
            row.location_name or '',
            row.incident_type,
            row.severity,
            row.status,
            str(row.incident_date),
            row.reported_at.strftime('%Y-%m-%d %H:%M:%S'),
            row.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if row.resolved_at else '',
            row.resolution_hours or ''
        ])

    output.seek(0)
    filename = f"incident-report-{start_date}-to-{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== PDF Export ====================

@router.get("/temperature/export/pdf")
async def export_temperature_pdf(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    equipment_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export temperature report as PDF"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF export requires reportlab library")

    report = await get_temperature_report(start_date, end_date, location_id, equipment_id, db)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("Temperature Log Report", styles['Heading1']))
    elements.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Summary
    summary = report.summary
    summary_data = [
        ['Total Readings', 'Alerts', 'Compliance Rate', 'Avg Temperature'],
        [str(summary.total_readings), str(summary.alerts_count),
         f"{summary.compliance_rate}%", f"{summary.avg_temperature}F" if summary.avg_temperature else "N/A"]
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Details table (limit rows for PDF)
    elements.append(Paragraph("Recent Readings", styles['Heading2']))
    detail_data = [['Equipment', 'Location', 'Temp', 'Range', 'Status', 'Time']]
    for row in report.details[:50]:
        detail_data.append([
            (row.equipment_name or '')[:25],
            (row.location_name or '')[:20],
            f"{row.temperature}{row.temp_unit}",
            'OK' if row.is_within_range else 'ALERT',
            row.alert_status or '-',
            row.logged_at.strftime('%m/%d %H:%M')
        ])

    detail_table = Table(detail_data, colWidths=[120, 100, 60, 50, 70, 80])
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(detail_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"temperature-report-{start_date}-to-{end_date}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/checklist/export/pdf")
async def export_checklist_pdf(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    template_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export checklist report as PDF"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF export requires reportlab library")

    report = await get_checklist_report(start_date, end_date, location_id, template_id, db)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Checklist Compliance Report", styles['Heading1']))
    elements.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    summary = report.summary
    summary_data = [
        ['Total Submissions', 'Completed', 'Pending Sign-off', 'Completion Rate', 'Pass Rate'],
        [str(summary.total_submissions), str(summary.completed_count),
         str(summary.pending_signoff_count), f"{summary.completion_rate}%", f"{summary.pass_rate}%"]
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Recent Submissions", styles['Heading2']))
    detail_data = [['Template', 'Location', 'Date', 'Status', 'Items', 'Passed', 'Failed']]
    for row in report.details[:50]:
        detail_data.append([
            (row.template_name or '')[:25],
            (row.location_name or '')[:20],
            str(row.submission_date),
            row.status,
            str(row.items_total),
            str(row.items_passed),
            str(row.items_failed)
        ])

    detail_table = Table(detail_data)
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(detail_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"checklist-report-{start_date}-to-{end_date}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/inspection/export/pdf")
async def export_inspection_pdf(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    inspection_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export inspection report as PDF"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF export requires reportlab library")

    report = await get_inspection_report(start_date, end_date, location_id, inspection_type, db)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Inspection Results Report", styles['Heading1']))
    elements.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    summary = report.summary
    summary_data = [
        ['Total', 'Passed', 'Failed', 'Avg Score', 'Follow-ups', 'Pending Corrections'],
        [str(summary.total_inspections), str(summary.passed_count), str(summary.failed_count),
         str(summary.average_score or 'N/A'), str(summary.follow_ups_required), str(summary.pending_corrections)]
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Inspections", styles['Heading2']))
    detail_data = [['Location', 'Type', 'Date', 'Inspector', 'Score', 'Passed', 'Violations']]
    for row in report.details[:50]:
        detail_data.append([
            (row.location_name or '')[:20],
            row.inspection_type,
            str(row.inspection_date),
            (row.inspector_name or '')[:15],
            str(row.score or ''),
            'Yes' if row.passed else 'No' if row.passed is False else '',
            str(row.violations_count)
        ])

    detail_table = Table(detail_data)
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(detail_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"inspection-report-{start_date}-to-{end_date}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/incident/export/pdf")
async def export_incident_pdf(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[int] = Query(None),
    incident_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export incident report as PDF"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF export requires reportlab library")

    report = await get_incident_report(start_date, end_date, location_id, incident_type, severity, db)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Incident Summary Report", styles['Heading1']))
    elements.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    summary = report.summary
    summary_data = [
        ['Total', 'Open', 'Resolved', 'Closed', 'Avg Resolution (hrs)', 'Pending Actions'],
        [str(summary.total_incidents), str(summary.open_count), str(summary.resolved_count),
         str(summary.closed_count), str(summary.avg_resolution_hours or 'N/A'), str(summary.pending_corrective_actions)]
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Incidents", styles['Heading2']))
    detail_data = [['#', 'Title', 'Location', 'Type', 'Severity', 'Status', 'Date']]
    for row in report.details[:50]:
        detail_data.append([
            row.incident_number,
            row.title[:30],
            (row.location_name or '')[:15],
            row.incident_type[:15],
            row.severity,
            row.status,
            str(row.incident_date)
        ])

    detail_table = Table(detail_data, colWidths=[70, 150, 80, 80, 60, 60, 70])
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(detail_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"incident-report-{start_date}-to-{end_date}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
