"""
Units of Measure API endpoints

Hub is the source of truth for UOM data.
Inventory and other systems fetch UOM list from this API.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
from integration_hub.db.database import get_db
from integration_hub.models.unit_of_measure import UnitOfMeasure, UnitCategory
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uom", tags=["uom"])


class UOMResponse(BaseModel):
    """Response model for a unit of measure"""
    id: int
    name: str
    abbreviation: str
    dimension: str  # count, weight, volume
    to_base_factor: float
    is_base_unit: bool
    category_id: int
    category_name: Optional[str] = None

    class Config:
        from_attributes = True


class UOMCreateRequest(BaseModel):
    """Request model for creating a new UOM"""
    name: str
    abbreviation: str
    dimension: str  # count, weight, volume
    to_base_factor: float = 1.0
    is_base_unit: bool = False


class UOMUpdateRequest(BaseModel):
    """Request model for updating a UOM"""
    name: Optional[str] = None
    abbreviation: Optional[str] = None
    to_base_factor: Optional[float] = None
    is_base_unit: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("/", response_model=List[UOMResponse])
def get_all_uoms(
    dimension: Optional[str] = Query(None, description="Filter by dimension: count, weight, volume"),
    active_only: bool = Query(True, description="Only return active UOMs"),
    db: Session = Depends(get_db)
):
    """
    Get all units of measure.

    This is the primary endpoint for Inventory and other systems to fetch UOM list.
    Returns UOMs with their conversion factors for calculations.

    Dimensions:
    - count: Discrete items (each, case, bottle, dozen)
    - weight: Mass measures (oz, lb, kg, g)
    - volume: Liquid measures (fl oz, gallon, liter, ml)
    """
    query = db.query(UnitOfMeasure)

    if active_only:
        query = query.filter(UnitOfMeasure.is_active == True)

    if dimension:
        # Map dimension string to enum value
        dimension_lower = dimension.lower()
        query = query.filter(UnitOfMeasure.dimension.has(value=dimension_lower))

    uoms = query.order_by(UnitOfMeasure.dimension, UnitOfMeasure.name).all()

    # Build response with category names
    result = []
    for uom in uoms:
        dim_value = uom.dimension.value if uom.dimension else 'count'
        result.append(UOMResponse(
            id=uom.id,
            name=uom.name,
            abbreviation=uom.abbreviation,
            dimension=dim_value,
            to_base_factor=float(uom.to_base_factor) if uom.to_base_factor else 1.0,
            is_base_unit=uom.is_base_unit or False,
            category_id=uom.category_id,
            category_name=uom.category.name if uom.category else None
        ))

    return result


@router.get("/by-dimension/{dimension}", response_model=List[UOMResponse])
def get_uoms_by_dimension(
    dimension: str,
    db: Session = Depends(get_db)
):
    """
    Get UOMs filtered by dimension.

    Useful for populating dropdowns based on item type:
    - count: For countable items (bottles, cans, cases)
    - weight: For items measured by weight (meat, produce)
    - volume: For liquid items (beverages, sauces)
    """
    dimension_lower = dimension.lower()
    if dimension_lower not in ['count', 'weight', 'volume']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension: {dimension}. Must be one of: count, weight, volume"
        )

    uoms = db.query(UnitOfMeasure).filter(
        UnitOfMeasure.is_active == True
    ).all()

    # Filter by dimension value
    result = []
    for uom in uoms:
        dim_value = uom.dimension.value if uom.dimension else 'count'
        if dim_value == dimension_lower:
            result.append(UOMResponse(
                id=uom.id,
                name=uom.name,
                abbreviation=uom.abbreviation,
                dimension=dim_value,
                to_base_factor=float(uom.to_base_factor) if uom.to_base_factor else 1.0,
                is_base_unit=uom.is_base_unit or False,
                category_id=uom.category_id,
                category_name=uom.category.name if uom.category else None
            ))

    return sorted(result, key=lambda x: x.name)


@router.get("/{uom_id}", response_model=UOMResponse)
def get_uom(
    uom_id: int,
    db: Session = Depends(get_db)
):
    """Get a single UOM by ID"""
    uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).first()

    if not uom:
        raise HTTPException(status_code=404, detail=f"UOM with id {uom_id} not found")

    dim_value = uom.dimension.value if uom.dimension else 'count'
    return UOMResponse(
        id=uom.id,
        name=uom.name,
        abbreviation=uom.abbreviation,
        dimension=dim_value,
        to_base_factor=float(uom.to_base_factor) if uom.to_base_factor else 1.0,
        is_base_unit=uom.is_base_unit or False,
        category_id=uom.category_id,
        category_name=uom.category.name if uom.category else None
    )


@router.post("/", response_model=UOMResponse)
def create_uom(
    request: UOMCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new unit of measure.

    Note: Most standard UOMs already exist. Only create new ones for
    specific business needs (e.g., custom pack sizes).
    """
    # Map dimension to category
    dimension_lower = request.dimension.lower()
    dimension_to_category = {
        'count': 'Count',
        'weight': 'Weight',
        'volume': 'Volume'
    }

    if dimension_lower not in dimension_to_category:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension: {request.dimension}. Must be one of: count, weight, volume"
        )

    # Get or create category
    category_name = dimension_to_category[dimension_lower]
    category = db.query(UnitCategory).filter(UnitCategory.name == category_name).first()

    if not category:
        category = UnitCategory(name=category_name, description=f"{category_name} units")
        db.add(category)
        db.flush()

    # Check for duplicate
    existing = db.query(UnitOfMeasure).filter(
        UnitOfMeasure.abbreviation == request.abbreviation
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"UOM with abbreviation '{request.abbreviation}' already exists"
        )

    # Import enum for dimension
    from integration_hub.models.unit_of_measure import UnitDimension

    uom = UnitOfMeasure(
        name=request.name,
        abbreviation=request.abbreviation,
        dimension=UnitDimension(dimension_lower),
        to_base_factor=Decimal(str(request.to_base_factor)),
        is_base_unit=request.is_base_unit,
        category_id=category.id,
        is_active=True
    )

    db.add(uom)
    db.commit()
    db.refresh(uom)

    logger.info(f"Created new UOM: {uom.name} ({uom.abbreviation})")

    return UOMResponse(
        id=uom.id,
        name=uom.name,
        abbreviation=uom.abbreviation,
        dimension=dimension_lower,
        to_base_factor=float(uom.to_base_factor),
        is_base_unit=uom.is_base_unit,
        category_id=uom.category_id,
        category_name=category.name
    )


