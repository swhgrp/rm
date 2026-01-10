"""Work orders router for Maintenance Service"""
import logging
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from maintenance.database import get_db
from maintenance.models import (
    WorkOrder, WorkOrderComment, WorkOrderPart,
    Equipment, Vendor, WorkOrderStatus, WorkOrderPriority
)
from maintenance.schemas import (
    WorkOrderCreate, WorkOrderUpdate, WorkOrderResponse,
    WorkOrderListResponse, WorkOrderDetailResponse,
    WorkOrderCommentCreate, WorkOrderCommentResponse,
    WorkOrderPartCreate, WorkOrderPartResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=List[WorkOrderListResponse])
async def list_work_orders(
    location_id: Optional[int] = None,
    equipment_id: Optional[int] = None,
    status: Optional[WorkOrderStatus] = None,
    priority: Optional[WorkOrderPriority] = None,
    assigned_to: Optional[int] = None,
    include_closed: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List work orders with optional filters"""
    query = select(WorkOrder).options(selectinload(WorkOrder.equipment))

    if location_id:
        query = query.where(WorkOrder.location_id == location_id)
    if equipment_id:
        query = query.where(WorkOrder.equipment_id == equipment_id)
    if status:
        query = query.where(WorkOrder.status == status)
    elif not include_closed:
        query = query.where(
            WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED])
        )
    if priority:
        query = query.where(WorkOrder.priority == priority)
    if assigned_to:
        query = query.where(WorkOrder.assigned_to == assigned_to)

    # Order by priority (critical first) then by reported date
    query = query.order_by(
        WorkOrder.priority.desc(),
        WorkOrder.reported_date.desc()
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return [
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
        for wo in work_orders
    ]


@router.get("/stats")
async def get_work_order_stats(
    location_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get work order statistics"""
    base_query = select(WorkOrder)
    if location_id:
        base_query = base_query.where(WorkOrder.location_id == location_id)

    # Count by status
    status_query = (
        select(WorkOrder.status, func.count(WorkOrder.id))
        .group_by(WorkOrder.status)
    )
    if location_id:
        status_query = status_query.where(WorkOrder.location_id == location_id)
    status_result = await db.execute(status_query)
    status_counts = {row[0].value: row[1] for row in status_result.all()}

    # Count by priority (open only)
    priority_query = (
        select(WorkOrder.priority, func.count(WorkOrder.id))
        .where(WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]))
        .group_by(WorkOrder.priority)
    )
    if location_id:
        priority_query = priority_query.where(WorkOrder.location_id == location_id)
    priority_result = await db.execute(priority_query)
    priority_counts = {row[0].value: row[1] for row in priority_result.all()}

    # Overdue count
    overdue_query = (
        select(func.count(WorkOrder.id))
        .where(
            and_(
                WorkOrder.status.not_in([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]),
                WorkOrder.due_date < date.today()
            )
        )
    )
    if location_id:
        overdue_query = overdue_query.where(WorkOrder.location_id == location_id)
    overdue_result = await db.execute(overdue_query)
    overdue_count = overdue_result.scalar() or 0

    return {
        "by_status": status_counts,
        "by_priority": priority_counts,
        "overdue": overdue_count,
        "total_open": sum(
            count for status, count in status_counts.items()
            if status not in ["completed", "cancelled"]
        )
    }


