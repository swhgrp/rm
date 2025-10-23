"""Budget API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import date

from accounting.db.database import get_db
from accounting.models.budget import Budget, BudgetLine, BudgetPeriod, BudgetStatus
from accounting.models.user import User
from accounting.models.area import Area
from accounting.schemas.budget import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
    BudgetSummary,
    BudgetLineCreate,
    BudgetLineResponse,
    BulkBudgetLineUpdate,
    BudgetApprovalRequest,
    BudgetVsActualReport
)
from accounting.services.budget_service import BudgetService
from accounting.api.auth import require_auth

router = APIRouter()


@router.get("/", response_model=List[BudgetSummary])
def list_budgets(
    fiscal_year: Optional[int] = None,
    status: Optional[str] = None,
    area_id: Optional[int] = None,
    budget_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List all budgets with optional filters"""
    query = db.query(Budget).options(
        joinedload(Budget.area)
    )

    if fiscal_year:
        query = query.filter(Budget.fiscal_year == fiscal_year)
    if status:
        query = query.filter(Budget.status == status)
    if area_id:
        query = query.filter(Budget.area_id == area_id)
    if budget_type:
        query = query.filter(Budget.budget_type == budget_type)

    budgets = query.order_by(Budget.fiscal_year.desc(), Budget.created_at.desc()).all()

    return [
        BudgetSummary(
            id=b.id,
            budget_name=b.budget_name,
            fiscal_year=b.fiscal_year,
            budget_type=b.budget_type,
            status=b.status.value,
            area_name=b.area.name if b.area else None,
            department=b.department,
            total_revenue=b.total_revenue,
            total_expenses=b.total_expenses,
            net_income=b.net_income,
            start_date=b.start_date,
            end_date=b.end_date,
            created_at=b.created_at
        )
        for b in budgets
    ]


@router.post("/", response_model=BudgetResponse)
def create_budget(
    budget: BudgetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create a new budget"""
    service = BudgetService(db)
    return service.create_budget(budget, user.id)


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get budget details"""
    budget = db.query(Budget).options(
        joinedload(Budget.area),
        joinedload(Budget.creator),
        joinedload(Budget.approver),
        joinedload(Budget.periods).joinedload(BudgetPeriod.lines)
    ).filter(Budget.id == budget_id).first()

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    return budget


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: int,
    budget_update: BudgetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update budget"""
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    update_data = budget_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(budget, field, value)

    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete budget"""
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.status in [BudgetStatus.APPROVED, BudgetStatus.ACTIVE]:
        raise HTTPException(status_code=400, detail="Cannot delete approved or active budgets")

    db.delete(budget)
    db.commit()
    return {"message": "Budget deleted successfully"}


@router.get("/{budget_id}/lines", response_model=List[BudgetLineResponse])
def get_budget_lines(
    budget_id: int,
    period_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get budget lines for a budget"""
    query = db.query(BudgetLine).filter(BudgetLine.budget_id == budget_id)

    if period_id:
        query = query.filter(BudgetLine.budget_period_id == period_id)
    else:
        query = query.filter(BudgetLine.budget_period_id.is_(None))

    return query.all()


@router.put("/{budget_id}/lines", response_model=BudgetResponse)
def update_budget_lines(
    budget_id: int,
    lines_update: BulkBudgetLineUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update all budget lines (bulk replace)"""
    service = BudgetService(db)
    return service.update_budget_lines(budget_id, lines_update.lines)


@router.post("/{budget_id}/approve", response_model=BudgetResponse)
def approve_budget(
    budget_id: int,
    approval: BudgetApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Approve or reject budget"""
    service = BudgetService(db)

    if approval.action == "approve":
        return service.approve_budget(budget_id, user.id)
    else:
        budget = db.query(Budget).filter(Budget.id == budget_id).first()
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")

        budget.status = BudgetStatus.REJECTED
        budget.notes = (budget.notes or "") + f"\n\nRejected: {approval.notes}"
        db.commit()
        db.refresh(budget)
        return budget


@router.get("/{budget_id}/vs-actual", response_model=BudgetVsActualReport)
def budget_vs_actual(
    budget_id: int,
    period_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get budget vs actual report"""
    service = BudgetService(db)
    return service.get_budget_vs_actual(budget_id, period_id, start_date, end_date)


@router.get("/{budget_id}/copy", response_model=BudgetResponse)
def copy_budget(
    budget_id: int,
    new_fiscal_year: int = Query(...),
    growth_rate: float = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Copy budget to new fiscal year"""
    source_budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not source_budget:
        raise HTTPException(status_code=404, detail="Source budget not found")

    service = BudgetService(db)

    # Create budget data from source
    budget_data = BudgetCreate(
        budget_name=f"{source_budget.budget_name} - FY{new_fiscal_year}",
        fiscal_year=new_fiscal_year,
        start_date=date(new_fiscal_year, 1, 1),
        end_date=date(new_fiscal_year, 12, 31),
        budget_type=source_budget.budget_type,
        area_id=source_budget.area_id,
        department=source_budget.department,
        description=f"Copied from {source_budget.budget_name}",
        copy_from_budget_id=budget_id,
        growth_rate=growth_rate
    )

    return service.create_budget(budget_data, user.id)
