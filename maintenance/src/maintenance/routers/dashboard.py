"""Dashboard router for Maintenance Service"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from maintenance.database import get_db
from maintenance.models import (
    Equipment, MaintenanceSchedule, MaintenanceLog, WorkOrder,
    EquipmentStatus, WorkOrderStatus, WorkOrderPriority
)
from maintenance.schemas import (
    DashboardStats, WorkOrderListResponse, MaintenanceDueItem
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics"""

    # Equipment count by status
    eq_query = select(Equipment.status, func.count(Equipment.id)).group_by(Equipment.status)
    if location_id:
        eq_query = eq_query.where(Equipment.location_id == location_id)
    eq_result = await db.execute(eq_query)
    equipment_by_status = {row[0].value: row[1] for row in eq_result.all()}
    total_equipment = sum(equipment_by_status.values())

    # Open work orders count
    open_wo_query = select(func.count(WorkOrder.id)).where(
        WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED])
    )
    if location_id:
        open_wo_query = open_wo_query.where(WorkOrder.location_id == location_id)
    open_wo_result = await db.execute(open_wo_query)
    open_work_orders = open_wo_result.scalar() or 0

    # Work orders by priority (open only)
    wo_priority_query = (
        select(WorkOrder.priority, func.count(WorkOrder.id))
        .where(WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]))
        .group_by(WorkOrder.priority)
    )
    if location_id:
        wo_priority_query = wo_priority_query.where(WorkOrder.location_id == location_id)
    wo_priority_result = await db.execute(wo_priority_query)
    work_orders_by_priority = {row[0].value: row[1] for row in wo_priority_result.all()}

    # Overdue maintenance
    today = date.today()
    overdue_query = (
        select(func.count(MaintenanceSchedule.id))
        .where(
            and_(
                MaintenanceSchedule.is_active == True,
                MaintenanceSchedule.next_due < today
            )
        )
    )
    if location_id:
        overdue_query = overdue_query.join(Equipment).where(Equipment.location_id == location_id)
    overdue_result = await db.execute(overdue_query)
    overdue_maintenance = overdue_result.scalar() or 0

    # Upcoming maintenance (7 days)
    upcoming_query = (
        select(func.count(MaintenanceSchedule.id))
        .where(
            and_(
                MaintenanceSchedule.is_active == True,
                MaintenanceSchedule.next_due >= today,
                MaintenanceSchedule.next_due <= today + timedelta(days=7)
            )
        )
    )
    if location_id:
        upcoming_query = upcoming_query.join(Equipment).where(Equipment.location_id == location_id)
    upcoming_result = await db.execute(upcoming_query)
    upcoming_maintenance_7_days = upcoming_result.scalar() or 0

    # Recent work orders
    recent_wo_query = (
        select(WorkOrder)
        .options(selectinload(WorkOrder.equipment))
        .where(WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]))
        .order_by(WorkOrder.priority.desc(), WorkOrder.reported_date.desc())
        .limit(10)
    )
    if location_id:
        recent_wo_query = recent_wo_query.where(WorkOrder.location_id == location_id)
    recent_wo_result = await db.execute(recent_wo_query)
    recent_work_orders = [
        WorkOrderListResponse(
            id=wo.id,
            title=wo.title,
            equipment_id=wo.equipment_id,
            equipment_name=wo.equipment.name if wo.equipment else None,
            location_id=wo.location_id,
            priority=wo.priority,
            status=wo.status,
            assigned_to=wo.assigned_to,
            reported_date=wo.reported_date,
            due_date=wo.due_date
        )
        for wo in recent_wo_result.scalars().all()
    ]

    return DashboardStats(
        total_equipment=total_equipment,
        equipment_by_status=equipment_by_status,
        open_work_orders=open_work_orders,
        work_orders_by_priority=work_orders_by_priority,
        overdue_maintenance=overdue_maintenance,
        upcoming_maintenance_7_days=upcoming_maintenance_7_days,
        recent_work_orders=recent_work_orders
    )


