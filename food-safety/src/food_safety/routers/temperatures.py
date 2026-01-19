"""Temperature logging router for Food Safety Service"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from food_safety.database import get_db
from food_safety.models import (
    TemperatureLog, TemperatureThreshold, TemperatureAlertStatus,
    EquipmentTempThreshold, Location
)
from food_safety.schemas import (
    TemperatureLogCreate, TemperatureLogResponse, TemperatureLogWithDetails,
    TemperatureThresholdCreate, TemperatureThresholdUpdate, TemperatureThresholdResponse,
    TemperatureAlertAcknowledge
)
from food_safety.services.maintenance_client import maintenance_client

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== Temperature Thresholds ====================

@router.get("/thresholds", response_model=List[TemperatureThresholdResponse])
async def list_thresholds(
    db: AsyncSession = Depends(get_db)
):
    """List all temperature thresholds"""
    query = select(TemperatureThreshold).order_by(TemperatureThreshold.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/thresholds", response_model=TemperatureThresholdResponse, status_code=201)
async def create_threshold(
    data: TemperatureThresholdCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new temperature threshold"""
    threshold = TemperatureThreshold(**data.model_dump())
    db.add(threshold)
    await db.commit()
    await db.refresh(threshold)

    logger.info(f"Created temperature threshold: {threshold.name}")
    return threshold


