"""Maintenance schedules router for Maintenance Service"""
import logging
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from maintenance.database import get_db
from maintenance.models import MaintenanceSchedule, Equipment, ScheduleFrequency
from maintenance.schemas import (
    MaintenanceScheduleCreate, MaintenanceScheduleUpdate,
    MaintenanceScheduleResponse, MaintenanceScheduleWithEquipment,
    MaintenanceDueItem
)

logger = logging.getLogger(__name__)
router = APIRouter()


def calculate_next_due(frequency: ScheduleFrequency, from_date: date, custom_days: Optional[int] = None) -> date:
    """Calculate next due date based on frequency"""
    intervals = {
        ScheduleFrequency.DAILY: 1,
        ScheduleFrequency.WEEKLY: 7,
        ScheduleFrequency.BIWEEKLY: 14,
        ScheduleFrequency.MONTHLY: 30,
        ScheduleFrequency.QUARTERLY: 90,
        ScheduleFrequency.SEMIANNUAL: 180,
        ScheduleFrequency.ANNUAL: 365,
    }

    if frequency == ScheduleFrequency.CUSTOM:
        days = custom_days or 30
    else:
        days = intervals.get(frequency, 30)

    return from_date + timedelta(days=days)


@router.get("", response_model=List[MaintenanceScheduleWithEquipment])
async def list_schedules(
    equipment_id: Optional[int] = None,
    location_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List maintenance schedules with optional filters"""
    query = select(MaintenanceSchedule).options(selectinload(MaintenanceSchedule.equipment))

    if equipment_id:
        query = query.where(MaintenanceSchedule.equipment_id == equipment_id)
    if location_id:
        query = query.join(Equipment).where(Equipment.location_id == location_id)
    if is_active is not None:
        query = query.where(MaintenanceSchedule.is_active == is_active)

    query = query.order_by(MaintenanceSchedule.next_due).offset(skip).limit(limit)
    result = await db.execute(query)
    schedules = result.scalars().all()

    return [
        MaintenanceScheduleWithEquipment(
            id=s.id,
            equipment_id=s.equipment_id,
            name=s.name,
            description=s.description,
            frequency=s.frequency,
            custom_interval_days=s.custom_interval_days,
            last_performed=s.last_performed,
            next_due=s.next_due,
            estimated_duration_minutes=s.estimated_duration_minutes,
            checklist=s.checklist,
            assigned_to=s.assigned_to,
            vendor_id=s.vendor_id,
            is_external=s.is_external,
            is_active=s.is_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
            equipment_name=s.equipment.name if s.equipment else None,
            equipment_location_id=s.equipment.location_id if s.equipment else None
        )
        for s in schedules
    ]


@router.get("/due", response_model=List[MaintenanceDueItem])
async def get_due_maintenance(
    days_ahead: int = Query(7, ge=0, le=90),
    location_id: Optional[int] = None,
    include_overdue: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Get maintenance items due within specified days"""
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


@router.get("/{schedule_id}", response_model=MaintenanceScheduleWithEquipment)
async def get_schedule(schedule_id: int, db: AsyncSession = Depends(get_db)):
    """Get maintenance schedule by ID"""
    query = (
        select(MaintenanceSchedule)
        .options(selectinload(MaintenanceSchedule.equipment))
        .where(MaintenanceSchedule.id == schedule_id)
    )
    result = await db.execute(query)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return MaintenanceScheduleWithEquipment(
        id=schedule.id,
        equipment_id=schedule.equipment_id,
        name=schedule.name,
        description=schedule.description,
        frequency=schedule.frequency,
        custom_interval_days=schedule.custom_interval_days,
        last_performed=schedule.last_performed,
        next_due=schedule.next_due,
        estimated_duration_minutes=schedule.estimated_duration_minutes,
        checklist=schedule.checklist,
        assigned_to=schedule.assigned_to,
        vendor_id=schedule.vendor_id,
        is_external=schedule.is_external,
        is_active=schedule.is_active,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        equipment_name=schedule.equipment.name if schedule.equipment else None,
        equipment_location_id=schedule.equipment.location_id if schedule.equipment else None
    )


@router.post("", response_model=MaintenanceScheduleResponse, status_code=201)
async def create_schedule(
    schedule_data: MaintenanceScheduleCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new maintenance schedule"""
    # Verify equipment exists
    eq_query = select(Equipment.id).where(Equipment.id == schedule_data.equipment_id)
    result = await db.execute(eq_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Equipment not found")

    schedule = MaintenanceSchedule(**schedule_data.model_dump())
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    logger.info(f"Created maintenance schedule: {schedule.name} (ID: {schedule.id})")
    return schedule


@router.put("/{schedule_id}", response_model=MaintenanceScheduleResponse)
async def update_schedule(
    schedule_id: int,
    schedule_data: MaintenanceScheduleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update maintenance schedule"""
    query = select(MaintenanceSchedule).where(MaintenanceSchedule.id == schedule_id)
    result = await db.execute(query)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    update_data = schedule_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)

    await db.commit()
    await db.refresh(schedule)

    logger.info(f"Updated maintenance schedule: {schedule.name} (ID: {schedule.id})")
    return schedule


@router.post("/{schedule_id}/complete", response_model=MaintenanceScheduleResponse)
async def complete_maintenance(
    schedule_id: int,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Mark maintenance as completed and calculate next due date"""
    query = select(MaintenanceSchedule).where(MaintenanceSchedule.id == schedule_id)
    result = await db.execute(query)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    today = date.today()
    schedule.last_performed = today
    schedule.next_due = calculate_next_due(
        schedule.frequency,
        today,
        schedule.custom_interval_days
    )

    await db.commit()
    await db.refresh(schedule)

    # Update equipment's maintenance dates
    eq_query = select(Equipment).where(Equipment.id == schedule.equipment_id)
    eq_result = await db.execute(eq_query)
    equipment = eq_result.scalar_one_or_none()
    if equipment:
        equipment.last_maintenance_date = today
        # Find next earliest maintenance for this equipment
        next_query = (
            select(MaintenanceSchedule.next_due)
            .where(
                and_(
                    MaintenanceSchedule.equipment_id == equipment.id,
                    MaintenanceSchedule.is_active == True
                )
            )
            .order_by(MaintenanceSchedule.next_due)
            .limit(1)
        )
        next_result = await db.execute(next_query)
        next_date = next_result.scalar_one_or_none()
        equipment.next_maintenance_date = next_date
        await db.commit()

    logger.info(f"Completed maintenance schedule: {schedule.name} (ID: {schedule.id})")
    return schedule


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete maintenance schedule"""
    query = select(MaintenanceSchedule).where(MaintenanceSchedule.id == schedule_id)
    result = await db.execute(query)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()

    logger.info(f"Deleted maintenance schedule: {schedule.name} (ID: {schedule_id})")
