"""
Positions API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from hr.db.database import get_db
from hr.schemas.position import Position, PositionCreate, PositionUpdate
from hr.models.position import Position as PositionModel
from typing import List

router = APIRouter()


@router.post("/", response_model=Position, status_code=201)
def create_position(position: PositionCreate, db: Session = Depends(get_db)):
    """Create a new position"""
    db_position = PositionModel(**position.dict())
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    return db_position


@router.get("/", response_model=List[Position])
def list_positions(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """List all positions with optional filtering"""
    query = db.query(PositionModel)

    if active_only:
        query = query.filter(PositionModel.is_active == True)

    positions = query.offset(skip).limit(limit).all()
    return positions


@router.get("/{position_id}", response_model=Position)
def get_position(position_id: int, db: Session = Depends(get_db)):
    """Get a specific position by ID"""
    position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.put("/{position_id}", response_model=Position)
def update_position(
    position_id: int,
    position: PositionUpdate,
    db: Session = Depends(get_db)
):
    """Update a position"""
    db_position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
    if not db_position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Update only provided fields
    for key, value in position.dict(exclude_unset=True).items():
        setattr(db_position, key, value)

    db.commit()
    db.refresh(db_position)
    return db_position


@router.delete("/{position_id}", status_code=204)
def delete_position(position_id: int, db: Session = Depends(get_db)):
    """Delete a position"""
    db_position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
    if not db_position:
        raise HTTPException(status_code=404, detail="Position not found")

    db.delete(db_position)
    db.commit()
    return None