@router.get("/maintenance-due", response_model=List[MaintenanceDueItem])
async def get_maintenance_due(
    days_ahead: int = Query(7, ge=0, le=90),
    location_id: Optional[int] = None,
    include_overdue: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Get maintenance items due soon"""
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    query = (
        select(MaintenanceSchedule)
        .options(selectinload(MaintenanceSchedule.equipment))
        .where(MaintenanceSchedule.is_active == True)
    )

    if include_overdue:
        query = query.where(MaintenanceSchedule.next_due <= end_date)
    else:
        query = query.where(
            and_(
                MaintenanceSchedule.next_due >= today,
                MaintenanceSchedule.next_due <= end_date
            )
        )

    if location_id:
        query = query.join(Equipment).where(Equipment.location_id == location_id)

    query = query.order_by(MaintenanceSchedule.next_due)
    result = await db.execute(query)
    schedules = result.scalars().all()

    return [
        MaintenanceDueItem(
            schedule_id=s.id,
            schedule_name=s.name,
            equipment_id=s.equipment_id,
            equipment_name=s.equipment.name if s.equipment else "Unknown",
            location_id=s.equipment.location_id if s.equipment else 0,
            next_due=s.next_due,
            days_until_due=(s.next_due - today).days,
            frequency=s.frequency
        )
        for s in schedules
    ]


@router.get("/equipment-status")
async def get_equipment_status_summary(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get equipment status summary by location"""
    query = (
        select(
            Equipment.location_id,
            Equipment.status,
            func.count(Equipment.id)
        )
        .group_by(Equipment.location_id, Equipment.status)
    )
    if location_id:
        query = query.where(Equipment.location_id == location_id)

    result = await db.execute(query)
    rows = result.all()

    # Organize by location
    by_location = {}
    for loc_id, status, count in rows:
        if loc_id not in by_location:
            by_location[loc_id] = {"total": 0, "by_status": {}}
        by_location[loc_id]["by_status"][status.value] = count
        by_location[loc_id]["total"] += count

    return by_location


@router.get("/alerts")
async def get_alerts(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get system alerts (overdue maintenance, critical work orders, etc.)"""
    today = date.today()
    alerts = []

    # Overdue maintenance
    overdue_query = (
        select(MaintenanceSchedule)
        .options(selectinload(MaintenanceSchedule.equipment))
        .where(
            and_(
                MaintenanceSchedule.is_active == True,
                MaintenanceSchedule.next_due < today
            )
        )
        .order_by(MaintenanceSchedule.next_due)
        .limit(10)
    )
    if location_id:
        overdue_query = overdue_query.join(Equipment).where(Equipment.location_id == location_id)
    overdue_result = await db.execute(overdue_query)
    for s in overdue_result.scalars().all():
        days_overdue = (today - s.next_due).days
        alerts.append({
            "type": "overdue_maintenance",
            "severity": "high" if days_overdue > 7 else "medium",
            "message": f"Maintenance overdue: {s.name} for {s.equipment.name if s.equipment else 'Unknown'}",
            "days_overdue": days_overdue,
            "schedule_id": s.id,
            "equipment_id": s.equipment_id
        })

    # Critical work orders
    critical_query = (
        select(WorkOrder)
        .where(
            and_(
                WorkOrder.priority == WorkOrderPriority.CRITICAL,
                WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED])
            )
        )
        .order_by(WorkOrder.reported_date)
        .limit(10)
    )
    if location_id:
        critical_query = critical_query.where(WorkOrder.location_id == location_id)
    critical_result = await db.execute(critical_query)
    for wo in critical_result.scalars().all():
        alerts.append({
            "type": "critical_work_order",
            "severity": "critical",
            "message": f"Critical work order: {wo.title}",
            "work_order_id": wo.id,
            "reported_date": wo.reported_date.isoformat()
        })

    # Overdue work orders
    overdue_wo_query = (
        select(WorkOrder)
        .where(
            and_(
                WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]),
                WorkOrder.due_date < today
            )
        )
        .order_by(WorkOrder.due_date)
        .limit(10)
    )
    if location_id:
        overdue_wo_query = overdue_wo_query.where(WorkOrder.location_id == location_id)
    overdue_wo_result = await db.execute(overdue_wo_query)
    for wo in overdue_wo_result.scalars().all():
        days_overdue = (today - wo.due_date).days
        alerts.append({
            "type": "overdue_work_order",
            "severity": "high" if days_overdue > 3 else "medium",
            "message": f"Work order overdue: {wo.title}",
            "days_overdue": days_overdue,
            "work_order_id": wo.id
        })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda x: severity_order.get(x["severity"], 4))

    return {"alerts": alerts, "count": len(alerts)}


@router.get("/recent-activity")
async def get_recent_activity(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get recent activity across the maintenance system"""
    from datetime import datetime
    activities = []

    # Recent maintenance completions
    log_query = (
        select(MaintenanceLog)
        .options(
            selectinload(MaintenanceLog.schedule).selectinload(MaintenanceSchedule.equipment)
        )
        .order_by(MaintenanceLog.created_at.desc())
        .limit(10)
    )
    if location_id:
        log_query = (
            log_query
            .join(MaintenanceSchedule)
            .join(Equipment)
            .where(Equipment.location_id == location_id)
        )
    log_result = await db.execute(log_query)
    for log in log_result.scalars().all():
        eq = log.schedule.equipment if log.schedule else None
        eq_name = eq.name if eq else "Unknown"
        schedule_name = log.schedule.name if log.schedule else "Unknown"
        location_id_val = eq.location_id if eq else None
        activities.append({
            "type": "maintenance_completed",
            "title": f"{schedule_name}",
            "subtitle": eq_name,
            "location_id": location_id_val,
            "timestamp": log.created_at.isoformat(),
            "completed_date": log.completed_date.isoformat(),
        })

    # Recent work order activity (created or completed in last 30 days)
    cutoff = date.today() - timedelta(days=30)
    wo_query = (
        select(WorkOrder)
        .options(selectinload(WorkOrder.equipment))
        .where(WorkOrder.reported_date >= datetime.combine(cutoff, datetime.min.time()))
        .order_by(WorkOrder.reported_date.desc())
        .limit(10)
    )
    if location_id:
        wo_query = wo_query.where(WorkOrder.location_id == location_id)
    wo_result = await db.execute(wo_query)
    for wo in wo_result.scalars().all():
        eq_name = wo.equipment.name if wo.equipment else "General"
        if wo.status == WorkOrderStatus.COMPLETED:
            activities.append({
                "type": "work_order_completed",
                "title": wo.title,
                "subtitle": eq_name,
                "location_id": wo.location_id,
                "timestamp": (wo.completed_date or wo.updated_at or wo.reported_date).isoformat(),
            })
        else:
            activities.append({
                "type": "work_order_created",
                "title": wo.title,
                "subtitle": eq_name,
                "location_id": wo.location_id,
                "timestamp": wo.reported_date.isoformat(),
            })

    # Sort all by timestamp desc and limit
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:10]
