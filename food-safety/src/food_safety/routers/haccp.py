"""HACCP management router for Food Safety Service"""
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from food_safety.database import get_db
from food_safety.models import HACCPPlan, CriticalControlPoint, Location
from food_safety.schemas import (
    HACCPPlanCreate, HACCPPlanUpdate, HACCPPlanResponse, HACCPPlanWithCCPs,
    HACCPPlanApprove, CriticalControlPointCreate, CriticalControlPointUpdate,
    CriticalControlPointResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plans", response_model=List[HACCPPlanResponse])
async def list_plans(
    location_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List HACCP plans"""
    query = select(HACCPPlan)

    if location_id:
        query = query.where(HACCPPlan.location_id == location_id)
    if is_active is not None:
        query = query.where(HACCPPlan.is_active == is_active)

    query = query.order_by(HACCPPlan.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/plans/{plan_id}", response_model=HACCPPlanWithCCPs)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get HACCP plan with critical control points"""
    query = select(HACCPPlan).options(
        selectinload(HACCPPlan.critical_control_points)
    ).where(HACCPPlan.id == plan_id)

    result = await db.execute(query)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="HACCP plan not found")

    # Get location name
    loc_query = select(Location.name).where(Location.id == plan.location_id)
    loc_result = await db.execute(loc_query)
    location_name = loc_result.scalar_one_or_none()

    response = HACCPPlanWithCCPs.model_validate(plan)
    response.location_name = location_name
    return response


@router.post("/plans", response_model=HACCPPlanWithCCPs, status_code=201)
async def create_plan(
    data: HACCPPlanCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new HACCP plan"""
    # Extract CCPs from data
    ccps_data = data.critical_control_points
    plan_data = data.model_dump(exclude={"critical_control_points"})

    plan = HACCPPlan(**plan_data)
    db.add(plan)
    await db.flush()  # Get plan ID

    # Create CCPs
    for idx, ccp_data in enumerate(ccps_data):
        ccp = CriticalControlPoint(
            haccp_plan_id=plan.id,
            sort_order=ccp_data.sort_order if ccp_data.sort_order else idx,
            **ccp_data.model_dump(exclude={"sort_order"})
        )
        db.add(ccp)

    await db.commit()
    await db.refresh(plan)

    # Reload with CCPs
    query = select(HACCPPlan).options(
        selectinload(HACCPPlan.critical_control_points)
    ).where(HACCPPlan.id == plan.id)
    result = await db.execute(query)
    plan = result.scalar_one()

    logger.info(f"Created HACCP plan: {plan.name}")
    return HACCPPlanWithCCPs.model_validate(plan)


@router.put("/plans/{plan_id}", response_model=HACCPPlanResponse)
async def update_plan(
    plan_id: int,
    data: HACCPPlanUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a HACCP plan"""
    query = select(HACCPPlan).where(HACCPPlan.id == plan_id)
    result = await db.execute(query)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="HACCP plan not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)

    logger.info(f"Updated HACCP plan: {plan.name}")
    return plan


@router.post("/plans/{plan_id}/approve", response_model=HACCPPlanResponse)
async def approve_plan(
    plan_id: int,
    data: HACCPPlanApprove,
    db: AsyncSession = Depends(get_db)
):
    """Approve a HACCP plan"""
    query = select(HACCPPlan).where(HACCPPlan.id == plan_id)
    result = await db.execute(query)
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="HACCP plan not found")

    plan.approved_by = data.approved_by
    plan.approved_at = get_now()

    await db.commit()
    await db.refresh(plan)

    logger.info(f"Approved HACCP plan: {plan.name}")
    return plan


# ==================== Critical Control Points ====================

@router.get("/plans/{plan_id}/ccps", response_model=List[CriticalControlPointResponse])
async def list_ccps(
    plan_id: int,
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List critical control points for a plan"""
    query = select(CriticalControlPoint).where(
        CriticalControlPoint.haccp_plan_id == plan_id
    )

    if is_active is not None:
        query = query.where(CriticalControlPoint.is_active == is_active)

    query = query.order_by(CriticalControlPoint.sort_order)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/plans/{plan_id}/ccps", response_model=CriticalControlPointResponse, status_code=201)
async def add_ccp(
    plan_id: int,
    data: CriticalControlPointCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add a critical control point to a plan"""
    # Verify plan exists
    query = select(HACCPPlan.id).where(HACCPPlan.id == plan_id)
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="HACCP plan not found")

    ccp = CriticalControlPoint(
        haccp_plan_id=plan_id,
        **data.model_dump()
    )
    db.add(ccp)
    await db.commit()
    await db.refresh(ccp)

    logger.info(f"Added CCP {ccp.ccp_number} to plan {plan_id}")
    return ccp


@router.put("/ccps/{ccp_id}", response_model=CriticalControlPointResponse)
async def update_ccp(
    ccp_id: int,
    data: CriticalControlPointUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a critical control point"""
    query = select(CriticalControlPoint).where(CriticalControlPoint.id == ccp_id)
    result = await db.execute(query)
    ccp = result.scalar_one_or_none()

    if not ccp:
        raise HTTPException(status_code=404, detail="Critical control point not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ccp, field, value)

    await db.commit()
    await db.refresh(ccp)

    logger.info(f"Updated CCP {ccp.ccp_number}")
    return ccp


@router.delete("/ccps/{ccp_id}")
async def delete_ccp(
    ccp_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a critical control point"""
    query = select(CriticalControlPoint).where(CriticalControlPoint.id == ccp_id)
    result = await db.execute(query)
    ccp = result.scalar_one_or_none()

    if not ccp:
        raise HTTPException(status_code=404, detail="Critical control point not found")

    await db.delete(ccp)
    await db.commit()

    logger.info(f"Deleted CCP {ccp_id}")
    return {"message": "Critical control point deleted"}
