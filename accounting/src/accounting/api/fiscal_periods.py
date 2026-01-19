"""
Fiscal Period API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from accounting.db.database import get_db
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus
from accounting.models.user import User
from accounting.api.auth import require_auth, require_admin
from pydantic import BaseModel, Field


# Pydantic schemas
class FiscalPeriodCreate(BaseModel):
    period_name: str = Field(..., max_length=50)
    year: int = Field(..., ge=2000, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    start_date: date
    end_date: date


class FiscalPeriodUpdate(BaseModel):
    period_name: Optional[str] = Field(None, max_length=50)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


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
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
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
def create_fiscal_period(
    period: FiscalPeriodCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Create a new fiscal period (admin only)
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


@router.put("/{period_id}", response_model=FiscalPeriodResponse)
def update_fiscal_period(
    period_id: int,
    period_update: FiscalPeriodUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Update a fiscal period (admin only)
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    # Can't update closed or locked periods
    if period.status in [FiscalPeriodStatus.CLOSED, FiscalPeriodStatus.LOCKED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update {period.status.value.lower()} period"
        )

    # Update fields if provided
    if period_update.period_name is not None:
        period.period_name = period_update.period_name

    if period_update.quarter is not None:
        period.quarter = period_update.quarter

    if period_update.start_date is not None:
        period.start_date = period_update.start_date

    if period_update.end_date is not None:
        period.end_date = period_update.end_date

    # Validate date range
    if period.end_date <= period.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    db.commit()
    db.refresh(period)
    return period


@router.delete("/{period_id}")
def delete_fiscal_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Delete a fiscal period (admin only)
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    # Can't delete closed or locked periods
    if period.status in [FiscalPeriodStatus.CLOSED, FiscalPeriodStatus.LOCKED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete {period.status.value.lower()} period"
        )

    # TODO: Check if period has any journal entries
    # if period has entries, raise HTTPException

    db.delete(period)
    db.commit()

    return {
        "message": "Fiscal period deleted successfully",
        "year": period.year,
        "period_name": period.period_name
    }


@router.post("/{period_id}/close")
def close_fiscal_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Close a fiscal period (admin only - prevents new entries)
    """
    period = db.query(FiscalPeriod).filter(FiscalPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    if period.status == FiscalPeriodStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Period is already closed")

    if period.status == FiscalPeriodStatus.LOCKED:
        raise HTTPException(status_code=400, detail="Cannot close a locked period")

    period.status = FiscalPeriodStatus.CLOSED
    period.closed_at = get_now()
    period.closed_by = user.id

    db.commit()

    return {
        "message": "Fiscal period closed successfully",
        "year": period.year,
        "period_name": period.period_name
    }


@router.post("/{period_id}/reopen")
def reopen_fiscal_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Reopen a closed fiscal period (admin only)
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
def lock_fiscal_period(
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Lock a fiscal period (admin only - permanent, for audited periods)
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
def create_full_year(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin)
):
    """
    Create all 12 fiscal periods for a year (admin only)
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