@router.put("/thresholds/{threshold_id}", response_model=TemperatureThresholdResponse)
async def update_threshold(
    threshold_id: int,
    data: TemperatureThresholdUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a temperature threshold"""
    query = select(TemperatureThreshold).where(TemperatureThreshold.id == threshold_id)
    result = await db.execute(query)
    threshold = result.scalar_one_or_none()

    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(threshold, field, value)

    await db.commit()
    await db.refresh(threshold)

    logger.info(f"Updated temperature threshold: {threshold.name}")
    return threshold


# ==================== Equipment (from Maintenance) ====================

@router.get("/equipment")
async def list_equipment(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List temperature-monitored equipment from Maintenance service"""
    # Get equipment from Maintenance service
    equipment_list = await maintenance_client.get_temperature_equipment(location_id=location_id)

    # Get local threshold overrides
    override_query = select(EquipmentTempThreshold)
    if location_id:
        override_query = override_query.where(EquipmentTempThreshold.location_id == location_id)
    override_result = await db.execute(override_query)
    overrides = {o.maintenance_equipment_id: o for o in override_result.scalars().all()}

    # Get default thresholds by equipment type
    default_query = select(TemperatureThreshold)
    default_result = await db.execute(default_query)
    defaults = {t.equipment_type: t for t in default_result.scalars().all()}

    # Merge equipment with local overrides and defaults
    result = []
    for eq in equipment_list:
        override = overrides.get(eq.id)
        default = defaults.get(eq.equipment_type)

        # Priority: override > equipment specs > default by type
        min_temp = None
        max_temp = None
        temp_unit = eq.temp_unit
        threshold_source = None

        if override and override.min_temp is not None:
            min_temp = float(override.min_temp)
            max_temp = float(override.max_temp) if override.max_temp else None
            temp_unit = override.temp_unit
            threshold_source = "override"
        elif eq.min_temp is not None:
            min_temp = float(eq.min_temp)
            max_temp = float(eq.max_temp) if eq.max_temp else None
            threshold_source = "equipment"
        elif default:
            min_temp = float(default.min_temp)
            max_temp = float(default.max_temp)
            temp_unit = default.temp_unit
            threshold_source = "default"

        result.append({
            "id": eq.id,
            "name": eq.name,
            "location_id": eq.location_id,
            "category_name": eq.category_name,
            "equipment_type": eq.equipment_type,
            "status": eq.status,
            "serial_number": eq.serial_number,
            "qr_code": eq.qr_code,
            "min_temp": min_temp,
            "max_temp": max_temp,
            "temp_unit": temp_unit,
            "has_override": override is not None,
            "threshold_id": override.id if override else None,  # ID needed for delete/update
            "threshold_source": threshold_source  # 'override', 'equipment', 'default', or None
        })

    return result


@router.get("/equipment/{equipment_id}")
async def get_equipment(
    equipment_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get specific equipment from Maintenance service"""
    equipment = await maintenance_client.get_equipment(equipment_id)

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found in Maintenance service")

    # Check for local threshold override
    override_query = select(EquipmentTempThreshold).where(
        EquipmentTempThreshold.maintenance_equipment_id == equipment_id
    )
    override_result = await db.execute(override_query)
    override = override_result.scalar_one_or_none()

    # Get default threshold for equipment type
    default_query = select(TemperatureThreshold).where(
        TemperatureThreshold.equipment_type == equipment.equipment_type
    )
    default_result = await db.execute(default_query)
    default = default_result.scalar_one_or_none()

    # Priority: override > equipment specs > default by type
    min_temp = None
    max_temp = None
    temp_unit = equipment.temp_unit
    threshold_source = None

    if override and override.min_temp is not None:
        min_temp = float(override.min_temp)
        max_temp = float(override.max_temp) if override.max_temp else None
        temp_unit = override.temp_unit
        threshold_source = "override"
    elif equipment.min_temp is not None:
        min_temp = float(equipment.min_temp)
        max_temp = float(equipment.max_temp) if equipment.max_temp else None
        threshold_source = "equipment"
    elif default:
        min_temp = float(default.min_temp)
        max_temp = float(default.max_temp)
        temp_unit = default.temp_unit
        threshold_source = "default"

    return {
        "id": equipment.id,
        "name": equipment.name,
        "location_id": equipment.location_id,
        "category_name": equipment.category_name,
        "equipment_type": equipment.equipment_type,
        "status": equipment.status,
        "serial_number": equipment.serial_number,
        "model_number": equipment.model_number,
        "manufacturer": equipment.manufacturer,
        "qr_code": equipment.qr_code,
        "min_temp": min_temp,
        "max_temp": max_temp,
        "temp_unit": temp_unit,
        "has_override": override is not None,
        "threshold_id": override.id if override else None,
        "threshold_source": threshold_source
    }


# ==================== Temperature Logs ====================

@router.get("", response_model=List[TemperatureLogWithDetails])
async def list_temperature_logs(
    location_id: Optional[int] = Query(None),
    equipment_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    alerts_only: bool = Query(False),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List temperature logs with optional filters"""
    query = select(TemperatureLog)

    if location_id:
        query = query.where(TemperatureLog.location_id == location_id)
    if equipment_id:
        query = query.where(TemperatureLog.maintenance_equipment_id == equipment_id)
    if start_date:
        query = query.where(TemperatureLog.logged_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.where(TemperatureLog.logged_at <= datetime.combine(end_date, datetime.max.time()))
    if alerts_only:
        query = query.where(TemperatureLog.is_within_range == False)

    query = query.order_by(TemperatureLog.logged_at.desc()).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    # Get location names
    loc_ids = list(set(log.location_id for log in logs))
    location_names = {}

    if loc_ids:
        loc_query = select(Location).where(Location.id.in_(loc_ids))
        loc_result = await db.execute(loc_query)
        location_names = {loc.id: loc.name for loc in loc_result.scalars().all()}

    # Build response with details
    response = []
    for log in logs:
        log_dict = TemperatureLogWithDetails.model_validate(log)
        log_dict.equipment_name = log.equipment_name
        log_dict.location_name = location_names.get(log.location_id)
        response.append(log_dict)

    return response


@router.get("/alerts", response_model=List[TemperatureLogWithDetails])
async def list_active_alerts(
    location_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List active temperature alerts"""
    query = select(TemperatureLog).where(
        and_(
            TemperatureLog.is_within_range == False,
            TemperatureLog.alert_status == TemperatureAlertStatus.ACTIVE
        )
    )

    if location_id:
        query = query.where(TemperatureLog.location_id == location_id)

    query = query.order_by(TemperatureLog.logged_at.desc())
    result = await db.execute(query)
    logs = result.scalars().all()

    # Get location names
    loc_ids = list(set(log.location_id for log in logs))
    location_names = {}

    if loc_ids:
        loc_query = select(Location).where(Location.id.in_(loc_ids))
        loc_result = await db.execute(loc_query)
        location_names = {loc.id: loc.name for loc in loc_result.scalars().all()}

    response = []
    for log in logs:
        log_dict = TemperatureLogWithDetails.model_validate(log)
        log_dict.equipment_name = log.equipment_name
        log_dict.location_name = location_names.get(log.location_id)
        response.append(log_dict)

    return response


@router.post("", response_model=TemperatureLogResponse, status_code=201)
async def log_temperature(
    data: TemperatureLogCreate,
    db: AsyncSession = Depends(get_db)
):
    """Log a temperature reading"""
    # Get equipment from Maintenance service
    equipment = await maintenance_client.get_equipment(data.equipment_id)

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found in Maintenance service")

    # Get local threshold override if exists
    override_query = select(EquipmentTempThreshold).where(
        EquipmentTempThreshold.maintenance_equipment_id == data.equipment_id
    )
    override_result = await db.execute(override_query)
    override = override_result.scalar_one_or_none()

    # Determine thresholds
    min_threshold = None
    max_threshold = None

    # Priority: local override > equipment specs > default by type
    if override and override.min_temp is not None:
        min_threshold = override.min_temp
    elif equipment.min_temp is not None:
        min_threshold = equipment.min_temp
    else:
        # Fall back to default thresholds for equipment type
        threshold_query = select(TemperatureThreshold).where(
            TemperatureThreshold.equipment_type == equipment.equipment_type
        )
        threshold_result = await db.execute(threshold_query)
        default_threshold = threshold_result.scalar_one_or_none()
        if default_threshold:
            min_threshold = default_threshold.min_temp

    if override and override.max_temp is not None:
        max_threshold = override.max_temp
    elif equipment.max_temp is not None:
        max_threshold = equipment.max_temp
    else:
        threshold_query = select(TemperatureThreshold).where(
            TemperatureThreshold.equipment_type == equipment.equipment_type
        )
        threshold_result = await db.execute(threshold_query)
        default_threshold = threshold_result.scalar_one_or_none()
        if default_threshold:
            max_threshold = default_threshold.max_temp

    # Check if within range
    is_within_range = True
    if min_threshold is not None and data.temperature < min_threshold:
        is_within_range = False
    if max_threshold is not None and data.temperature > max_threshold:
        is_within_range = False

    # Get location from local DB using inventory_location_id
    location_query = select(Location).where(Location.inventory_location_id == equipment.location_id)
    location_result = await db.execute(location_query)
    location = location_result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not configured for food safety")

    # Create log entry
    log = TemperatureLog(
        maintenance_equipment_id=data.equipment_id,
        equipment_name=equipment.name,
        location_id=location.id,
        temperature=data.temperature,
        temp_unit=data.temp_unit,
        min_threshold=min_threshold,
        max_threshold=max_threshold,
        is_within_range=is_within_range,
        alert_status=None if is_within_range else TemperatureAlertStatus.ACTIVE,
        logged_by=data.logged_by,
        shift_id=data.shift_id,
        notes=data.notes,
        corrective_action=data.corrective_action
    )

    db.add(log)
    await db.commit()
    await db.refresh(log)

    if not is_within_range:
        logger.warning(
            f"Temperature alert: Equipment {equipment.name} logged {data.temperature}°{data.temp_unit} "
            f"(range: {min_threshold}-{max_threshold}°{data.temp_unit})"
        )
        # TODO: Send email alert

    logger.info(f"Logged temperature: {data.temperature}°{data.temp_unit} for equipment {equipment.name}")
    return log


@router.post("/{log_id}/acknowledge", response_model=TemperatureLogResponse)
async def acknowledge_alert(
    log_id: int,
    data: TemperatureAlertAcknowledge,
    db: AsyncSession = Depends(get_db)
):
    """Acknowledge a temperature alert"""
    query = select(TemperatureLog).where(TemperatureLog.id == log_id)
    result = await db.execute(query)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Temperature log not found")

    if log.is_within_range:
        raise HTTPException(status_code=400, detail="This reading is within range, no alert to acknowledge")

    log.alert_status = TemperatureAlertStatus.ACKNOWLEDGED
    log.alert_acknowledged_by = data.acknowledged_by
    log.alert_acknowledged_at = get_now()
    log.alert_notes = data.notes
    if data.corrective_action:
        log.corrective_action = data.corrective_action

    await db.commit()
    await db.refresh(log)

    logger.info(f"Acknowledged temperature alert: log {log_id}")
    return log


@router.post("/{log_id}/resolve", response_model=TemperatureLogResponse)
async def resolve_alert(
    log_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Mark a temperature alert as resolved"""
    query = select(TemperatureLog).where(TemperatureLog.id == log_id)
    result = await db.execute(query)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Temperature log not found")

    if log.alert_status != TemperatureAlertStatus.ACKNOWLEDGED:
        raise HTTPException(status_code=400, detail="Alert must be acknowledged before resolving")

    log.alert_status = TemperatureAlertStatus.RESOLVED

    await db.commit()
    await db.refresh(log)

    logger.info(f"Resolved temperature alert: log {log_id}")
    return log


@router.get("/equipment/{equipment_id}/history", response_model=List[TemperatureLogResponse])
async def get_equipment_temperature_history(
    equipment_id: int,
    days: int = Query(7, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Get temperature history for specific equipment"""
    start_date = get_now() - timedelta(days=days)

    query = select(TemperatureLog).where(
        and_(
            TemperatureLog.maintenance_equipment_id == equipment_id,
            TemperatureLog.logged_at >= start_date
        )
    ).order_by(TemperatureLog.logged_at.desc())

    result = await db.execute(query)
    return result.scalars().all()
