"""Dashboard router for Food Safety Service"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from sqlalchemy.orm import selectinload

from food_safety.database import get_db
from food_safety.models import (
    TemperatureLog, TemperatureAlertStatus,
    ChecklistSubmission, ChecklistTemplate, ChecklistStatus,
    Incident, IncidentStatus, CorrectiveAction, CorrectiveActionStatus,
    Location
)
from food_safety.schemas import (
    DashboardStats, DashboardAlerts,
    TemperatureLogWithDetails, ChecklistSubmissionWithDetails,
    IncidentWithDetails, CorrectiveActionResponse
)
from food_safety.services.maintenance_client import maintenance_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics"""
    today = date.today()

    # Total equipment from Maintenance service
    try:
        equipment_list = await maintenance_client.get_temperature_equipment(location_id=location_id)
        total_equipment = len(equipment_list)
    except Exception as e:
        logger.error(f"Error fetching equipment from Maintenance: {e}")
        total_equipment = 0

    # Temperature alerts today
    alerts_query = select(func.count(TemperatureLog.id)).where(
        and_(
            TemperatureLog.is_within_range == False,
            func.date(TemperatureLog.logged_at) == today
        )
    )
    if location_id:
        alerts_query = alerts_query.where(TemperatureLog.location_id == location_id)
    result = await db.execute(alerts_query)
    temperature_alerts_today = result.scalar() or 0

    # Checklists due today (templates that should have submissions today)
    checklists_query = select(func.count(ChecklistTemplate.id)).where(
        and_(
            ChecklistTemplate.is_active == True,
            ChecklistTemplate.frequency == "daily"
        )
    )
    if location_id:
        checklists_query = checklists_query.where(ChecklistTemplate.location_id == location_id)
    result = await db.execute(checklists_query)
    checklists_due_today = result.scalar() or 0

    # Checklists completed today
    completed_query = select(func.count(ChecklistSubmission.id)).where(
        and_(
            ChecklistSubmission.submission_date == today,
            ChecklistSubmission.status.in_([ChecklistStatus.COMPLETED, ChecklistStatus.SIGNED_OFF])
        )
    )
    if location_id:
        completed_query = completed_query.where(ChecklistSubmission.location_id == location_id)
    result = await db.execute(completed_query)
    checklists_completed_today = result.scalar() or 0

    # Open incidents
    incidents_query = select(func.count(Incident.id)).where(
        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.ACTION_REQUIRED])
    )
    if location_id:
        incidents_query = incidents_query.where(Incident.location_id == location_id)
    result = await db.execute(incidents_query)
    open_incidents = result.scalar() or 0

    # Pending corrective actions
    ca_query = select(func.count(CorrectiveAction.id)).where(
        CorrectiveAction.status.in_([CorrectiveActionStatus.PENDING, CorrectiveActionStatus.IN_PROGRESS])
    )
    result = await db.execute(ca_query)
    pending_corrective_actions = result.scalar() or 0

    # Recent temperature logs
    temps_query = select(TemperatureLog).order_by(TemperatureLog.logged_at.desc()).limit(10)
    if location_id:
        temps_query = temps_query.where(TemperatureLog.location_id == location_id)
    result = await db.execute(temps_query)
    recent_temps = result.scalars().all()

    # Hydrate temps with location names
    recent_temp_responses = []
    if recent_temps:
        loc_ids = list(set(t.location_id for t in recent_temps))
        loc_q = select(Location.id, Location.name).where(Location.id.in_(loc_ids))
        loc_names = dict((await db.execute(loc_q)).all())
        for t in recent_temps:
            resp = TemperatureLogWithDetails.model_validate(t)
            resp.location_name = loc_names.get(t.location_id)
            recent_temp_responses.append(resp)

    # Pending signoffs
    signoffs_query = select(ChecklistSubmission).options(
        selectinload(ChecklistSubmission.template)
    ).where(
        ChecklistSubmission.status == ChecklistStatus.PENDING_SIGNOFF
    ).order_by(ChecklistSubmission.created_at.desc()).limit(10)
    if location_id:
        signoffs_query = signoffs_query.where(ChecklistSubmission.location_id == location_id)
    result = await db.execute(signoffs_query)
    pending_signoffs = result.scalars().all()

    # Hydrate signoffs with template/location names
    pending_signoff_responses = []
    if pending_signoffs:
        loc_ids = list(set(s.location_id for s in pending_signoffs))
        loc_q = select(Location.id, Location.name).where(Location.id.in_(loc_ids))
        loc_names = dict((await db.execute(loc_q)).all())
        for s in pending_signoffs:
            resp = ChecklistSubmissionWithDetails.model_validate(s)
            resp.template_name = s.template.name if s.template else None
            resp.location_name = loc_names.get(s.location_id)
            pending_signoff_responses.append(resp)

    return DashboardStats(
        total_equipment=total_equipment,
        temperature_alerts_today=temperature_alerts_today,
        checklists_due_today=checklists_due_today,
        checklists_completed_today=checklists_completed_today,
        open_incidents=open_incidents,
        pending_corrective_actions=pending_corrective_actions,
        recent_temperatures=recent_temp_responses,
        pending_signoffs=pending_signoff_responses
    )


