"""Location and shift management router for Food Safety Service

Note: Equipment is managed via the Maintenance service. Temperature-monitored
equipment can be configured via the /temperatures/equipment endpoints.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from food_safety.database import get_db
from food_safety.models import Location, Shift, EquipmentTempThreshold
from food_safety.schemas import (
    LocationCreate, LocationUpdate, LocationResponse,
    ShiftCreate, ShiftUpdate, ShiftResponse,
    EquipmentTempThresholdCreate, EquipmentTempThresholdUpdate, EquipmentTempThresholdResponse
)
from food_safety.services.maintenance_client import maintenance_client

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== Locations ====================

@router.get("", response_model=List[LocationResponse])
async def list_locations(
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List all locations"""
    query = select(Location)
    if is_active is not None:
        query = query.where(Location.is_active == is_active)
    query = query.order_by(Location.name)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get location by ID"""
    query = select(Location).where(Location.id == location_id)
    result = await db.execute(query)
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    return location


@router.post("", response_model=LocationResponse, status_code=201)
async def create_location(
    data: LocationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new location"""
    location = Location(**data.model_dump())
    db.add(location)
    await db.commit()
    await db.refresh(location)

    logger.info(f"Created location: {location.name}")
    return location


@router.put("/{location_id}", response_model=LocationResponse)
async def update_location(
    location_id: int,
    data: LocationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a location"""
    query = select(Location).where(Location.id == location_id)
    result = await db.execute(query)
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)

    await db.commit()
    await db.refresh(location)

    logger.info(f"Updated location: {location.name}")
    return location


# ==================== Shifts ====================

@router.get("/{location_id}/shifts", response_model=List[ShiftResponse])
async def list_shifts(
    location_id: int,
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List shifts for a location"""
    query = select(Shift).where(Shift.location_id == location_id)
    if is_active is not None:
        query = query.where(Shift.is_active == is_active)
    query = query.order_by(Shift.start_time)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{location_id}/shifts", response_model=ShiftResponse, status_code=201)
async def create_shift(
    location_id: int,
    data: ShiftCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a shift for a location"""
    # Verify location exists
    loc_query = select(Location.id).where(Location.id == location_id)
    result = await db.execute(loc_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Location not found")

    shift_data = data.model_dump()
    shift_data["location_id"] = location_id
    shift = Shift(**shift_data)
    db.add(shift)
    await db.commit()
    await db.refresh(shift)

    logger.info(f"Created shift: {shift.name} for location {location_id}")
    return shift


@router.put("/shifts/{shift_id}", response_model=ShiftResponse)
async def update_shift(
    shift_id: int,
    data: ShiftUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a shift"""
    query = select(Shift).where(Shift.id == shift_id)
    result = await db.execute(query)
    shift = result.scalar_one_or_none()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(shift, field, value)

    await db.commit()
    await db.refresh(shift)

    logger.info(f"Updated shift: {shift.name}")
    return shift


# ==================== Equipment Temperature Thresholds ====================

@router.get("/equipment-thresholds", response_model=List[EquipmentTempThresholdResponse])
async def list_equipment_thresholds(
    location_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List equipment temperature threshold overrides"""
    query = select(EquipmentTempThreshold)

    if location_id:
        query = query.where(EquipmentTempThreshold.location_id == location_id)
    if is_active is not None:
        query = query.where(EquipmentTempThreshold.is_active == is_active)

    query = query.order_by(EquipmentTempThreshold.equipment_name)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/equipment-thresholds", response_model=EquipmentTempThresholdResponse, status_code=201)
async def create_equipment_threshold(
    data: EquipmentTempThresholdCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create or update temperature threshold for equipment from Maintenance service"""
    # Check if threshold already exists for this maintenance equipment
    existing_query = select(EquipmentTempThreshold).where(
        EquipmentTempThreshold.maintenance_equipment_id == data.maintenance_equipment_id
    )
    result = await db.execute(existing_query)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing threshold
        update_data = data.model_dump(exclude={"maintenance_equipment_id"})
        for field, value in update_data.items():
            setattr(existing, field, value)
        await db.commit()
        await db.refresh(existing)
        logger.info(f"Updated equipment threshold: {existing.equipment_name}")
        return existing

    # Create new threshold
    threshold = EquipmentTempThreshold(**data.model_dump())
    db.add(threshold)
    await db.commit()
    await db.refresh(threshold)

    logger.info(f"Created equipment threshold: {threshold.equipment_name}")
    return threshold


@router.put("/equipment-thresholds/{threshold_id}", response_model=EquipmentTempThresholdResponse)
async def update_equipment_threshold(
    threshold_id: int,
    data: EquipmentTempThresholdUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update equipment temperature threshold"""
    query = select(EquipmentTempThreshold).where(EquipmentTempThreshold.id == threshold_id)
    result = await db.execute(query)
    threshold = result.scalar_one_or_none()

    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(threshold, field, value)

    await db.commit()
    await db.refresh(threshold)

    logger.info(f"Updated equipment threshold: {threshold.equipment_name}")
    return threshold


@router.delete("/equipment-thresholds/{threshold_id}")
async def delete_equipment_threshold(
    threshold_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete equipment temperature threshold (remove override)"""
    query = select(EquipmentTempThreshold).where(EquipmentTempThreshold.id == threshold_id)
    result = await db.execute(query)
    threshold = result.scalar_one_or_none()

    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    name = threshold.equipment_name
    await db.delete(threshold)
    await db.commit()

    logger.info(f"Deleted equipment threshold: {name}")
    return {"status": "deleted", "equipment_name": name}