@router.get("/{work_order_id}", response_model=WorkOrderDetailResponse)
async def get_work_order(work_order_id: int, db: AsyncSession = Depends(get_db)):
    """Get work order details"""
    query = (
        select(WorkOrder)
        .options(
            selectinload(WorkOrder.equipment),
            selectinload(WorkOrder.vendor),
            selectinload(WorkOrder.comments),
            selectinload(WorkOrder.parts_used)
        )
        .where(WorkOrder.id == work_order_id)
    )
    result = await db.execute(query)
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    return WorkOrderDetailResponse(
        id=work_order.id,
        title=work_order.title,
        description=work_order.description,
        equipment_id=work_order.equipment_id,
        equipment_name=work_order.equipment.name if work_order.equipment else None,
        schedule_id=work_order.schedule_id,
        priority=work_order.priority,
        status=work_order.status,
        location_id=work_order.location_id,
        reported_by=work_order.reported_by,
        assigned_to=work_order.assigned_to,
        is_external=work_order.is_external,
        vendor_id=work_order.vendor_id,
        vendor_name=work_order.vendor.name if work_order.vendor else None,
        reported_date=work_order.reported_date,
        due_date=work_order.due_date,
        started_date=work_order.started_date,
        completed_date=work_order.completed_date,
        resolution_notes=work_order.resolution_notes,
        root_cause=work_order.root_cause,
        estimated_cost=work_order.estimated_cost,
        actual_cost=work_order.actual_cost,
        labor_hours=work_order.labor_hours,
        created_at=work_order.created_at,
        updated_at=work_order.updated_at,
        comments=[
            WorkOrderCommentResponse(
                id=c.id,
                work_order_id=c.work_order_id,
                user_id=c.user_id,
                comment=c.comment,
                is_internal=c.is_internal,
                created_at=c.created_at
            )
            for c in work_order.comments
        ],
        parts_used=[
            WorkOrderPartResponse(
                id=p.id,
                work_order_id=p.work_order_id,
                part_name=p.part_name,
                part_number=p.part_number,
                quantity=p.quantity,
                unit_cost=p.unit_cost,
                notes=p.notes,
                created_at=p.created_at
            )
            for p in work_order.parts_used
        ]
    )


