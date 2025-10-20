"""
Area management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.area import Area
from accounting.models.role import role_areas
from accounting.schemas.area import AreaCreate, AreaUpdate, AreaResponse
from accounting.api.auth import require_admin, require_auth

router = APIRouter(prefix="/api/areas", tags=["areas"])


@router.get("/", response_model=List[AreaResponse])
def list_areas(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)  # Changed from require_admin - any user can list areas
):
    """List all areas/locations - available to all authenticated users"""
    query = db.query(Area)
    if not include_inactive:
        query = query.filter(Area.is_active == True)

    areas = query.offset(skip).limit(limit).all()
    return areas


@router.get("/{area_id}", response_model=AreaResponse)
def get_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get a specific area by ID (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )
    return area


@router.post("/", response_model=AreaResponse)
def create_area(
    area_data: AreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new area (admin only)"""
    # Check if area name already exists
    existing_name = db.query(Area).filter(Area.name == area_data.name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Area name already exists"
        )

    # Check if area code already exists
    existing_code = db.query(Area).filter(Area.code == area_data.code).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Area code already exists"
        )

    # Create new area
    new_area = Area(
        name=area_data.name,
        code=area_data.code,
        description=area_data.description,
        # Legal entity information
        legal_name=area_data.legal_name,
        ein=area_data.ein,
        entity_type=area_data.entity_type,
        # Address information
        address_line1=area_data.address_line1,
        address_line2=area_data.address_line2,
        city=area_data.city,
        state=area_data.state,
        zip_code=area_data.zip_code,
        country=area_data.country,
        # Contact information
        phone=area_data.phone,
        email=area_data.email,
        website=area_data.website
    )

    db.add(new_area)
    db.commit()
    db.refresh(new_area)

    return new_area


@router.put("/{area_id}", response_model=AreaResponse)
def update_area(
    area_id: int,
    area_data: AreaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an area (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )

    # Update fields if provided
    if area_data.name is not None:
        # Check if name already exists for another area
        existing_name = db.query(Area).filter(
            Area.name == area_data.name,
            Area.id != area_id
        ).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Area name already exists"
            )
        area.name = area_data.name

    if area_data.code is not None:
        # Check if code already exists for another area
        existing_code = db.query(Area).filter(
            Area.code == area_data.code,
            Area.id != area_id
        ).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Area code already exists"
            )
        area.code = area_data.code

    if area_data.description is not None:
        area.description = area_data.description

    if area_data.is_active is not None:
        area.is_active = area_data.is_active

    # Legal entity information
    if area_data.legal_name is not None:
        area.legal_name = area_data.legal_name

    if area_data.ein is not None:
        area.ein = area_data.ein

    if area_data.entity_type is not None:
        area.entity_type = area_data.entity_type

    # Address information
    if area_data.address_line1 is not None:
        area.address_line1 = area_data.address_line1

    if area_data.address_line2 is not None:
        area.address_line2 = area_data.address_line2

    if area_data.city is not None:
        area.city = area_data.city

    if area_data.state is not None:
        area.state = area_data.state

    if area_data.zip_code is not None:
        area.zip_code = area_data.zip_code

    if area_data.country is not None:
        area.country = area_data.country

    # Contact information
    if area_data.phone is not None:
        area.phone = area_data.phone

    if area_data.email is not None:
        area.email = area_data.email

    if area_data.website is not None:
        area.website = area_data.website

    db.commit()
    db.refresh(area)

    return area


@router.delete("/{area_id}")
def delete_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an area (admin only)"""
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area not found"
        )

    # Check if any roles are assigned to this area
    roles_count = db.query(role_areas).filter(role_areas.c.area_id == area_id).count()
    if roles_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete area: it is assigned to {roles_count} role(s)"
        )

    db.delete(area)
    db.commit()

    return {"message": "Area deleted successfully"}
