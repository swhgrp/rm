"""
Department API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from hr.db.database import get_db
from hr.schemas.department import Department, DepartmentCreate, DepartmentUpdate
from hr.models.department import Department as DepartmentModel
from hr.models.user import User
from hr.api.auth import require_auth
from typing import List

router = APIRouter()


@router.post("/", response_model=Department, status_code=201)
def create_department(
    department: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new department (requires authentication)"""
    # Check if department with same name already exists
    existing = db.query(DepartmentModel).filter(
        DepartmentModel.name == department.name
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Department '{department.name}' already exists"
        )

    db_department = DepartmentModel(
        **department.dict(),
        created_by=current_user.id
    )
    db.add(db_department)
    db.commit()
    db.refresh(db_department)
    return db_department


@router.get("/", response_model=List[Department])
def list_departments(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all departments (requires authentication)"""
    query = db.query(DepartmentModel)

    if not include_inactive:
        query = query.filter(DepartmentModel.is_active == True)

    departments = query.order_by(DepartmentModel.name).offset(skip).limit(limit).all()
    return departments


@router.get("/{department_id}", response_model=Department)
def get_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific department by ID (requires authentication)"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.put("/{department_id}", response_model=Department)
def update_department(
    department_id: int,
    department_update: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a department (requires authentication)"""
    db_department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not db_department:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check for duplicate name if name is being updated
    if department_update.name and department_update.name != db_department.name:
        existing = db.query(DepartmentModel).filter(
            DepartmentModel.name == department_update.name
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Department '{department_update.name}' already exists"
            )

    # Update fields
    update_data = department_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_department, field, value)

    db.commit()
    db.refresh(db_department)
    return db_department


@router.delete("/{department_id}", status_code=204)
def delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a department (requires authentication)"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check if any positions are using this department
    from hr.models.position import Position
    positions_using = db.query(Position).filter(Position.department_id == department_id).count()
    if positions_using > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete department. It is assigned to {positions_using} position(s)."
        )

    db.delete(department)
    db.commit()
    return None