@router.post("", response_model=WorkOrderResponse, status_code=201)
async def create_work_order(
    work_order_data: WorkOrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new work order"""
    # Verify equipment exists if specified
    if work_order_data.equipment_id:
        eq_query = select(Equipment.id).where(Equipment.id == work_order_data.equipment_id)
        result = await db.execute(eq_query)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Equipment not found")

    work_order = WorkOrder(**work_order_data.model_dump())
    db.add(work_order)
    await db.commit()
    await db.refresh(work_order)

    logger.info(f"Created work order: {work_order.title} (ID: {work_order.id})")
    return work_order


@router.put("/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: int,
    work_order_data: WorkOrderUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update work order"""
    query = select(WorkOrder).where(WorkOrder.id == work_order_id)
    result = await db.execute(query)
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    update_data = work_order_data.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == WorkOrderStatus.IN_PROGRESS and not work_order.started_date:
            work_order.started_date = datetime.utcnow()
        elif new_status == WorkOrderStatus.COMPLETED and not work_order.completed_date:
            work_order.completed_date = datetime.utcnow()

    for field, value in update_data.items():
        setattr(work_order, field, value)

    await db.commit()
    await db.refresh(work_order)

    logger.info(f"Updated work order: {work_order.title} (ID: {work_order.id})")
    return work_order


@router.post("/{work_order_id}/start", response_model=WorkOrderResponse)
async def start_work_order(work_order_id: int, db: AsyncSession = Depends(get_db)):
    """Start working on a work order"""
    query = select(WorkOrder).where(WorkOrder.id == work_order_id)
    result = await db.execute(query)
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    if work_order.status not in [WorkOrderStatus.OPEN, WorkOrderStatus.ON_HOLD]:
        raise HTTPException(status_code=400, detail="Work order cannot be started")

    work_order.status = WorkOrderStatus.IN_PROGRESS
    work_order.started_date = datetime.utcnow()

    await db.commit()
    await db.refresh(work_order)

    logger.info(f"Started work order: {work_order.title} (ID: {work_order.id})")
    return work_order


@router.post("/{work_order_id}/complete", response_model=WorkOrderResponse)
async def complete_work_order(
    work_order_id: int,
    resolution_notes: Optional[str] = None,
    root_cause: Optional[str] = None,
    actual_cost: Optional[float] = None,
    labor_hours: Optional[float] = None,
    db: AsyncSession = Depends(get_db)
):
    """Complete a work order"""
    query = select(WorkOrder).where(WorkOrder.id == work_order_id)
    result = await db.execute(query)
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    if work_order.status in [WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Work order already closed")

    work_order.status = WorkOrderStatus.COMPLETED
    work_order.completed_date = datetime.utcnow()
    if resolution_notes:
        work_order.resolution_notes = resolution_notes
    if root_cause:
        work_order.root_cause = root_cause
    if actual_cost is not None:
        work_order.actual_cost = actual_cost
    if labor_hours is not None:
        work_order.labor_hours = labor_hours

    await db.commit()
    await db.refresh(work_order)

    logger.info(f"Completed work order: {work_order.title} (ID: {work_order.id})")
    return work_order


@router.delete("/{work_order_id}", status_code=204)
async def delete_work_order(work_order_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel/delete a work order"""
    query = select(WorkOrder).where(WorkOrder.id == work_order_id)
    result = await db.execute(query)
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Soft delete by cancelling
    work_order.status = WorkOrderStatus.CANCELLED
    await db.commit()

    logger.info(f"Cancelled work order: {work_order.title} (ID: {work_order_id})")


# ==================== Comments ====================

@router.get("/{work_order_id}/comments", response_model=List[WorkOrderCommentResponse])
async def list_comments(
    work_order_id: int,
    include_internal: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """List comments for a work order"""
    query = (
        select(WorkOrderComment)
        .where(WorkOrderComment.work_order_id == work_order_id)
    )
    if not include_internal:
        query = query.where(WorkOrderComment.is_internal == False)
    query = query.order_by(WorkOrderComment.created_at)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{work_order_id}/comments", response_model=WorkOrderCommentResponse, status_code=201)
async def add_comment(
    work_order_id: int,
    comment_data: WorkOrderCommentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add comment to work order"""
    # Verify work order exists
    wo_query = select(WorkOrder.id).where(WorkOrder.id == work_order_id)
    result = await db.execute(wo_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Work order not found")

    comment = WorkOrderComment(
        work_order_id=work_order_id,
        user_id=comment_data.user_id,
        comment=comment_data.comment,
        is_internal=comment_data.is_internal
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return comment


# ==================== Parts ====================

@router.get("/{work_order_id}/parts", response_model=List[WorkOrderPartResponse])
async def list_parts(work_order_id: int, db: AsyncSession = Depends(get_db)):
    """List parts used in a work order"""
    query = (
        select(WorkOrderPart)
        .where(WorkOrderPart.work_order_id == work_order_id)
        .order_by(WorkOrderPart.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{work_order_id}/parts", response_model=WorkOrderPartResponse, status_code=201)
async def add_part(
    work_order_id: int,
    part_data: WorkOrderPartCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add part to work order"""
    # Verify work order exists
    wo_query = select(WorkOrder.id).where(WorkOrder.id == work_order_id)
    result = await db.execute(wo_query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Work order not found")

    part = WorkOrderPart(
        work_order_id=work_order_id,
        part_name=part_data.part_name,
        part_number=part_data.part_number,
        quantity=part_data.quantity,
        unit_cost=part_data.unit_cost,
        notes=part_data.notes
    )
    db.add(part)
    await db.commit()
    await db.refresh(part)

    return part


@router.delete("/{work_order_id}/parts/{part_id}", status_code=204)
async def remove_part(
    work_order_id: int,
    part_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove part from work order"""
    query = select(WorkOrderPart).where(
        and_(
            WorkOrderPart.id == part_id,
            WorkOrderPart.work_order_id == work_order_id
        )
    )
    result = await db.execute(query)
    part = result.scalar_one_or_none()

    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    await db.delete(part)
    await db.commit()
