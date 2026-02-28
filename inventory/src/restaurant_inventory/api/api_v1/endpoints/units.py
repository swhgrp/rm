from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from decimal import Decimal
import httpx
import os
import logging

from restaurant_inventory.db.database import get_db
from restaurant_inventory.models.unit_of_measure import UnitCategory, UnitOfMeasure
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.unit_of_measure import (
    UnitCategoryCreate,
    UnitCategoryUpdate,
    UnitCategoryResponse,
    UnitCategoryWithUnits,
    UnitOfMeasureCreate,
    UnitOfMeasureUpdate,
    UnitOfMeasureResponse,
    UnitConversionRequest,
    UnitConversionResponse
)
from restaurant_inventory.core.deps import get_current_user, require_manager_or_admin
from restaurant_inventory.core.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter()

# Hub API URL for UOM source of truth
HUB_API_URL = os.getenv("HUB_API_URL", "http://integration-hub:8000")


# ==================== Unit Categories ====================

@router.get("/categories", response_model=List[UnitCategoryWithUnits])
async def get_unit_categories(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unit categories with their units"""
    query = db.query(UnitCategory)
    if active_only:
        query = query.filter(UnitCategory.is_active == True)

    categories = query.order_by(UnitCategory.name).all()

    # For each category, filter active units only
    result = []
    for cat in categories:
        cat_dict = UnitCategoryWithUnits.model_validate(cat).model_dump()
        # Filter to only active units
        cat_dict['units'] = [u for u in cat.units if u.is_active]
        result.append(UnitCategoryWithUnits(**cat_dict))

    return result


@router.get("/categories/{category_id}", response_model=UnitCategoryWithUnits)
async def get_unit_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific unit category with its units"""
    category = db.query(UnitCategory).filter(UnitCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Unit category not found")
    return category


@router.post("/categories", response_model=UnitCategoryResponse)
async def create_unit_category(
    category_data: UnitCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new unit category"""
    # Check for duplicate name
    existing = db.query(UnitCategory).filter(UnitCategory.name == category_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Unit category with this name already exists")

    category = UnitCategory(**category_data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)

    log_audit_event(
        db=db,
        user=current_user,
        action="create",
        entity_type="unit_category",
        entity_id=category.id,
        changes={"name": category.name}
    )

    return category


@router.put("/categories/{category_id}", response_model=UnitCategoryResponse)
async def update_unit_category(
    category_id: int,
    category_data: UnitCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a unit category"""
    category = db.query(UnitCategory).filter(UnitCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Unit category not found")

    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)

    log_audit_event(
        db=db,
        user=current_user,
        action="update",
        entity_type="unit_category",
        entity_id=category.id,
        changes=update_data
    )

    return category


@router.delete("/categories/{category_id}")
async def delete_unit_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a unit category (soft delete by setting is_active=False)"""
    category = db.query(UnitCategory).filter(UnitCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Unit category not found")

    category.is_active = False
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="delete",
        entity_type="unit_category",
        entity_id=category.id
    )

    return {"message": "Unit category deleted successfully"}


# ==================== Units of Measure ====================

@router.get("/", response_model=List[UnitOfMeasureResponse])
async def get_units(
    category_id: Optional[int] = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all units of measure, optionally filtered by category"""
    query = db.query(UnitOfMeasure)
    if category_id:
        query = query.filter(UnitOfMeasure.category_id == category_id)
    if active_only:
        query = query.filter(UnitOfMeasure.is_active == True)

    units = query.order_by(UnitOfMeasure.category_id, UnitOfMeasure.name).all()

    # Add category name, reference unit name, and dimension to each unit
    result = []
    for unit in units:
        unit_dict = UnitOfMeasureResponse.model_validate(unit).model_dump()
        unit_dict['category_name'] = unit.category.name if unit.category else None
        unit_dict['reference_unit_name'] = unit.reference_unit.abbreviation if unit.reference_unit else None
        unit_dict['dimension'] = unit.dimension
        result.append(UnitOfMeasureResponse(**unit_dict))

    return result


# ==================== Hub UOM API (Source of Truth) ====================
# NOTE: These routes MUST come before /{unit_id} to avoid route conflicts!

@router.get("/hub")
async def get_hub_units(
    dimension: Optional[str] = Query(None, description="Filter by dimension: count, weight, volume"),
    current_user: User = Depends(get_current_user)
):
    """
    Get units of measure from Hub (source of truth).

    Hub is the authoritative source for UOM data. This endpoint fetches
    UOM list from Hub API and returns it to the frontend.

    Dimensions:
    - count: Discrete items (each, case, bottle, dozen)
    - weight: Mass measures (oz, lb, kg, g)
    - volume: Liquid measures (fl oz, gallon, liter, ml)
    """
    logger.info(f"get_hub_units called by user {current_user.username if current_user else 'unknown'}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"active_only": "true"}
            if dimension:
                params["dimension"] = dimension

            logger.info(f"Fetching from {HUB_API_URL}/api/uom/ with params {params}")
            response = await client.get(f"{HUB_API_URL}/api/uom/", params=params)
            response.raise_for_status()

            hub_uoms = response.json()
            logger.info(f"Got {len(hub_uoms)} UOMs from Hub")

            # Transform to match frontend expectations
            # Hub returns: id, name, abbreviation, dimension, to_base_factor, is_base_unit, category_id, category_name
            result = []
            for uom in hub_uoms:
                result.append({
                    "id": uom["id"],
                    "hub_id": uom["id"],  # Explicit hub ID
                    "name": uom["name"],
                    "abbreviation": uom["abbreviation"],
                    "dimension": uom["dimension"],
                    "to_base_factor": uom.get("to_base_factor", 1.0),
                    "is_base_unit": uom.get("is_base_unit", False),
                    "category_name": uom.get("category_name"),
                    "source": "hub"  # Indicate this came from Hub
                })

            return result

    except httpx.RequestError as e:
        logger.error(f"Error fetching UOMs from Hub: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Unable to reach Hub API for UOM data: {str(e)}"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Hub API error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Hub API error: {e.response.text}"
        )
    except Exception as e:
        logger.exception(f"Unexpected error in get_hub_units: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/hub/{uom_id}")
async def get_hub_unit(
    uom_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get a single UOM from Hub by ID"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HUB_API_URL}/api/uom/{uom_id}")
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error(f"Error fetching UOM {uom_id} from Hub: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Unable to reach Hub API: {str(e)}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"UOM {uom_id} not found in Hub")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Hub API error: {e.response.text}"
        )


# ==================== Local Units of Measure (by ID) ====================

@router.get("/{unit_id}", response_model=UnitOfMeasureResponse)
async def get_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific unit of measure"""
    unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit of measure not found")

    unit_dict = UnitOfMeasureResponse.model_validate(unit).model_dump()
    unit_dict['category_name'] = unit.category.name if unit.category else None
    unit_dict['reference_unit_name'] = unit.reference_unit.abbreviation if unit.reference_unit else None
    return UnitOfMeasureResponse(**unit_dict)


@router.post("/", response_model=UnitOfMeasureResponse)
async def create_unit(
    unit_data: UnitOfMeasureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new unit of measure with reference-based conversion"""
    # Validate category exists
    category = db.query(UnitCategory).filter(UnitCategory.id == unit_data.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Unit category not found")

    # Validate reference unit if provided
    if unit_data.reference_unit_id:
        reference_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == unit_data.reference_unit_id).first()
        if not reference_unit:
            raise HTTPException(status_code=404, detail="Reference unit not found")
        if reference_unit.category_id != unit_data.category_id:
            raise HTTPException(status_code=400, detail="Reference unit must be in the same category")
        if unit_data.contains_quantity is None or unit_data.contains_quantity <= 0:
            raise HTTPException(status_code=400, detail="Contains quantity must be specified and greater than 0 when reference unit is provided")

    # Check for duplicate name or abbreviation in same category (only active units)
    existing = db.query(UnitOfMeasure).filter(
        UnitOfMeasure.category_id == unit_data.category_id,
        UnitOfMeasure.is_active == True,
        (UnitOfMeasure.name == unit_data.name) | (UnitOfMeasure.abbreviation == unit_data.abbreviation)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Unit with this name or abbreviation already exists in this category")

    # Check if there's an inactive unit with the same name/abbreviation - reactivate it instead
    inactive_unit = db.query(UnitOfMeasure).filter(
        UnitOfMeasure.category_id == unit_data.category_id,
        UnitOfMeasure.is_active == False,
        (UnitOfMeasure.name == unit_data.name) | (UnitOfMeasure.abbreviation == unit_data.abbreviation)
    ).first()
    # Derive dimension from category name
    cat_lower = category.name.lower()
    if 'weight' in cat_lower:
        dimension = 'weight'
    elif 'volume' in cat_lower or 'liquid' in cat_lower:
        dimension = 'volume'
    elif 'count' in cat_lower:
        dimension = 'count'
    elif 'length' in cat_lower:
        dimension = 'length'
    else:
        dimension = cat_lower.split()[0] if cat_lower else None

    if inactive_unit:
        # Reactivate the unit with the new data
        inactive_unit.is_active = True
        inactive_unit.name = unit_data.name
        inactive_unit.abbreviation = unit_data.abbreviation
        inactive_unit.reference_unit_id = unit_data.reference_unit_id
        inactive_unit.contains_quantity = unit_data.contains_quantity
        inactive_unit.dimension = dimension
        db.commit()
        db.refresh(inactive_unit)

        log_audit_event(
            db=db,
            user=current_user,
            action="reactivate",
            entity_type="unit_of_measure",
            entity_id=inactive_unit.id,
            changes={"name": inactive_unit.name, "category": category.name}
        )

        unit_dict = UnitOfMeasureResponse.model_validate(inactive_unit).model_dump()
        unit_dict['category_name'] = category.name
        unit_dict['reference_unit_name'] = inactive_unit.reference_unit.abbreviation if inactive_unit.reference_unit else None
        return UnitOfMeasureResponse(**unit_dict)

    unit = UnitOfMeasure(**unit_data.model_dump(), dimension=dimension)
    db.add(unit)
    db.commit()
    db.refresh(unit)

    log_audit_event(
        db=db,
        user=current_user,
        action="create",
        entity_type="unit_of_measure",
        entity_id=unit.id,
        changes={"name": unit.name, "category": category.name}
    )

    unit_dict = UnitOfMeasureResponse.model_validate(unit).model_dump()
    unit_dict['category_name'] = category.name
    unit_dict['reference_unit_name'] = unit.reference_unit.abbreviation if unit.reference_unit else None
    return UnitOfMeasureResponse(**unit_dict)


@router.put("/{unit_id}", response_model=UnitOfMeasureResponse)
async def update_unit(
    unit_id: int,
    unit_data: UnitOfMeasureUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a unit of measure"""
    unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit of measure not found")

    update_data = unit_data.model_dump(exclude_unset=True)

    # Validate reference unit if being changed
    if 'reference_unit_id' in update_data and update_data['reference_unit_id']:
        reference_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == update_data['reference_unit_id']).first()
        if not reference_unit:
            raise HTTPException(status_code=404, detail="Reference unit not found")
        if reference_unit.category_id != unit.category_id:
            raise HTTPException(status_code=400, detail="Reference unit must be in the same category")
        # Prevent circular references
        if reference_unit.id == unit_id:
            raise HTTPException(status_code=400, detail="Unit cannot reference itself")

    for field, value in update_data.items():
        setattr(unit, field, value)

    db.commit()
    db.refresh(unit)

    # Convert Decimal to float for JSON serialization in audit log
    audit_changes = {}
    for key, value in update_data.items():
        if isinstance(value, Decimal):
            audit_changes[key] = float(value)
        else:
            audit_changes[key] = value

    log_audit_event(
        db=db,
        user=current_user,
        action="update",
        entity_type="unit_of_measure",
        entity_id=unit.id,
        changes=audit_changes
    )

    unit_dict = UnitOfMeasureResponse.model_validate(unit).model_dump()
    unit_dict['category_name'] = unit.category.name if unit.category else None
    unit_dict['reference_unit_name'] = unit.reference_unit.abbreviation if unit.reference_unit else None
    return UnitOfMeasureResponse(**unit_dict)


@router.delete("/{unit_id}")
async def delete_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a unit of measure (soft delete)"""
    unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit of measure not found")

    # Check if any other units reference this unit
    dependent_units = db.query(UnitOfMeasure).filter(
        UnitOfMeasure.reference_unit_id == unit_id,
        UnitOfMeasure.is_active == True
    ).count()
    if dependent_units > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete this unit. {dependent_units} other unit(s) reference it.")

    unit.is_active = False
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="delete",
        entity_type="unit_of_measure",
        entity_id=unit.id
    )

    return {"message": "Unit of measure deleted successfully"}


# ==================== Unit Conversion ====================

def get_unit_chain_to_base(unit: UnitOfMeasure, db: Session) -> list:
    """Get the chain of conversions from a unit to the base unit (unit with no reference)"""
    chain = []
    current = unit
    visited = set()

    while current:
        if current.id in visited:
            raise HTTPException(status_code=500, detail="Circular reference detected in unit chain")
        visited.add(current.id)
        chain.append(current)

        if not current.reference_unit_id:
            break  # Reached base unit
        current = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == current.reference_unit_id).first()
        if not current:
            raise HTTPException(status_code=500, detail="Broken reference in unit chain")

    return chain

def convert_to_common_base(quantity: Decimal, unit_chain: list) -> Decimal:
    """Convert quantity through the chain to the base unit"""
    result = quantity
    for unit in unit_chain:
        if unit.contains_quantity and unit.contains_quantity > 0:
            result *= unit.contains_quantity
    return result

@router.post("/convert", response_model=UnitConversionResponse)
async def convert_units(
    conversion_data: UnitConversionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Convert a quantity from one unit to another using reference chain"""
    from_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == conversion_data.from_unit_id).first()
    to_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == conversion_data.to_unit_id).first()

    if not from_unit or not to_unit:
        raise HTTPException(status_code=404, detail="One or both units not found")

    if from_unit.category_id != to_unit.category_id:
        raise HTTPException(status_code=400, detail="Cannot convert between different unit categories")

    # Get chains to base for both units
    from_chain = get_unit_chain_to_base(from_unit, db)
    to_chain = get_unit_chain_to_base(to_unit, db)

    # Find common ancestor (base unit)
    from_base_units = {u.id for u in from_chain}
    to_base_units = {u.id for u in to_chain}
    common_base = from_base_units & to_base_units

    if not common_base:
        raise HTTPException(status_code=400, detail="Units do not share a common base unit")

    # Convert from_unit to base, excluding the base itself
    from_in_base = convert_to_common_base(conversion_data.quantity, from_chain[:-1] if len(from_chain) > 1 else [])

    # Convert from base to to_unit (divide by the chain)
    to_conversion = Decimal('1.0')
    for unit in to_chain[:-1] if len(to_chain) > 1 else []:
        if unit.contains_quantity and unit.contains_quantity > 0:
            to_conversion *= unit.contains_quantity

    converted = from_in_base / to_conversion if to_conversion > 0 else from_in_base

    # Calculate overall conversion factor
    from_to_base_factor = convert_to_common_base(Decimal('1.0'), from_chain[:-1] if len(from_chain) > 1 else [])
    to_base_factor = convert_to_common_base(Decimal('1.0'), to_chain[:-1] if len(to_chain) > 1 else [])
    conversion_factor = from_to_base_factor / to_base_factor if to_base_factor > 0 else from_to_base_factor

    return UnitConversionResponse(
        from_unit=f"{from_unit.name} ({from_unit.abbreviation})",
        to_unit=f"{to_unit.name} ({to_unit.abbreviation})",
        input_quantity=conversion_data.quantity,
        converted_quantity=converted,
        conversion_factor=conversion_factor
    )
