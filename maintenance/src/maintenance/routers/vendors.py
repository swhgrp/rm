"""Vendors router for Maintenance Service"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from maintenance.database import get_db
from maintenance.models import Vendor
from maintenance.schemas import (
    VendorCreate, VendorUpdate, VendorResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=List[VendorResponse])
async def list_vendors(
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """List vendors with optional filters"""
    query = select(Vendor)

    if is_active is not None:
        query = query.where(Vendor.is_active == is_active)

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Vendor.name.ilike(search_term),
                Vendor.contact_name.ilike(search_term),
                Vendor.service_types.ilike(search_term)
            )
        )

    query = query.order_by(Vendor.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(vendor_id: int, db: AsyncSession = Depends(get_db)):
    """Get vendor by ID"""
    query = select(Vendor).where(Vendor.id == vendor_id)
    result = await db.execute(query)
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor


@router.post("", response_model=VendorResponse, status_code=201)
async def create_vendor(
    vendor_data: VendorCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create new vendor"""
    vendor = Vendor(**vendor_data.model_dump())
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)

    logger.info(f"Created vendor: {vendor.name} (ID: {vendor.id})")
    return vendor


@router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: int,
    vendor_data: VendorUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update vendor"""
    query = select(Vendor).where(Vendor.id == vendor_id)
    result = await db.execute(query)
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    update_data = vendor_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vendor, field, value)

    await db.commit()
    await db.refresh(vendor)

    logger.info(f"Updated vendor: {vendor.name} (ID: {vendor.id})")
    return vendor


@router.delete("/{vendor_id}", status_code=204)
async def delete_vendor(vendor_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate vendor"""
    query = select(Vendor).where(Vendor.id == vendor_id)
    result = await db.execute(query)
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor.is_active = False
    await db.commit()

    logger.info(f"Deactivated vendor: {vendor.name} (ID: {vendor_id})")