@router.get("/alerts", response_model=DashboardAlerts)
async def get_dashboard_alerts(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get active alerts and action items"""
    today = date.today()

    # Active temperature alerts
    temp_alerts_query = select(TemperatureLog).where(
        and_(
            TemperatureLog.is_within_range == False,
            TemperatureLog.alert_status == TemperatureAlertStatus.ACTIVE
        )
    ).order_by(TemperatureLog.logged_at.desc()).limit(20)
    if location_id:
        temp_alerts_query = temp_alerts_query.where(TemperatureLog.location_id == location_id)
    result = await db.execute(temp_alerts_query)
    temp_alerts = result.scalars().all()

    # Overdue checklists (in_progress past due)
    overdue_query = select(ChecklistSubmission).options(
        selectinload(ChecklistSubmission.template)
    ).where(
        and_(
            ChecklistSubmission.status == ChecklistStatus.IN_PROGRESS,
            ChecklistSubmission.submission_date < today
        )
    ).limit(20)
    if location_id:
        overdue_query = overdue_query.where(ChecklistSubmission.location_id == location_id)
    result = await db.execute(overdue_query)
    overdue_checklists = result.scalars().all()

    # Open incidents
    incidents_query = select(Incident).where(
        Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.ACTION_REQUIRED])
    ).order_by(Incident.incident_date.desc()).limit(20)
    if location_id:
        incidents_query = incidents_query.where(Incident.location_id == location_id)
    result = await db.execute(incidents_query)
    open_incidents = result.scalars().all()

    # Overdue corrective actions
    overdue_ca_query = select(CorrectiveAction).where(
        and_(
            CorrectiveAction.status.in_([CorrectiveActionStatus.PENDING, CorrectiveActionStatus.IN_PROGRESS]),
            CorrectiveAction.due_date < today
        )
    ).limit(20)
    result = await db.execute(overdue_ca_query)
    overdue_cas = result.scalars().all()

    # Batch-load location names for all entities
    all_loc_ids = set()
    for t in temp_alerts:
        all_loc_ids.add(t.location_id)
    for c in overdue_checklists:
        all_loc_ids.add(c.location_id)
    for i in open_incidents:
        all_loc_ids.add(i.location_id)
    loc_names = {}
    if all_loc_ids:
        loc_q = select(Location.id, Location.name).where(Location.id.in_(list(all_loc_ids)))
        loc_names = dict((await db.execute(loc_q)).all())

    # Hydrate temperature alerts
    temp_alert_responses = []
    for t in temp_alerts:
        resp = TemperatureLogWithDetails.model_validate(t)
        resp.location_name = loc_names.get(t.location_id)
        temp_alert_responses.append(resp)

    # Hydrate overdue checklists
    overdue_checklist_responses = []
    for c in overdue_checklists:
        resp = ChecklistSubmissionWithDetails.model_validate(c)
        resp.template_name = c.template.name if c.template else None
        resp.location_name = loc_names.get(c.location_id)
        overdue_checklist_responses.append(resp)

    # Hydrate open incidents
    incident_responses = []
    for i in open_incidents:
        resp = IncidentWithDetails.model_validate(i)
        resp.location_name = loc_names.get(i.location_id)
        incident_responses.append(resp)

    # Hydrate corrective actions
    ca_responses = [CorrectiveActionResponse.model_validate(ca) for ca in overdue_cas]

    return DashboardAlerts(
        temperature_alerts=temp_alert_responses,
        overdue_checklists=overdue_checklist_responses,
        open_incidents=incident_responses,
        overdue_corrective_actions=ca_responses
    )
