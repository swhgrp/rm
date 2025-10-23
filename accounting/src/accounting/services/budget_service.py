"""Budget service for business logic"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, extract
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict
from calendar import monthrange

from accounting.models.budget import (
    Budget, BudgetPeriod, BudgetLine, BudgetStatus, BudgetPeriodType
)
from accounting.models.account import Account, AccountType
from accounting.models.journal_entry import JournalEntryLine
from accounting.schemas.budget import (
    BudgetCreate, BudgetLineCreate, BudgetVsActualLine, BudgetVsActualReport
)


class BudgetService:
    """Service for budget operations"""

    def __init__(self, db: Session):
        self.db = db

    def create_budget(self, budget_data: BudgetCreate, user_id: int) -> Budget:
        """Create a new budget"""
        budget = Budget(
            budget_name=budget_data.budget_name,
            fiscal_year=budget_data.fiscal_year,
            start_date=budget_data.start_date,
            end_date=budget_data.end_date,
            budget_type=budget_data.budget_type,
            area_id=budget_data.area_id,
            department=budget_data.department,
            description=budget_data.description,
            notes=budget_data.notes,
            status=BudgetStatus.DRAFT,
            created_by=user_id
        )

        self.db.add(budget)
        self.db.flush()

        # Auto-create monthly periods if requested
        if budget_data.create_periods:
            self._create_monthly_periods(budget)

        # Copy from existing budget if specified
        if budget_data.copy_from_budget_id:
            self._copy_budget_lines(
                budget,
                budget_data.copy_from_budget_id,
                budget_data.growth_rate or Decimal(0)
            )

        self.db.commit()
        self.db.refresh(budget)
        return budget

    def _create_monthly_periods(self, budget: Budget):
        """Create monthly periods for a budget"""
        current_date = budget.start_date
        month_num = 1

        while current_date <= budget.end_date:
            # Get last day of month
            last_day = monthrange(current_date.year, current_date.month)[1]
            period_end = date(current_date.year, current_date.month, last_day)

            # Don't go past budget end date
            if period_end > budget.end_date:
                period_end = budget.end_date

            period = BudgetPeriod(
                budget_id=budget.id,
                period_type=BudgetPeriodType.MONTHLY,
                period_number=month_num,
                period_name=current_date.strftime("%B %Y"),
                start_date=current_date,
                end_date=period_end
            )
            self.db.add(period)

            # Move to next month
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)

            month_num += 1

            # Safety check
            if month_num > 12:
                break

    def _copy_budget_lines(self, new_budget: Budget, source_budget_id: int, growth_rate: Decimal):
        """Copy budget lines from another budget"""
        source_lines = self.db.query(BudgetLine).filter(
            BudgetLine.budget_id == source_budget_id
        ).all()

        growth_multiplier = Decimal(1) + (growth_rate / Decimal(100))

        for source_line in source_lines:
            new_amount = source_line.amount * growth_multiplier

            new_line = BudgetLine(
                budget_id=new_budget.id,
                budget_period_id=None,  # Will be set when mapping periods
                account_id=source_line.account_id,
                amount=new_amount,
                notes=f"Copied from budget #{source_budget_id} with {growth_rate}% growth"
            )
            self.db.add(new_line)

    def update_budget_lines(self, budget_id: int, lines: List[BudgetLineCreate]) -> Budget:
        """Update budget lines (replace all)"""
        # Delete existing lines
        self.db.query(BudgetLine).filter(
            BudgetLine.budget_id == budget_id
        ).delete()

        # Add new lines
        for line_data in lines:
            line = BudgetLine(
                budget_id=budget_id,
                budget_period_id=line_data.budget_period_id,
                account_id=line_data.account_id,
                amount=line_data.amount,
                notes=line_data.notes
            )
            self.db.add(line)

        # Recalculate totals
        budget = self.db.query(Budget).filter(Budget.id == budget_id).first()
        self._recalculate_budget_totals(budget)

        self.db.commit()
        self.db.refresh(budget)
        return budget

    def _recalculate_budget_totals(self, budget: Budget):
        """Recalculate budget summary totals"""
        # Get annual totals (lines without period_id)
        annual_lines = self.db.query(
            Account.account_type,
            func.sum(BudgetLine.amount).label('total')
        ).join(
            BudgetLine, Account.id == BudgetLine.account_id
        ).filter(
            BudgetLine.budget_id == budget.id,
            BudgetLine.budget_period_id.is_(None)
        ).group_by(Account.account_type).all()

        total_revenue = Decimal(0)
        total_expenses = Decimal(0)

        for account_type, total in annual_lines:
            if account_type in [AccountType.REVENUE, AccountType.REVENUE_CONTRA]:
                total_revenue += total or Decimal(0)
            elif account_type in [AccountType.EXPENSE, AccountType.EXPENSE_CONTRA]:
                total_expenses += total or Decimal(0)

        budget.total_revenue = total_revenue
        budget.total_expenses = total_expenses
        budget.net_income = total_revenue - total_expenses

    def approve_budget(self, budget_id: int, user_id: int) -> Budget:
        """Approve a budget"""
        budget = self.db.query(Budget).filter(Budget.id == budget_id).first()
        if not budget:
            raise ValueError("Budget not found")

        if budget.status != BudgetStatus.PENDING_APPROVAL:
            budget.status = BudgetStatus.PENDING_APPROVAL

        budget.status = BudgetStatus.APPROVED
        budget.approved_by = user_id
        budget.approved_at = datetime.utcnow()

        # If budget period includes today, make it active
        if budget.start_date <= date.today() <= budget.end_date:
            budget.status = BudgetStatus.ACTIVE

        self.db.commit()
        self.db.refresh(budget)
        return budget

    def get_budget_vs_actual(
        self,
        budget_id: int,
        period_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> BudgetVsActualReport:
        """Generate budget vs actual report"""
        budget = self.db.query(Budget).filter(Budget.id == budget_id).first()
        if not budget:
            raise ValueError("Budget not found")

        # Determine date range
        if period_id:
            period = self.db.query(BudgetPeriod).filter(BudgetPeriod.id == period_id).first()
            report_start = period.start_date
            report_end = period.end_date
            period_name = period.period_name
        elif start_date and end_date:
            report_start = start_date
            report_end = end_date
            period_name = f"{start_date} to {end_date}"
        else:
            report_start = budget.start_date
            report_end = budget.end_date
            period_name = "Full Year"

        # Get budget lines for period
        query = self.db.query(
            BudgetLine.account_id,
            Account.account_number,
            Account.account_name,
            Account.account_type,
            func.sum(BudgetLine.amount).label('budget_amount')
        ).join(
            Account, BudgetLine.account_id == Account.id
        ).filter(
            BudgetLine.budget_id == budget_id
        )

        if period_id:
            query = query.filter(BudgetLine.budget_period_id == period_id)
        else:
            query = query.filter(BudgetLine.budget_period_id.is_(None))

        budget_lines = query.group_by(
            BudgetLine.account_id,
            Account.account_number,
            Account.account_name,
            Account.account_type
        ).all()

        # Get actual amounts from GL
        actual_query = self.db.query(
            JournalEntryLine.account_id,
            func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount).label('actual_amount')
        ).join(
            JournalEntryLine.journal_entry
        ).filter(
            and_(
                JournalEntryLine.journal_entry.has(entry_date=report_start),
                JournalEntryLine.journal_entry.has(entry_date=report_end)
            )
        ).group_by(JournalEntryLine.account_id).all()

        actual_dict = {row.account_id: row.actual_amount for row in actual_query}

        # Build comparison lines
        revenue_lines = []
        expense_lines = []
        total_revenue_budget = Decimal(0)
        total_revenue_actual = Decimal(0)
        total_expenses_budget = Decimal(0)
        total_expenses_actual = Decimal(0)

        for line in budget_lines:
            actual_amt = actual_dict.get(line.account_id, Decimal(0))
            variance = actual_amt - line.budget_amount
            variance_pct = (variance / line.budget_amount * 100) if line.budget_amount != 0 else Decimal(0)

            # Determine if favorable (revenue over budget good, expenses under budget good)
            is_favorable = False
            if line.account_type in [AccountType.REVENUE, AccountType.REVENUE_CONTRA]:
                is_favorable = variance > 0
                total_revenue_budget += line.budget_amount
                total_revenue_actual += actual_amt
            elif line.account_type in [AccountType.EXPENSE, AccountType.EXPENSE_CONTRA]:
                is_favorable = variance < 0
                total_expenses_budget += line.budget_amount
                total_expenses_actual += actual_amt

            comparison_line = BudgetVsActualLine(
                account_id=line.account_id,
                account_number=line.account_number,
                account_name=line.account_name,
                account_type=line.account_type.value,
                budget_amount=line.budget_amount,
                actual_amount=actual_amt,
                variance=variance,
                variance_percent=variance_pct,
                is_favorable=is_favorable
            )

            if line.account_type in [AccountType.REVENUE, AccountType.REVENUE_CONTRA]:
                revenue_lines.append(comparison_line)
            else:
                expense_lines.append(comparison_line)

        # Calculate variances
        revenue_variance = total_revenue_actual - total_revenue_budget
        revenue_variance_pct = (revenue_variance / total_revenue_budget * 100) if total_revenue_budget != 0 else Decimal(0)

        expenses_variance = total_expenses_actual - total_expenses_budget
        expenses_variance_pct = (expenses_variance / total_expenses_budget * 100) if total_expenses_budget != 0 else Decimal(0)

        net_income_budget = total_revenue_budget - total_expenses_budget
        net_income_actual = total_revenue_actual - total_expenses_actual
        net_income_variance = net_income_actual - net_income_budget
        net_income_variance_pct = (net_income_variance / net_income_budget * 100) if net_income_budget != 0 else Decimal(0)

        return BudgetVsActualReport(
            budget_id=budget.id,
            budget_name=budget.budget_name,
            fiscal_year=budget.fiscal_year,
            period_name=period_name,
            start_date=report_start,
            end_date=report_end,
            total_revenue_budget=total_revenue_budget,
            total_revenue_actual=total_revenue_actual,
            total_revenue_variance=revenue_variance,
            total_revenue_variance_percent=revenue_variance_pct,
            total_expenses_budget=total_expenses_budget,
            total_expenses_actual=total_expenses_actual,
            total_expenses_variance=expenses_variance,
            total_expenses_variance_percent=expenses_variance_pct,
            net_income_budget=net_income_budget,
            net_income_actual=net_income_actual,
            net_income_variance=net_income_variance,
            net_income_variance_percent=net_income_variance_pct,
            revenue_lines=revenue_lines,
            expense_lines=expense_lines
        )
