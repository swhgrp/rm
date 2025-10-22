#!/usr/bin/env python3
"""
Dashboard Data Population Script

This script backfills the dashboard tables with historical data:
1. daily_financial_snapshots - Daily aggregated financial metrics
2. monthly_performance_summaries - Closed month performance
3. expense_category_summaries - Top expense tracking
4. dashboard_alerts - System-generated alerts

Usage:
    python populate_dashboard_data.py [--months 12] [--area-id 1]
"""

import sys
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, func, and_, or_, text
from sqlalchemy.orm import sessionmaker, Session
from accounting.models import (
    Account, JournalEntry, JournalEntryLine, JournalEntryStatus,
    Area, VendorBill, BillStatus, CustomerInvoice, InvoiceStatus,
    DailyFinancialSnapshot, MonthlyPerformanceSummary,
    ExpenseCategorySummary, DashboardAlert, DashboardAlertType,
    BankAccount, BankReconciliation
)
from accounting.core.config import settings


class DashboardDataPopulator:
    """Populates dashboard tables with historical data"""

    def __init__(self, db: Session):
        self.db = db

    def populate_all(self, months: int = 12, area_id: Optional[int] = None):
        """Populate all dashboard tables"""
        print(f"🚀 Starting dashboard data population for last {months} months...")

        # Get areas to process
        areas = self._get_areas(area_id)

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=months * 30)

        print(f"📅 Date range: {start_date} to {end_date}")
        print(f"📍 Processing {len(areas)} location(s)")

        # Populate each table
        self.populate_daily_snapshots(start_date, end_date, areas)
        self.populate_monthly_summaries(start_date, end_date, areas)
        self.populate_expense_summaries(start_date, end_date, areas)
        self.generate_alerts(areas)

        print("✅ Dashboard data population complete!")

    def _get_areas(self, area_id: Optional[int] = None) -> List[Area]:
        """Get areas to process"""
        if area_id:
            area = self.db.query(Area).filter(Area.id == area_id).first()
            return [area] if area else []
        else:
            return self.db.query(Area).filter(Area.is_active == True).all()

    def populate_daily_snapshots(self, start_date: date, end_date: date, areas: List[Area]):
        """Populate daily_financial_snapshots table"""
        print("\n📊 Populating daily financial snapshots...")

        current_date = start_date
        total_days = (end_date - start_date).days
        count = 0

        while current_date <= end_date:
            for area in areas:
                # Check if snapshot already exists
                existing = self.db.query(DailyFinancialSnapshot).filter(
                    and_(
                        DailyFinancialSnapshot.snapshot_date == current_date,
                        DailyFinancialSnapshot.area_id == area.id
                    )
                ).first()

                if existing:
                    continue

                # Calculate metrics for this day
                metrics = self._calculate_daily_metrics(current_date, area.id)

                # Create snapshot
                snapshot = DailyFinancialSnapshot(
                    snapshot_date=current_date,
                    area_id=area.id,
                    total_sales=metrics['sales'],
                    total_cogs=metrics['cogs'],
                    gross_profit=metrics['gross_profit'],
                    total_expenses=metrics['expenses'],
                    net_income=metrics['net_income'],
                    labor_expense=metrics['labor'],
                    cogs_percentage=metrics['cogs_pct'],
                    labor_percentage=metrics['labor_pct'],
                    gross_profit_margin=metrics['gross_margin'],
                    transaction_count=metrics['txn_count'],
                    average_check=metrics['avg_check']
                )

                # Calculate derived metrics
                snapshot.calculate_metrics()

                self.db.add(snapshot)
                count += 1

                if count % 100 == 0:
                    self.db.commit()
                    progress = ((current_date - start_date).days / total_days) * 100
                    print(f"  Progress: {progress:.1f}% ({count} snapshots created)")

            current_date += timedelta(days=1)

        self.db.commit()
        print(f"✅ Created {count} daily snapshots")

    def _calculate_daily_metrics(self, snapshot_date: date, area_id: int) -> dict:
        """Calculate financial metrics for a specific day"""

        # Get posted journal entries for this day
        entries = self.db.query(JournalEntryLine).join(JournalEntry).filter(
            and_(
                JournalEntry.entry_date == snapshot_date,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntryLine.area_id == area_id
            )
        ).all()

        # Initialize metrics
        sales = Decimal('0.00')
        cogs = Decimal('0.00')
        labor = Decimal('0.00')
        other_expenses = Decimal('0.00')
        txn_count = 0

        # Sum by account type
        for line in entries:
            account = line.account
            amount = line.credit_amount - line.debit_amount  # Net effect

            if account.account_number.startswith('4'):  # Revenue
                sales += amount
                if 'sales' in account.account_name.lower():
                    txn_count += 1  # Approximate
            elif account.account_number.startswith('5'):  # COGS
                cogs += abs(amount)
            elif account.account_number.startswith('6'):  # Expenses
                if 'labor' in account.account_name.lower() or 'payroll' in account.account_name.lower():
                    labor += abs(amount)
                else:
                    other_expenses += abs(amount)

        # Calculate derived metrics
        gross_profit = sales - cogs
        expenses = labor + other_expenses
        net_income = gross_profit - expenses

        cogs_pct = (cogs / sales * 100) if sales > 0 else Decimal('0.00')
        labor_pct = (labor / sales * 100) if sales > 0 else Decimal('0.00')
        gross_margin = (gross_profit / sales * 100) if sales > 0 else Decimal('0.00')
        avg_check = (sales / txn_count) if txn_count > 0 else Decimal('0.00')

        # Get cash balance as of this date
        cash_balance = self._get_cash_balance(snapshot_date, area_id)

        # Get AP/AR outstanding as of this date
        ap_outstanding = self._get_ap_outstanding(snapshot_date, area_id)
        ar_outstanding = self._get_ar_outstanding(snapshot_date, area_id)

        return {
            'sales': sales,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'expenses': expenses,
            'net_income': net_income,
            'labor': labor,
            'other_expenses': other_expenses,
            'cogs_pct': cogs_pct,
            'labor_pct': labor_pct,
            'gross_margin': gross_margin,
            'txn_count': txn_count or 1,  # Avoid zero
            'avg_check': avg_check,
            'cash_balance': cash_balance,
            'ap_outstanding': ap_outstanding,
            'ar_outstanding': ar_outstanding
        }

    def _get_cash_balance(self, as_of_date: date, area_id: int) -> Decimal:
        """Get total cash balance as of a specific date"""

        # Get cash accounts (1000-series)
        result = self.db.query(
            func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount)
        ).join(JournalEntry).join(Account).filter(
            and_(
                Account.account_number.like('1000%'),
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntryLine.area_id == area_id
            )
        ).scalar()

        return result or Decimal('0.00')

    def _get_ap_outstanding(self, as_of_date: date, area_id: int) -> Decimal:
        """Get total AP outstanding as of a specific date"""

        result = self.db.query(func.sum(VendorBill.total_amount - VendorBill.paid_amount)).filter(
            and_(
                VendorBill.bill_date <= as_of_date,
                VendorBill.status != BillStatus.PAID,
                VendorBill.area_id == area_id
            )
        ).scalar()

        return result or Decimal('0.00')

    def _get_ar_outstanding(self, as_of_date: date, area_id: int) -> Decimal:
        """Get total AR outstanding as of a specific date"""

        result = self.db.query(func.sum(CustomerInvoice.total_amount)).filter(
            and_(
                CustomerInvoice.invoice_date <= as_of_date,
                CustomerInvoice.status != InvoiceStatus.PAID,
                CustomerInvoice.area_id == area_id
            )
        ).scalar()

        return result or Decimal('0.00')

    def populate_monthly_summaries(self, start_date: date, end_date: date, areas: List[Area]):
        """Populate monthly_performance_summaries table"""
        print("\n📈 Populating monthly performance summaries...")

        count = 0
        current_month = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)

        while current_month <= end_month:
            for area in areas:
                # Check if summary already exists
                existing = self.db.query(MonthlyPerformanceSummary).filter(
                    and_(
                        MonthlyPerformanceSummary.period_month == current_month,
                        MonthlyPerformanceSummary.area_id == area.id
                    )
                ).first()

                if existing:
                    continue

                # Calculate month-end date
                if current_month.month == 12:
                    month_end = date(current_month.year + 1, 1, 1) - timedelta(days=1)
                else:
                    month_end = date(current_month.year, current_month.month + 1, 1) - timedelta(days=1)

                # Get daily snapshots for this month
                snapshots = self.db.query(DailyFinancialSnapshot).filter(
                    and_(
                        DailyFinancialSnapshot.snapshot_date >= current_month,
                        DailyFinancialSnapshot.snapshot_date <= month_end,
                        DailyFinancialSnapshot.area_id == area.id
                    )
                ).all()

                if not snapshots:
                    current_month = self._add_months(current_month, 1)
                    continue

                # Aggregate monthly totals
                total_revenue = sum(s.total_sales for s in snapshots)
                total_cogs = sum(s.total_cogs for s in snapshots)
                labor_expense = sum(s.labor_expense or Decimal('0.00') for s in snapshots)
                total_expenses = sum(s.total_expenses for s in snapshots)
                other_expenses = total_expenses - labor_expense

                gross_profit = total_revenue - total_cogs
                net_income = gross_profit - total_expenses

                # Calculate percentages
                cogs_pct = (total_cogs / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
                labor_pct = (labor_expense / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
                prime_cost = cogs_pct + labor_pct
                gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')

                # Get prior month for comparison
                prior_month = self._add_months(current_month, -1)
                prior_summary = self.db.query(MonthlyPerformanceSummary).filter(
                    and_(
                        MonthlyPerformanceSummary.period_month == prior_month,
                        MonthlyPerformanceSummary.area_id == area.id
                    )
                ).first()

                vs_prior_revenue = Decimal('0.00')
                vs_prior_net_income = Decimal('0.00')

                if prior_summary and prior_summary.total_revenue > 0:
                    vs_prior_revenue = ((total_revenue - prior_summary.total_revenue) / prior_summary.total_revenue * 100)
                    vs_prior_net_income = ((net_income - prior_summary.net_income) / prior_summary.net_income * 100) if prior_summary.net_income != 0 else Decimal('0.00')

                # Create summary
                summary = MonthlyPerformanceSummary(
                    period_month=current_month,
                    area_id=area.id,
                    is_closed=(month_end < date.today()),
                    total_revenue=total_revenue,
                    total_cogs=total_cogs,
                    gross_profit=gross_profit,
                    labor_expense=labor_expense,
                    other_expenses=other_expenses,
                    net_income=net_income,
                    cogs_percentage=cogs_pct,
                    labor_percentage=labor_pct,
                    prime_cost=prime_cost,
                    gross_profit_margin=gross_margin,
                    vs_prior_month_revenue=vs_prior_revenue,
                    vs_prior_month_net_income=vs_prior_net_income
                )

                self.db.add(summary)
                count += 1

            current_month = self._add_months(current_month, 1)

        self.db.commit()
        print(f"✅ Created {count} monthly summaries")

    def populate_expense_summaries(self, start_date: date, end_date: date, areas: List[Area]):
        """Populate expense_category_summaries table"""
        print("\n💰 Populating expense category summaries...")

        count = 0
        current_month = date(start_date.year, start_date.month, 1)
        end_month = date(end_date.year, end_date.month, 1)

        # Define expense categories (map account codes to categories)
        expense_categories = {
            '6100': 'Labor & Payroll',
            '6200': 'Rent & Occupancy',
            '6300': 'Utilities',
            '6400': 'Marketing & Advertising',
            '6500': 'Repairs & Maintenance',
            '6600': 'Supplies',
            '6700': 'Insurance',
            '6800': 'Professional Fees',
            '6900': 'Other Operating Expenses'
        }

        while current_month <= end_month:
            for area in areas:
                # Calculate month-end date
                if current_month.month == 12:
                    month_end = date(current_month.year + 1, 1, 1) - timedelta(days=1)
                else:
                    month_end = date(current_month.year, current_month.month + 1, 1) - timedelta(days=1)

                # Get revenue for percentage calculation
                revenue = self.db.query(func.sum(DailyFinancialSnapshot.total_sales)).filter(
                    and_(
                        DailyFinancialSnapshot.snapshot_date >= current_month,
                        DailyFinancialSnapshot.snapshot_date <= month_end,
                        DailyFinancialSnapshot.area_id == area.id
                    )
                ).scalar() or Decimal('0.00')

                # Calculate expenses by category
                for code_prefix, category_name in expense_categories.items():
                    # Get expense accounts in this category
                    accounts = self.db.query(Account).filter(
                        Account.account_number.like(f'{code_prefix}%')
                    ).all()

                    if not accounts:
                        continue

                    account_ids = [a.id for a in accounts]

                    # Sum expenses for this category
                    current_month_total = self.db.query(
                        func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount)
                    ).join(JournalEntry).filter(
                        and_(
                            JournalEntryLine.account_id.in_(account_ids),
                            JournalEntry.entry_date >= current_month,
                            JournalEntry.entry_date <= month_end,
                            JournalEntry.status == JournalEntryStatus.POSTED,
                            JournalEntryLine.area_id == area.id
                        )
                    ).scalar() or Decimal('0.00')

                    if current_month_total <= 0:
                        continue

                    # Calculate YTD
                    year_start = date(current_month.year, 1, 1)
                    ytd_total = self.db.query(
                        func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount)
                    ).join(JournalEntry).filter(
                        and_(
                            JournalEntryLine.account_id.in_(account_ids),
                            JournalEntry.entry_date >= year_start,
                            JournalEntry.entry_date <= month_end,
                            JournalEntry.status == JournalEntryStatus.POSTED,
                            JournalEntryLine.area_id == area.id
                        )
                    ).scalar() or Decimal('0.00')

                    # Calculate percentage of revenue
                    pct_of_revenue = (current_month_total / revenue * 100) if revenue > 0 else Decimal('0.00')

                    # Check if already exists
                    existing = self.db.query(ExpenseCategorySummary).filter(
                        and_(
                            ExpenseCategorySummary.period_month == current_month,
                            ExpenseCategorySummary.area_id == area.id,
                            ExpenseCategorySummary.category_name == category_name
                        )
                    ).first()

                    if existing:
                        continue

                    # Create summary
                    summary = ExpenseCategorySummary(
                        period_month=current_month,
                        area_id=area.id,
                        category_name=category_name,
                        account_id=accounts[0].id,  # Use first account as representative
                        current_month=current_month_total,
                        ytd_total=ytd_total,
                        pct_of_revenue=pct_of_revenue,
                        rank_by_amount=0  # Will be calculated after all inserted
                    )

                    self.db.add(summary)
                    count += 1

                # Rank expenses for this month/area
                self._rank_expenses(current_month, area.id)

            current_month = self._add_months(current_month, 1)

        self.db.commit()
        print(f"✅ Created {count} expense summaries")

    def _rank_expenses(self, period_month: date, area_id: int):
        """Rank expenses by amount for a specific month/area"""
        summaries = self.db.query(ExpenseCategorySummary).filter(
            and_(
                ExpenseCategorySummary.period_month == period_month,
                ExpenseCategorySummary.area_id == area_id
            )
        ).order_by(ExpenseCategorySummary.current_month.desc()).all()

        for rank, summary in enumerate(summaries, start=1):
            summary.rank_by_amount = rank

    def generate_alerts(self, areas: List[Area]):
        """Generate dashboard alerts based on current system state"""
        print("\n⚠️  Generating dashboard alerts...")

        count = 0

        for area in areas:
            # 1. Check for unposted journal entries
            unposted_count = self.db.query(JournalEntry).filter(
                and_(
                    JournalEntry.status == JournalEntryStatus.DRAFT,
                    JournalEntry.lines.any(JournalEntryLine.area_id == area.id)
                )
            ).count()

            if unposted_count > 0:
                self._create_alert(
                    alert_type=DashboardAlertType.UNPOSTED_JOURNAL,
                    severity='warning',
                    area_id=area.id,
                    title=f"{unposted_count} Unposted Journal Entries",
                    message=f"There are {unposted_count} journal entries in DRAFT status that need to be posted to the general ledger.",
                    action_url="/accounting/journal-entries?status=DRAFT"
                )
                count += 1

            # 2. Check for pending bank reconciliations
            pending_recon_count = self.db.query(BankAccount).filter(
                BankAccount.area_id == area.id
            ).count()

            if pending_recon_count > 0:
                # Check if any accounts haven't been reconciled in 30+ days
                last_recon = self.db.query(func.max(BankReconciliation.reconciliation_date)).filter(
                    BankReconciliation.bank_account.has(area_id=area.id)
                ).scalar()

                if last_recon is None or (date.today() - last_recon).days > 30:
                    self._create_alert(
                        alert_type=DashboardAlertType.PENDING_RECONCILIATION,
                        severity='critical',
                        area_id=area.id,
                        title="Bank Reconciliation Overdue",
                        message=f"Bank accounts for {area.name} haven't been reconciled in over 30 days.",
                        action_url="/accounting/bank-reconciliation"
                    )
                    count += 1

            # 3. Check for high COGS percentage
            recent_snapshot = self.db.query(DailyFinancialSnapshot).filter(
                DailyFinancialSnapshot.area_id == area.id
            ).order_by(DailyFinancialSnapshot.snapshot_date.desc()).first()

            if recent_snapshot and recent_snapshot.cogs_percentage > 35:
                self._create_alert(
                    alert_type=DashboardAlertType.COGS_HIGH,
                    severity='warning',
                    area_id=area.id,
                    title=f"High COGS Percentage: {recent_snapshot.cogs_percentage:.1f}%",
                    message=f"COGS percentage for {area.name} is {recent_snapshot.cogs_percentage:.1f}%, which exceeds the target of 32%.",
                    action_url="/accounting/reports"
                )
                count += 1

            # 4. Check for high AP aging
            ap_90plus = self.db.query(func.sum(VendorBill.total_amount - VendorBill.paid_amount)).filter(
                and_(
                    VendorBill.area_id == area.id,
                    VendorBill.status != BillStatus.PAID,
                    VendorBill.due_date < (date.today() - timedelta(days=90))
                )
            ).scalar() or Decimal('0.00')

            if ap_90plus > 1000:
                self._create_alert(
                    alert_type=DashboardAlertType.AP_AGING_HIGH,
                    severity='critical',
                    area_id=area.id,
                    title=f"High Aged Payables: ${ap_90plus:,.2f}",
                    message=f"{area.name} has ${ap_90plus:,.2f} in payables over 90 days old.",
                    action_url="/accounting/ap-aging"
                )
                count += 1

            # 5. Check for negative cash balance
            if recent_snapshot and recent_snapshot.cash_balance < 0:
                self._create_alert(
                    alert_type=DashboardAlertType.NEGATIVE_CASH,
                    severity='critical',
                    area_id=area.id,
                    title="Negative Cash Balance",
                    message=f"{area.name} has a negative cash balance of ${recent_snapshot.cash_balance:,.2f}.",
                    action_url="/accounting/bank-accounts"
                )
                count += 1

        self.db.commit()
        print(f"✅ Generated {count} alerts")

    def _create_alert(self, alert_type: DashboardAlertType, severity: str,
                      area_id: int, title: str, message: str, action_url: str):
        """Create a dashboard alert if it doesn't already exist"""

        # Check if alert already exists and is active
        existing = self.db.query(DashboardAlert).filter(
            and_(
                DashboardAlert.alert_type == alert_type,
                DashboardAlert.area_id == area_id,
                DashboardAlert.is_active == True,
                DashboardAlert.is_resolved == False
            )
        ).first()

        if existing:
            return

        alert = DashboardAlert(
            alert_type=alert_type,
            severity=severity,
            area_id=area_id,
            title=title,
            message=message,
            action_url=action_url,
            is_active=True,
            is_acknowledged=False,
            is_resolved=False,
            created_at=datetime.now()
        )

        self.db.add(alert)

    def _add_months(self, source_date: date, months: int) -> date:
        """Add months to a date"""
        month = source_date.month - 1 + months
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Populate dashboard data')
    parser.add_argument('--months', type=int, default=12, help='Number of months to backfill (default: 12)')
    parser.add_argument('--area-id', type=int, help='Specific area ID to process (default: all areas)')
    parser.add_argument('--skip-snapshots', action='store_true', help='Skip daily snapshots')
    parser.add_argument('--skip-summaries', action='store_true', help='Skip monthly summaries')
    parser.add_argument('--skip-expenses', action='store_true', help='Skip expense summaries')
    parser.add_argument('--skip-alerts', action='store_true', help='Skip alert generation')

    args = parser.parse_args()

    # Create database engine
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        populator = DashboardDataPopulator(db)

        # Get areas
        areas = populator._get_areas(args.area_id)
        if not areas:
            print("❌ No areas found to process")
            return

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=args.months * 30)

        print(f"🚀 Starting dashboard data population")
        print(f"📅 Date range: {start_date} to {end_date}")
        print(f"📍 Processing {len(areas)} location(s)")

        # Populate tables based on flags
        if not args.skip_snapshots:
            populator.populate_daily_snapshots(start_date, end_date, areas)

        if not args.skip_summaries:
            populator.populate_monthly_summaries(start_date, end_date, areas)

        if not args.skip_expenses:
            populator.populate_expense_summaries(start_date, end_date, areas)

        if not args.skip_alerts:
            populator.generate_alerts(areas)

        print("\n✅ Dashboard data population complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
