"""
Fiscal Period API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from accounting.db.database import get_db
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus
from pydantic import BaseModel, Field


# Pydantic schemas
class FiscalPeriodCreate(BaseModel):
    period_name: str = Field(..., max_length=50)
    year: int = Field(..., ge=2000, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    start_date: date
    end_date: date


class FiscalPeriodResponse(BaseModel):
    id: int
    period_name: str
    year: int
    quarter: Optional[int]
    start_date: date
    end_date: date
    status: FiscalPeriodStatus
    closed_at: Optional[datetime]
    closed_by: Optional[int]

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/fiscal-periods", tags=["Fiscal Periods"])


@router.get("/", response_model=List[FiscalPeriodResponse])
def list_fiscal_periods(
    year: Optional[int] = None,
    status: Optional[FiscalPeriodStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    List fiscal periods with optional filters
    """
    query = db.query(FiscalPeriod)

    if year:
        query = query.filter(FiscalPeriod.year == year)

    if status:
        query = query.filter(FiscalPeriod.status == status)

    periods = query.order_by(FiscalPeriod.year.desc(), FiscalPeriod.start_date.desc()).offset(skip).limit(limit).all()
    return periods


@router.get("/{period_id}", response_model=FiscalPeriodResponse)
def get_fiscal_period(period_id: int, db: Session = Depends(get_db)):
    """
    Get a specific fiscal period by ID
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")
    return period


@router.get("/year/{year}/name/{period_name}", response_model=FiscalPeriodResponse)
def get_fiscal_period_by_year_name(year: int, period_name: str, db: Session = Depends(get_db)):
    """
    Get a specific fiscal period by year and period name
    """
    period = db.query(FiscalPeriod).filter(
        FiscalPeriod.year == year,
        FiscalPeriod.period_name == period_name
    ).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")
    return period


@router.post("/", response_model=FiscalPeriodResponse, status_code=201)
def create_fiscal_period(period: FiscalPeriodCreate, db: Session = Depends(get_db)):
    """
    Create a new fiscal period
    """
    # Check if period already exists
    existing = db.query(FiscalPeriod).filter(
        FiscalPeriod.year == period.year,
        FiscalPeriod.period_name == period.period_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Fiscal period {period.year}-{period.period_name} already exists"
        )

    # Validate date range
    if period.end_date <= period.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    # Create period
    new_period = FiscalPeriod(
        period_name=period.period_name,
        year=period.year,
        quarter=period.quarter,
        start_date=period.start_date,
        end_date=period.end_date,
        status=FiscalPeriodStatus.OPEN
    )
    db.add(new_period)
    db.commit()
    db.refresh(new_period)
    return new_period


@router.post("/{period_id}/close")
def close_fiscal_period(period_id: int, db: Session = Depends(get_db)):
    """
    Close a fiscal period (prevent new entries)
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    if period.status == FiscalPeriodStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Period is already closed")

    if period.status == FiscalPeriodStatus.LOCKED:
        raise HTTPException(status_code=400, detail="Cannot close a locked period")

    period.status = FiscalPeriodStatus.CLOSED
    period.closed_at = datetime.utcnow()
    # period.closed_by = current_user.id  # TODO: Add authentication

    db.commit()

    return {
        "message": "Fiscal period closed successfully",
        "year": period.year,
        "period_name": period.period_name
    }


@router.post("/{period_id}/reopen")
def reopen_fiscal_period(period_id: int, db: Session = Depends(get_db)):
    """
    Reopen a closed fiscal period
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    if period.status == FiscalPeriodStatus.LOCKED:
        raise HTTPException(status_code=400, detail="Cannot reopen a locked period")

    if period.status == FiscalPeriodStatus.OPEN:
        raise HTTPException(status_code=400, detail="Period is already open")

    period.status = FiscalPeriodStatus.OPEN
    period.closed_at = None
    period.closed_by = None

    db.commit()

    return {
        "message": "Fiscal period reopened successfully",
        "year": period.year,
        "period_name": period.period_name
    }


@router.post("/{period_id}/lock")
def lock_fiscal_period(period_id: int, db: Session = Depends(get_db)):
    """
    Lock a fiscal period (permanent, for audited periods)
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    if period.status == FiscalPeriodStatus.LOCKED:
        raise HTTPException(status_code=400, detail="Period is already locked")

    if period.status == FiscalPeriodStatus.OPEN:
        raise HTTPException(status_code=400, detail="Must close period before locking")

    period.status = FiscalPeriodStatus.LOCKED

    db.commit()

    return {
        "message": "Fiscal period locked successfully (this is irreversible)",
        "year": period.year,
        "period_name": period.period_name
    }


@router.post("/create-year/{year}")
def create_full_year(year: int, db: Session = Depends(get_db)):
    """
    Create all 12 fiscal periods for a year
    """
    from calendar import monthrange, month_name

    created_periods = []
    errors = []

    for month in range(1, 13):
        period_name = f"{month_name[month]} {year}"

        # Check if period already exists
        existing = db.query(FiscalPeriod).filter(
            FiscalPeriod.year == year,
            FiscalPeriod.period_name == period_name
        ).first()

        if existing:
            errors.append(f"Period {period_name} already exists")
            continue

        # Calculate start and end dates
        start_date = date(year, month, 1)
        last_day = monthrange(year, month)[1]
        end_date = date(year, month, last_day)

        # Calculate quarter
        quarter = ((month - 1) // 3) + 1

        # Create period
        new_period = FiscalPeriod(
            period_name=period_name,
            year=year,
            quarter=quarter,
            start_date=start_date,
            end_date=end_date,
            status=FiscalPeriodStatus.OPEN
        )
        db.add(new_period)
        created_periods.append(period_name)

    db.commit()

    return {
        "message": f"Created {len(created_periods)} fiscal periods for year {year}",
        "created": created_periods,
        "errors": errors if errors else None
    }
