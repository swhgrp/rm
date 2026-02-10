"""Equipment router for Maintenance Service"""
import secrets
import logging
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
import httpx

from maintenance.database import get_db
from maintenance.models import (
    Equipment, EquipmentCategory, EquipmentHistory, EquipmentStatus,
    WorkOrder, WorkOrderStatus, MaintenanceSchedule, MaintenanceLog, MaintenanceDocument
)
from maintenance.schemas import (
    EquipmentCreate, EquipmentUpdate, EquipmentResponse,
    EquipmentListResponse, EquipmentDetailResponse,
    EquipmentHistoryResponse
)
from pydantic import BaseModel
from datetime import datetime as dt
from maintenance.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_location_names() -> Dict[int, str]:
    """Fetch location names from inventory service"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.INVENTORY_SERVICE_URL}/api/locations/_sync",
                params={"include_inactive": "false"}
            )
            if response.status_code == 200:
                locations = response.json()
                return {loc["id"]: loc["name"] for loc in locations}
    except Exception as e:
        logger.warning(f"Failed to fetch location names: {e}")
    return {}


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

    # Fetch location names
    location_names = await get_location_names()

    return [
        EquipmentListResponse(
            id=eq.id,
            name=eq.name,
            description=eq.description,
            category_id=eq.category_id,
            category_name=eq.category.name if eq.category else None,
            location_id=eq.location_id,
            location_name=location_names.get(eq.location_id),
            status=eq.status,
            serial_number=eq.serial_number,
            next_maintenance_date=eq.next_maintenance_date,
            qr_code=eq.qr_code,
            ownership_type=eq.ownership_type,
            owner_name=eq.owner_name
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


class HistoryDocumentItem(BaseModel):
    id: int
    file_name: str
    file_size: int | None = None
    mime_type: str | None = None


class CombinedHistoryItem(BaseModel):
    """Combined history item for equipment history + work orders + maintenance logs"""
    id: int
    equipment_id: int
    changed_by: int | None = None
    changed_by_name: str | None = None
    change_type: str
    old_value: str | None = None
    new_value: str | None = None
    notes: str | None = None
    created_at: dt
    documents: List[HistoryDocumentItem] = []

    class Config:
        from_attributes = True


@router.get("/{equipment_id}/history", response_model=List[CombinedHistoryItem])
async def get_equipment_history(
    equipment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get equipment history including completed work orders"""
    # Verify equipment exists
    eq_query = select(Equipment.id).where(Equipment.id == equipment_id)
    result = await db.execute(eq_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Get equipment history records
    history_query = (
        select(EquipmentHistory)
        .where(EquipmentHistory.equipment_id == equipment_id)
    )
    history_result = await db.execute(history_query)
    history_records = history_result.scalars().all()

    # Get completed work orders for this equipment
    wo_query = (
        select(WorkOrder)
        .where(
            WorkOrder.equipment_id == equipment_id,
            WorkOrder.status.in_([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED])
        )
    )
    wo_result = await db.execute(wo_query)
    work_orders = wo_result.scalars().all()

    # Get maintenance logs for this equipment (through schedules)
    schedule_id_query = (
        select(MaintenanceSchedule.id)
        .where(MaintenanceSchedule.equipment_id == equipment_id)
    )
    schedule_result = await db.execute(schedule_id_query)
    schedule_ids = [s for s in schedule_result.scalars().all()]

    maintenance_logs = []
    if schedule_ids:
        log_query = (
            select(MaintenanceLog)
            .options(
                selectinload(MaintenanceLog.documents),
                selectinload(MaintenanceLog.schedule)
            )
            .where(MaintenanceLog.schedule_id.in_(schedule_ids))
        )
        log_result = await db.execute(log_query)
        maintenance_logs = log_result.scalars().all()

    logger.info(
        f"Equipment {equipment_id}: Found {len(history_records)} history records, "
        f"{len(work_orders)} work orders, {len(maintenance_logs)} maintenance logs"
    )

    # Combine and format results
    combined = []

    # Add history records
    for h in history_records:
        combined.append(CombinedHistoryItem(
            id=h.id,
            equipment_id=h.equipment_id,
            changed_by=h.changed_by,
            change_type=h.change_type,
            old_value=h.old_value,
            new_value=h.new_value,
            notes=h.notes,
            created_at=h.created_at
        ))

    # Add work orders as history items
    for wo in work_orders:
        change_type = "work_order_cancelled" if wo.status == WorkOrderStatus.CANCELLED else "work_order"
        notes = wo.title
        if wo.resolution_notes:
            notes = f"{wo.title}: {wo.resolution_notes}"

        combined.append(CombinedHistoryItem(
            id=wo.id + 100000,  # Offset to avoid ID collision
            equipment_id=equipment_id,
            changed_by=wo.assigned_to,
            change_type=change_type,
            old_value=None,
            new_value=wo.status.value if wo.status else None,
            notes=notes,
            created_at=wo.completed_date or wo.created_at
        ))

    # Add maintenance log entries
    for log in maintenance_logs:
        schedule_name = log.schedule.name if log.schedule else "Maintenance"
        notes = schedule_name
        if log.notes:
            notes = f"{schedule_name}: {log.notes}"

        docs = [
            HistoryDocumentItem(
                id=doc.id,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
            )
            for doc in (log.documents or [])
        ]

        from datetime import datetime as datetime_mod
        log_datetime = datetime_mod.combine(log.completed_date, datetime_mod.min.time())

        combined.append(CombinedHistoryItem(
            id=log.id + 200000,  # Offset to avoid ID collision
            equipment_id=equipment_id,
            changed_by=None,
            change_type="maintenance",
            old_value=None,
            new_value=str(log.completed_date),
            notes=notes,
            created_at=log_datetime,
            documents=docs,
        ))

    # Sort by created_at descending and apply pagination
    combined.sort(key=lambda x: x.created_at, reverse=True)
    return combined[skip:skip + limit]


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
