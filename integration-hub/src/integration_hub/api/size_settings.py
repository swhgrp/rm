"""
Size Settings API endpoints

CRUD operations for Size Units and Containers (Backbar-style sizing).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from integration_hub.db.database import get_db
from integration_hub.models.size_unit import SizeUnit
from integration_hub.models.container import Container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/size-settings", tags=["size-settings"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class SizeUnitCreate(BaseModel):
    """Create size unit request"""
    symbol: str
    name: str
    measure_type: str
    base_unit_symbol: str
    conversion_to_base: float = 1.0
    sort_order: int = 0
    is_active: bool = True


class SizeUnitUpdate(BaseModel):
    """Update size unit request"""
    symbol: Optional[str] = None
    name: Optional[str] = None
    measure_type: Optional[str] = None
    base_unit_symbol: Optional[str] = None
    conversion_to_base: Optional[float] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class SizeUnitResponse(BaseModel):
    """Size unit response"""
    id: int
    symbol: str
    name: str
    measure_type: str
    base_unit_symbol: str
    conversion_to_base: float
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class ContainerCreate(BaseModel):
    """Create container request"""
    name: str
    sort_order: int = 0
    is_active: bool = True


class ContainerUpdate(BaseModel):
    """Update container request"""
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ContainerResponse(BaseModel):
    """Container response"""
    id: int
    name: str
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================================
# SIZE UNITS ENDPOINTS
# ============================================================================

@router.get("/size-units")
async def list_size_units(
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """Get all size units"""
    query = db.query(SizeUnit)
    if not include_inactive:
        query = query.filter(SizeUnit.is_active == True)

    units = query.order_by(SizeUnit.measure_type, SizeUnit.sort_order).all()

    return [
        {
            "id": u.id,
            "symbol": u.symbol,
            "name": u.name,
            "measure_type": u.measure_type,
            "base_unit_symbol": u.base_unit_symbol,
            "conversion_to_base": float(u.conversion_to_base),
            "sort_order": u.sort_order or 0,
            "is_active": u.is_active
        }
        for u in units
    ]


@router.get("/size-units/{unit_id}")
async def get_size_unit(unit_id: int, db: Session = Depends(get_db)):
    """Get a specific size unit"""
    unit = db.query(SizeUnit).filter(SizeUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Size unit not found")

    return {
        "id": unit.id,
        "symbol": unit.symbol,
        "name": unit.name,
        "measure_type": unit.measure_type,
        "base_unit_symbol": unit.base_unit_symbol,
        "conversion_to_base": float(unit.conversion_to_base),
        "sort_order": unit.sort_order or 0,
        "is_active": unit.is_active
    }


@router.post("/size-units")
async def create_size_unit(data: SizeUnitCreate, db: Session = Depends(get_db)):
    """Create a new size unit"""
    # Check for duplicate symbol
    existing = db.query(SizeUnit).filter(SizeUnit.symbol == data.symbol).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Size unit with symbol '{data.symbol}' already exists")

    unit = SizeUnit(
        symbol=data.symbol,
        name=data.name,
        measure_type=data.measure_type,
        base_unit_symbol=data.base_unit_symbol,
        conversion_to_base=data.conversion_to_base,
        sort_order=data.sort_order,
        is_active=data.is_active
    )

    db.add(unit)
    db.commit()
    db.refresh(unit)

    logger.info(f"Created size unit: {unit.symbol} ({unit.name})")

    return {
        "id": unit.id,
        "symbol": unit.symbol,
        "name": unit.name,
        "measure_type": unit.measure_type,
        "base_unit_symbol": unit.base_unit_symbol,
        "conversion_to_base": float(unit.conversion_to_base),
        "sort_order": unit.sort_order or 0,
        "is_active": unit.is_active
    }


@router.put("/size-units/{unit_id}")
async def update_size_unit(unit_id: int, data: SizeUnitUpdate, db: Session = Depends(get_db)):
    """Update a size unit"""
    unit = db.query(SizeUnit).filter(SizeUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Size unit not found")

    # Check for duplicate symbol if changing
    if data.symbol and data.symbol != unit.symbol:
        existing = db.query(SizeUnit).filter(SizeUnit.symbol == data.symbol).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Size unit with symbol '{data.symbol}' already exists")

    # Update fields
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(unit, field, value)

    db.commit()
    db.refresh(unit)

    logger.info(f"Updated size unit {unit_id}: {unit.symbol}")

    return {
        "id": unit.id,
        "symbol": unit.symbol,
        "name": unit.name,
        "measure_type": unit.measure_type,
        "base_unit_symbol": unit.base_unit_symbol,
        "conversion_to_base": float(unit.conversion_to_base),
        "sort_order": unit.sort_order or 0,
        "is_active": unit.is_active
    }


# ============================================================================
# CONTAINERS ENDPOINTS
# ============================================================================

@router.get("/containers")
async def list_containers(
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """Get all containers"""
    query = db.query(Container)
    if not include_inactive:
        query = query.filter(Container.is_active == True)

    containers = query.order_by(Container.sort_order).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "sort_order": c.sort_order or 0,
            "is_active": c.is_active
        }
        for c in containers
    ]


@router.get("/containers/{container_id}")
async def get_container(container_id: int, db: Session = Depends(get_db)):
    """Get a specific container"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    return {
        "id": container.id,
        "name": container.name,
        "sort_order": container.sort_order or 0,
        "is_active": container.is_active
    }


@router.post("/containers")
async def create_container(data: ContainerCreate, db: Session = Depends(get_db)):
    """Create a new container"""
    name = data.name.lower()

    # Check for duplicate name
    existing = db.query(Container).filter(Container.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Container '{name}' already exists")

    container = Container(
        name=name,
        sort_order=data.sort_order,
        is_active=data.is_active
    )

    db.add(container)
    db.commit()
    db.refresh(container)

    logger.info(f"Created container: {container.name}")

    return {
        "id": container.id,
        "name": container.name,
        "sort_order": container.sort_order or 0,
        "is_active": container.is_active
    }


@router.put("/containers/{container_id}")
async def update_container(container_id: int, data: ContainerUpdate, db: Session = Depends(get_db)):
    """Update a container"""
    container = db.query(Container).filter(Container.id == container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    # Check for duplicate name if changing
    if data.name:
        new_name = data.name.lower()
        if new_name != container.name:
            existing = db.query(Container).filter(Container.name == new_name).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"Container '{new_name}' already exists")
            data.name = new_name

    # Update fields
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(container, field, value)

    db.commit()
    db.refresh(container)

    logger.info(f"Updated container {container_id}: {container.name}")

    return {
        "id": container.id,
        "name": container.name,
        "sort_order": container.sort_order or 0,
        "is_active": container.is_active
    }
