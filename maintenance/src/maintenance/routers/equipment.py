"""Equipment router for Maintenance Service"""
import secrets
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from maintenance.database import get_db
from maintenance.models import Equipment, EquipmentCategory, EquipmentHistory, EquipmentStatus
from maintenance.schemas import (
    EquipmentCreate, EquipmentUpdate, EquipmentResponse,
    EquipmentListResponse, EquipmentDetailResponse,
    EquipmentHistoryResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_qr_code() -> str:
    """Generate unique QR code identifier"""
    return f"EQ-{secrets.token_hex(6).upper()}"


@router.get("", response_model=List[EquipmentListResponse])
async def list_equipment(
    location_id: Optional[int] = None,
    category_id: Optional[int] = None,
    status: Optional[EquipmentStatus] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List all equipment with optional filters"""
    query = select(Equipment).options(selectinload(Equipment.category))

    if location_id:
        query = query.where(Equipment.location_id == location_id)
    if category_id:
        query = query.where(Equipment.category_id == category_id)
    if status:
        query = query.where(Equipment.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Equipment.name.ilike(search_term),
                Equipment.serial_number.ilike(search_term),
                Equipment.model_number.ilike(search_term),
                Equipment.manufacturer.ilike(search_term)
            )
        )

    query = query.order_by(Equipment.name).offset(skip).limit(limit)
    result = await db.execute(query)
    equipment_list = result.scalars().all()

    return [
        EquipmentListResponse(
            id=eq.id,
            name=eq.name,
            category_id=eq.category_id,
            category_name=eq.category.name if eq.category else None,
            location_id=eq.location_id,
            status=eq.status,
            serial_number=eq.serial_number,
            next_maintenance_date=eq.next_maintenance_date,
            qr_code=eq.qr_code
        )
        for eq in equipment_list
    ]


@router.get("/by-qr/{qr_code}", response_model=EquipmentDetailResponse)
async def get_equipment_by_qr(qr_code: str, db: AsyncSession = Depends(get_db)):
    """Get equipment by QR code"""
    query = select(Equipment).options(selectinload(Equipment.category)).where(Equipment.qr_code == qr_code)
    result = await db.execute(query)
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    return EquipmentDetailResponse(
        **{c.name: getattr(equipment, c.name) for c in equipment.__table__.columns},
        category=equipment.category
    )


@router.get("/{equipment_id}", response_model=EquipmentDetailResponse)
async def get_equipment(equipment_id: int, db: AsyncSession = Depends(get_db)):
    """Get equipment by ID"""
    query = select(Equipment).options(selectinload(Equipment.category)).where(Equipment.id == equipment_id)
    result = await db.execute(query)
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    return EquipmentDetailResponse(
        **{c.name: getattr(equipment, c.name) for c in equipment.__table__.columns},
        category=equipment.category
    )


@router.post("", response_model=EquipmentResponse, status_code=201)
async def create_equipment(
    equipment_data: EquipmentCreate,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create new equipment"""
    equipment = Equipment(
        **equipment_data.model_dump(),
        qr_code=generate_qr_code(),
        created_by=user_id
    )
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)

    # Log creation
    history = EquipmentHistory(
        equipment_id=equipment.id,
        changed_by=user_id,
        change_type="created",
        new_value=equipment.name,
        notes="Equipment created"
    )
    db.add(history)
    await db.commit()

    logger.info(f"Created equipment: {equipment.name} (ID: {equipment.id})")
    return equipment


@router.put("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: int,
    equipment_data: EquipmentUpdate,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Update equipment"""
    query = select(Equipment).where(Equipment.id == equipment_id)
    result = await db.execute(query)
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    update_data = equipment_data.model_dump(exclude_unset=True)

    # Track status changes
    if "status" in update_data and update_data["status"] != equipment.status:
        history = EquipmentHistory(
            equipment_id=equipment.id,
            changed_by=user_id,
            change_type="status_change",
            old_value=equipment.status.value if equipment.status else None,
            new_value=update_data["status"].value if update_data["status"] else None
        )
        db.add(history)

    for field, value in update_data.items():
        setattr(equipment, field, value)

    await db.commit()
    await db.refresh(equipment)

    logger.info(f"Updated equipment: {equipment.name} (ID: {equipment.id})")
    return equipment


@router.delete("/{equipment_id}", status_code=204)
async def delete_equipment(equipment_id: int, db: AsyncSession = Depends(get_db)):
    """Delete equipment (soft delete by marking as retired)"""
    query = select(Equipment).where(Equipment.id == equipment_id)
    result = await db.execute(query)
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    equipment.status = EquipmentStatus.RETIRED
    await db.commit()

    logger.info(f"Retired equipment: {equipment.name} (ID: {equipment.id})")


@router.get("/{equipment_id}/history", response_model=List[EquipmentHistoryResponse])
async def get_equipment_history(
    equipment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get equipment history"""
    # Verify equipment exists
    eq_query = select(Equipment.id).where(Equipment.id == equipment_id)
    result = await db.execute(eq_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Equipment not found")

    query = (
        select(EquipmentHistory)
        .where(EquipmentHistory.equipment_id == equipment_id)
        .order_by(EquipmentHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/location/{location_id}/count")
async def get_equipment_count_by_location(location_id: int, db: AsyncSession = Depends(get_db)):
    """Get equipment count by location and status"""
    query = (
        select(Equipment.status, func.count(Equipment.id))
        .where(Equipment.location_id == location_id)
        .group_by(Equipment.status)
    )
    result = await db.execute(query)
    counts = {row[0].value: row[1] for row in result.all()}

    return {
        "location_id": location_id,
        "total": sum(counts.values()),
        "by_status": counts
    }