@router.put("/{uom_id}", response_model=UOMResponse)
def update_uom(
    uom_id: int,
    request: UOMUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update an existing UOM"""
    uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).first()

    if not uom:
        raise HTTPException(status_code=404, detail=f"UOM with id {uom_id} not found")

    if request.name is not None:
        uom.name = request.name
    if request.abbreviation is not None:
        uom.abbreviation = request.abbreviation
    if request.to_base_factor is not None:
        uom.to_base_factor = Decimal(str(request.to_base_factor))
    if request.is_base_unit is not None:
        uom.is_base_unit = request.is_base_unit
    if request.is_active is not None:
        uom.is_active = request.is_active

    db.commit()
    db.refresh(uom)

    dim_value = uom.dimension.value if uom.dimension else 'count'
    return UOMResponse(
        id=uom.id,
        name=uom.name,
        abbreviation=uom.abbreviation,
        dimension=dim_value,
        to_base_factor=float(uom.to_base_factor) if uom.to_base_factor else 1.0,
        is_base_unit=uom.is_base_unit or False,
        category_id=uom.category_id,
        category_name=uom.category.name if uom.category else None
    )


@router.get("/convert/{from_uom_id}/{to_uom_id}")
def convert_units(
    from_uom_id: int,
    to_uom_id: int,
    quantity: float = Query(..., description="Quantity to convert"),
    db: Session = Depends(get_db)
):
    """
    Convert a quantity from one UOM to another.

    Both UOMs must be in the same dimension (e.g., both weight or both volume).
    Returns the converted quantity.

    Example: Convert 2 gallons to fluid ounces
    - from_uom_id: 19 (Gallon)
    - to_uom_id: 15 (Fluid Ounce)
    - quantity: 2
    - result: 256.0
    """
    from_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == from_uom_id).first()
    to_uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == to_uom_id).first()

    if not from_uom:
        raise HTTPException(status_code=404, detail=f"From UOM with id {from_uom_id} not found")
    if not to_uom:
        raise HTTPException(status_code=404, detail=f"To UOM with id {to_uom_id} not found")

    # Check same dimension
    from_dim = from_uom.dimension.value if from_uom.dimension else 'count'
    to_dim = to_uom.dimension.value if to_uom.dimension else 'count'

    if from_dim != to_dim:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot convert between different dimensions: {from_dim} to {to_dim}"
        )

    # Convert through base unit
    from_factor = float(from_uom.to_base_factor) if from_uom.to_base_factor else 1.0
    to_factor = float(to_uom.to_base_factor) if to_uom.to_base_factor else 1.0

    # quantity in from_unit -> base units -> to_unit
    base_quantity = quantity * from_factor
    result_quantity = base_quantity / to_factor

    return {
        "from_uom": from_uom.name,
        "to_uom": to_uom.name,
        "from_quantity": quantity,
        "to_quantity": round(result_quantity, 6),
        "dimension": from_dim
    }
