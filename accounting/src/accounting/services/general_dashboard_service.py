"""
General Accounting Dashboard Service

Calculates real-time and historical financial metrics for the dashboard.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, extract
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from accounting.models.account import Account, AccountType
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.daily_sales_summary import DailySalesSummary
from accounting.models.vendor_bill import VendorBill, BillStatus
from accounting.models.area import Area
from accounting.models.bank_account import BankAccount, BankTransaction
from accounting.models.general_dashboard import (
    DailyFinancialSnapshot,
    MonthlyPerformanceSummary,
    DashboardAlert,
    ExpenseCategorySummary,
    DashboardAlertType
)
from accounting.schemas.general_dashboard import *


class GeneralDashboardService:
    """Service for calculating dashboard metrics"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Executive Summary
    # ========================================================================

    def get_executive_summary(
        self,
        as_of_date: date = None,
        area_id: Optional[int] = None
    ) -> ExecutiveSummaryResponse:
        """Get executive summary metrics"""
        if not as_of_date:
            as_of_date = date.today()

        # Get month-to-date and year-to-date periods
        month_start = date(as_of_date.year, as_of_date.month, 1)
        year_start = date(as_of_date.year, 1, 1)

        # Calculate key metrics
        net_income_mtd = self._calculate_net_income(month_start, as_of_date, area_id)
        net_income_ytd = self._calculate_net_income(year_start, as_of_date, area_id)
        revenue_mtd = self._get_revenue(month_start, as_of_date, area_id)
        revenue_ytd = self._get_revenue(year_start, as_of_date, area_id)

        # Calculate margins (use MTD for current period)
        cogs_mtd = self._get_cogs(month_start, as_of_date, area_id)
        expenses_mtd = self._get_expenses(month_start, as_of_date, area_id)
        labor_mtd = self._get_labor_expense(month_start, as_of_date, area_id)

        gross_profit_margin = ((revenue_mtd - cogs_mtd) / revenue_mtd * 100) if revenue_mtd > 0 else Decimal('0.00')
        operating_margin = ((revenue_mtd - cogs_mtd - expenses_mtd) / revenue_mtd * 100) if revenue_mtd > 0 else Decimal('0.00')
        prime_cost_pct = ((cogs_mtd + labor_mtd) / revenue_mtd * 100) if revenue_mtd > 0 else Decimal('0.00')

        # Prior month comparison
        prior_month_start = (month_start - timedelta(days=1)).replace(day=1)
        prior_month_end = month_start - timedelta(days=1)

        revenue_prior = self._get_revenue(prior_month_start, prior_month_end, area_id)
        net_income_prior = self._calculate_net_income(prior_month_start, prior_month_end, area_id)

        revenue_vs_prior = ((revenue_mtd - revenue_prior) / revenue_prior * 100) if revenue_prior > 0 else Decimal('0.00')
        ni_vs_prior = ((net_income_mtd - net_income_prior) / net_income_prior * 100) if net_income_prior != 0 else Decimal('0.00')

        metrics = ExecutiveSummaryMetrics(
            net_income_mtd=net_income_mtd,
            net_income_ytd=net_income_ytd,
            total_revenue_mtd=revenue_mtd,
            total_revenue_ytd=revenue_ytd,
            gross_profit_margin=gross_profit_margin,
            operating_margin=operating_margin,
            prime_cost_percentage=prime_cost_pct,
            revenue_vs_prior_month=revenue_vs_prior,
            net_income_vs_prior_month=ni_vs_prior
        )

        # Top 5 expenses
        top_expenses = self._get_top_expense_categories(month_start, as_of_date, area_id, limit=5)

        # Revenue by location
        revenue_by_location = self._get_revenue_by_location(month_start, as_of_date)

        # Revenue by category
        revenue_categories = self._get_revenue_by_category(month_start, as_of_date, area_id)

        return ExecutiveSummaryResponse(
            metrics=metrics,
            top_expenses=top_expenses,
            revenue_by_location=revenue_by_location,
            revenue_categories=revenue_categories,
            as_of_date=as_of_date
        )

    # ========================================================================
    # Real-Time Tracking
    # ========================================================================

    def get_real_time_tracking(
        self,
        as_of_date: date = None,
        area_id: Optional[int] = None
    ) -> RealTimeTrackingResponse:
        """Get real-time tracking metrics"""
        if not as_of_date:
            as_of_date = date.today()

        month_start = date(as_of_date.year, as_of_date.month, 1)

        # Daily sales metrics
        daily_sales = self._get_daily_sales_metrics(as_of_date, area_id)

        # COGS metrics
        cogs = self._get_cogs_metrics(as_of_date, area_id)

        # Bank balance
        bank_balance = self._get_bank_balance_summary(area_id)

        # Cash flow forecast
        cash_flow_forecast = self._get_cash_flow_forecast(area_id)

        # AP aging
        ap_aging = self._get_ap_aging_summary(area_id)

        # Accounting health
        accounting_health = self._get_accounting_health_metrics(area_id)

        return RealTimeTrackingResponse(
            daily_sales=daily_sales,
            cogs=cogs,
            bank_balance=bank_balance,
            cash_flow_forecast=cash_flow_forecast,
            ap_aging=ap_aging,
            accounting_health=accounting_health,
            as_of_datetime=datetime.now()
        )

    # ========================================================================
    # Historical Trends
    # ========================================================================

    def get_historical_trends(
        self,
        months: int = 6,
        area_id: Optional[int] = None
    ) -> HistoricalTrendResponse:
        """Get historical performance trends"""
        # Get last N closed months
        trend_data = []

        for i in range(months, 0, -1):
            period = date.today().replace(day=1) - timedelta(days=32 * i)
            period = period.replace(day=1)

            # Try to get from monthly_performance_summaries first
            summary = self.db.query(MonthlyPerformanceSummary).filter(
                MonthlyPerformanceSummary.period_month == period,
                MonthlyPerformanceSummary.area_id == area_id if area_id else True
            ).first()

            if summary:
                trend_data.append(MonthlyPerformancePoint(
                    period_month=summary.period_month,
                    revenue=summary.total_revenue,
                    cogs_pct=summary.cogs_percentage or Decimal('0.00'),
                    labor_pct=summary.labor_percentage,
                    net_income=summary.net_income,
                    net_income_margin=summary.net_income_margin or Decimal('0.00')
                ))
            else:
                # Calculate from GL if not closed
                period_end = (period.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                revenue = self._get_revenue(period, period_end, area_id)
                cogs = self._get_cogs(period, period_end, area_id)
                net_income = self._calculate_net_income(period, period_end, area_id)

                cogs_pct = (cogs / revenue * 100) if revenue > 0 else Decimal('0.00')
                ni_margin = (net_income / revenue * 100) if revenue > 0 else Decimal('0.00')

                trend_data.append(MonthlyPerformancePoint(
                    period_month=period,
                    revenue=revenue,
                    cogs_pct=cogs_pct,
                    labor_pct=None,  # Not available without closeout
                    net_income=net_income,
                    net_income_margin=ni_margin
                ))

        # Determine trends
        revenue_trend = self._determine_trend([p.revenue for p in trend_data])
        cogs_trend = self._determine_trend([p.cogs_pct for p in trend_data])
        ni_trend = self._determine_trend([p.net_income for p in trend_data])

        return HistoricalTrendResponse(
            months=trend_data,
            revenue_trend=revenue_trend,
            cogs_trend=cogs_trend,
            net_income_trend=ni_trend
        )

    # ========================================================================
    # Alerts
    # ========================================================================

    def get_alert_summary(self, area_id: Optional[int] = None) -> AlertSummaryResponse:
        """Get active alerts summary"""
        query = self.db.query(DashboardAlert).filter(
            DashboardAlert.is_active == True
        )

        if area_id:
            query = query.filter(
                or_(
                    DashboardAlert.area_id == area_id,
                    DashboardAlert.area_id == None
                )
            )

        alerts = query.order_by(DashboardAlert.created_at.desc()).all()

        # Count by severity
        critical_count = sum(1 for a in alerts if a.severity == 'critical')
        warning_count = sum(1 for a in alerts if a.severity == 'warning')
        info_count = sum(1 for a in alerts if a.severity == 'info')

        # Convert to response models
        alert_responses = []
        for alert in alerts:
            area_name = None
            if alert.area_id:
                area = self.db.query(Area).filter(Area.id == alert.area_id).first()
                if area:
                    area_name = area.name

            alert_responses.append(DashboardAlertResponse(
                id=alert.id,
                alert_type=alert.alert_type.value,
                severity=alert.severity,
                title=alert.title,
                message=alert.message,
                metric_value=alert.metric_value,
                threshold_value=alert.threshold_value,
                action_url=alert.action_url,
                area_id=alert.area_id,
                area_name=area_name,
                is_active=alert.is_active,
                is_acknowledged=alert.is_acknowledged,
                acknowledged_by=alert.acknowledged_by,
                acknowledged_at=alert.acknowledged_at,
                is_resolved=alert.is_resolved,
                created_at=alert.created_at
            ))

        return AlertSummaryResponse(
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            total_active=len(alerts),
            alerts=alert_responses
        )

    # ========================================================================
    # Helper Methods - GL Queries
    # ========================================================================

    def _get_revenue(self, start_date: date, end_date: date, area_id: Optional[int]) -> Decimal:
        """Get total revenue for period (net of discounts/contra-revenue)"""
        # Get revenue credits (gross sales)
        revenue_credits = self._get_account_type_balance(
            AccountType.REVENUE,
            start_date,
            end_date,
            area_id,
            is_credit=True
        )

        # Get revenue debits (discounts, comps, employee meals, waste - contra-revenue)
        revenue_debits = self._get_account_type_balance(
            AccountType.REVENUE,
            start_date,
            end_date,
            area_id,
            is_credit=False
        )

        # Net revenue = Credits - Debits
        return revenue_credits - revenue_debits

    def _get_cogs(self, start_date: date, end_date: date, area_id: Optional[int]) -> Decimal:
        """Get total COGS for period"""
        return self._get_account_type_balance(
            AccountType.COGS,
            start_date,
            end_date,
            area_id,
            is_credit=False
        )

    def _get_expenses(self, start_date: date, end_date: date, area_id: Optional[int]) -> Decimal:
        """Get total expenses for period"""
        return self._get_account_type_balance(
            AccountType.EXPENSE,
            start_date,
            end_date,
            area_id,
            is_credit=False
        )

    def _get_labor_expense(self, start_date: date, end_date: date, area_id: Optional[int]) -> Decimal:
        """Get labor expense for period"""
        query = self.db.query(
            func.sum(JournalEntryLine.debit_amount).label('total')
        ).join(
            JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id
        ).join(
            Account, JournalEntryLine.account_id == Account.id
        ).filter(
            Account.account_type == AccountType.EXPENSE,
            Account.account_name.ilike('%labor%') | Account.account_name.ilike('%payroll%') | Account.account_name.ilike('%wage%'),
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        if area_id:
            query = query.filter(JournalEntryLine.area_id == area_id)

        result = query.scalar()
        return Decimal(str(result)) if result else Decimal('0.00')

    def _calculate_net_income(self, start_date: date, end_date: date, area_id: Optional[int]) -> Decimal:
        """Calculate net income for period"""
        revenue = self._get_revenue(start_date, end_date, area_id)
        cogs = self._get_cogs(start_date, end_date, area_id)
        expenses = self._get_expenses(start_date, end_date, area_id)
        return revenue - cogs - expenses

    def _get_account_type_balance(
        self,
        account_type: AccountType,
        start_date: date,
        end_date: date,
        area_id: Optional[int],
        is_credit: bool
    ) -> Decimal:
        """Get total balance for account type"""
        query = self.db.query(
            func.sum(JournalEntryLine.credit_amount if is_credit else JournalEntryLine.debit_amount).label('total')
        ).join(
            JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id
        ).join(
            Account, JournalEntryLine.account_id == Account.id
        ).filter(
            Account.account_type == account_type,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        if area_id:
            query = query.filter(JournalEntryLine.area_id == area_id)

        result = query.scalar()
        return Decimal(str(result)) if result else Decimal('0.00')

    # ========================================================================
    # Helper Methods - Other Metrics
    # ========================================================================

    def _get_daily_sales_metrics(self, as_of_date: date, area_id: Optional[int]) -> DailySalesMetrics:
        """Get daily sales metrics from Daily Sales Summary (posted entries)"""
        # Get today's sales from posted DSS entries
        today_query = self.db.query(
            func.sum(DailySalesSummary.net_sales).label('total')
        ).filter(
            DailySalesSummary.business_date == as_of_date,
            DailySalesSummary.status == 'posted'
        )

        if area_id:
            today_query = today_query.filter(DailySalesSummary.area_id == area_id)

        today_sales = today_query.scalar() or Decimal('0.00')

        # MTD sales
        month_start = date(as_of_date.year, as_of_date.month, 1)
        mtd_query = self.db.query(
            func.sum(DailySalesSummary.net_sales).label('total'),
            func.count(func.distinct(DailySalesSummary.business_date)).label('days'),
            func.sum(DailySalesSummary.pos_transaction_count).label('transactions')
        ).filter(
            DailySalesSummary.business_date >= month_start,
            DailySalesSummary.business_date <= as_of_date,
            DailySalesSummary.status == 'posted'
        )

        if area_id:
            mtd_query = mtd_query.filter(DailySalesSummary.area_id == area_id)

        mtd_result = mtd_query.first()
        mtd_sales = Decimal(str(mtd_result[0])) if mtd_result[0] else Decimal('0.00')
        mtd_days = mtd_result[1] or 1
        transaction_count = mtd_result[2] or 0

        mtd_avg = mtd_sales / mtd_days if mtd_days > 0 else Decimal('0.00')
        avg_check = mtd_sales / transaction_count if transaction_count > 0 else Decimal('0.00')

        # Prior day
        prior_day = as_of_date - timedelta(days=1)
        prior_day_query = self.db.query(
            func.sum(DailySalesSummary.net_sales)
        ).filter(
            DailySalesSummary.business_date == prior_day,
            DailySalesSummary.status == 'posted'
        )

        if area_id:
            prior_day_query = prior_day_query.filter(DailySalesSummary.area_id == area_id)

        prior_day_sales = prior_day_query.scalar() or Decimal('0.00')

        vs_prior = ((today_sales - prior_day_sales) / prior_day_sales * 100) if prior_day_sales > 0 else Decimal('0.00')

        return DailySalesMetrics(
            today_sales=today_sales,
            mtd_sales=mtd_sales,
            mtd_avg_daily=mtd_avg,
            vs_prior_day=vs_prior,
            vs_prior_month_same_day=None,  # TODO: Calculate if needed
            transaction_count=transaction_count,
            average_check=avg_check
        )

    def _get_cogs_metrics(self, as_of_date: date, area_id: Optional[int]) -> COGSMetrics:
        """Get COGS metrics"""
        month_start = date(as_of_date.year, as_of_date.month, 1)

        revenue = self._get_revenue(month_start, as_of_date, area_id)
        cogs = self._get_cogs(month_start, as_of_date, area_id)

        current_cogs_pct = (cogs / revenue * 100) if revenue > 0 else Decimal('0.00')
        target = Decimal('32.0')  # Default target
        variance = current_cogs_pct - target

        # Breakdown by category (simplified - would need account subcategories)
        return COGSMetrics(
            current_cogs_pct=current_cogs_pct,
            target_cogs_pct=target,
            variance_from_target=variance,
            mtd_cogs_pct=current_cogs_pct,
            food_cogs_pct=Decimal('0.00'),  # TODO: Calculate by category
            beverage_cogs_pct=Decimal('0.00')
        )

    def _get_bank_balance_summary(self, area_id: Optional[int]) -> BankBalanceSummary:
        """Get bank balance summary"""
        query = self.db.query(
            func.count(BankAccount.id).label('count'),
            func.sum(BankAccount.current_balance).label('total')
        ).filter(BankAccount.status == 'active')

        if area_id:
            query = query.filter(BankAccount.area_id == area_id)

        result = query.first()
        total_cash = Decimal(str(result[1])) if result[1] else Decimal('0.00')
        account_count = result[0] or 0

        # Unreconciled transactions
        unrec_query = self.db.query(
            func.count(BankTransaction.id),
            func.min(BankTransaction.transaction_date)
        ).filter(BankTransaction.status != 'reconciled')

        if area_id:
            unrec_query = unrec_query.join(BankAccount).filter(BankAccount.area_id == area_id)

        unrec_result = unrec_query.first()
        unreconciled_count = unrec_result[0] or 0
        oldest_date = unrec_result[1]
        oldest_days = (date.today() - oldest_date).days if oldest_date else None

        return BankBalanceSummary(
            total_cash=total_cash,
            bank_account_count=account_count,
            last_reconciled=None,  # TODO
            unreconciled_count=unreconciled_count,
            oldest_unreconciled_days=oldest_days
        )

    def _get_cash_flow_forecast(self, area_id: Optional[int]) -> CashFlowForecast:
        """Get cash flow forecast"""
        # Current cash
        bank_summary = self._get_bank_balance_summary(area_id)
        current_cash = bank_summary.total_cash

        # Open AP
        ap_query = self.db.query(
            func.sum(VendorBill.total_amount - VendorBill.paid_amount)
        ).filter(VendorBill.status.in_([BillStatus.APPROVED, BillStatus.PARTIALLY_PAID]))

        if area_id:
            ap_query = ap_query.filter(VendorBill.area_id == area_id)

        open_ap = Decimal(str(ap_query.scalar() or 0))

        # Open AR (simplified - assuming no AR module yet)
        open_ar = Decimal('0.00')

        projected_cash = current_cash - open_ap + open_ar

        return CashFlowForecast(
            current_cash=current_cash,
            open_ap=open_ap,
            open_ar=open_ar,
            projected_cash=projected_cash,
            days_of_cash=None  # TODO: Calculate based on daily burn rate
        )

    def _get_ap_aging_summary(self, area_id: Optional[int]) -> APAgingSummary:
        """Get AP aging summary"""
        today = date.today()

        # Query open bills
        query = self.db.query(
            VendorBill.id,
            VendorBill.bill_date,
            VendorBill.total_amount,
            VendorBill.paid_amount
        ).filter(VendorBill.status != BillStatus.PAID)

        if area_id:
            query = query.filter(VendorBill.area_id == area_id)

        bills = query.all()

        # Calculate aging buckets
        bucket_0_30 = Decimal('0.00')
        bucket_31_60 = Decimal('0.00')
        bucket_61_90 = Decimal('0.00')
        bucket_over_90 = Decimal('0.00')
        total_outstanding = Decimal('0.00')
        total_age_days = 0
        vendors = set()

        for bill in bills:
            outstanding = bill.total_amount - (bill.paid_amount or 0)
            days_old = (today - bill.bill_date).days
            total_age_days += days_old
            total_outstanding += outstanding

            if days_old <= 30:
                bucket_0_30 += outstanding
            elif days_old <= 60:
                bucket_31_60 += outstanding
            elif days_old <= 90:
                bucket_61_90 += outstanding
            else:
                bucket_over_90 += outstanding

        avg_age = Decimal(str(total_age_days / len(bills))) if bills else Decimal('0.00')

        return APAgingSummary(
            total_outstanding=total_outstanding,
            bucket_0_30=bucket_0_30,
            bucket_31_60=bucket_31_60,
            bucket_61_90=bucket_61_90,
            bucket_over_90=bucket_over_90,
            average_age_days=avg_age,
            vendor_count=len(vendors)
        )

    def _get_accounting_health_metrics(self, area_id: Optional[int]) -> AccountingHealthMetrics:
        """Get accounting health metrics"""
        # Unposted journals
        unposted_query = self.db.query(func.count(JournalEntry.id)).filter(
            JournalEntry.status == JournalEntryStatus.DRAFT
        )

        if area_id:
            unposted_query = unposted_query.join(JournalEntryLine).filter(
                JournalEntryLine.area_id == area_id
            ).distinct()

        unposted = unposted_query.scalar() or 0

        # Pending reconciliations - bank accounts with unreconciled transactions
        pending_recs_query = self.db.query(
            func.count(func.distinct(BankAccount.id))
        ).join(
            BankTransaction, BankTransaction.bank_account_id == BankAccount.id
        ).filter(
            BankTransaction.status != 'reconciled'
        )

        if area_id:
            pending_recs_query = pending_recs_query.filter(BankAccount.area_id == area_id)

        pending_recs = pending_recs_query.scalar() or 0

        # Missing DSS mappings - daily sales without journal entry
        missing_dss_query = self.db.query(
            func.count(DailySalesSummary.id)
        ).filter(
            DailySalesSummary.journal_entry_id.is_(None),
            DailySalesSummary.status == 'draft'
        )

        if area_id:
            missing_dss_query = missing_dss_query.filter(DailySalesSummary.area_id == area_id)

        missing_dss = missing_dss_query.scalar() or 0

        # GL outliers - accounts with balances that seem unusual (simplified check)
        # Count accounts with very large unexpected balances
        # Use subquery approach since we need to filter on aggregated values
        balance_query = self.db.query(
            Account.id,
            func.sum(
                func.coalesce(JournalEntryLine.debit_amount, 0) -
                func.coalesce(JournalEntryLine.credit_amount, 0)
            ).label('balance')
        ).join(
            JournalEntryLine, JournalEntryLine.account_id == Account.id
        )

        if area_id:
            balance_query = balance_query.filter(JournalEntryLine.area_id == area_id)

        balance_query = balance_query.group_by(Account.id).subquery()

        gl_outliers = self.db.query(
            func.count(balance_query.c.id)
        ).filter(
            func.abs(balance_query.c.balance) > 1000000  # Balances over $1M
        ).scalar() or 0

        return AccountingHealthMetrics(
            unposted_journals=unposted,
            pending_reconciliations=pending_recs,
            missing_dss_mappings=missing_dss,
            gl_outliers=gl_outliers,
            last_inventory_date=None,
            days_since_inventory=None
        )

    def _get_top_expense_categories(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int],
        limit: int = 5
    ) -> List[TopExpenseCategory]:
        """Get top expense categories"""
        # Query expense accounts
        query = self.db.query(
            Account.account_name.label('category'),
            func.sum(
                func.coalesce(JournalEntryLine.debit_amount, 0) -
                func.coalesce(JournalEntryLine.credit_amount, 0)
            ).label('amount')
        ).join(
            JournalEntryLine, Account.id == JournalEntryLine.account_id
        ).join(
            JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
        ).filter(
            Account.account_type == AccountType.EXPENSE,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        if area_id:
            query = query.filter(JournalEntryLine.area_id == area_id)

        query = query.group_by(Account.account_name).order_by(
            func.sum(
                func.coalesce(JournalEntryLine.debit_amount, 0) -
                func.coalesce(JournalEntryLine.credit_amount, 0)
            ).desc()
        ).limit(limit)

        results = query.all()

        revenue = self._get_revenue(start_date, end_date, area_id)

        categories = []
        for idx, (category, amount) in enumerate(results, 1):
            amount_decimal = Decimal(str(amount)) if amount else Decimal('0.00')
            pct_of_revenue = (amount_decimal / revenue * 100) if revenue > 0 and amount_decimal > 0 else Decimal('0.00')
            categories.append(TopExpenseCategory(
                category_name=category,
                amount=amount_decimal,
                pct_of_revenue=pct_of_revenue,
                pct_change_mom=None,  # TODO: Calculate vs prior month
                rank=idx
            ))

        return categories

    def _get_revenue_by_location(self, start_date: date, end_date: date) -> List[LocationRevenue]:
        """Get revenue by location"""
        query = self.db.query(
            Area.id,
            Area.name,
            func.sum(JournalEntryLine.credit_amount).label('revenue')
        ).join(
            JournalEntryLine, Area.id == JournalEntryLine.area_id
        ).join(
            JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id
        ).join(
            Account, JournalEntryLine.account_id == Account.id
        ).filter(
            Account.account_type == AccountType.REVENUE,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        ).group_by(Area.id, Area.name).all()

        total_revenue = sum(Decimal(str(r[2])) for r in query)

        locations = []
        for area_id, area_name, revenue in query:
            revenue_dec = Decimal(str(revenue))
            pct_of_total = (revenue_dec / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')

            locations.append(LocationRevenue(
                area_id=area_id,
                area_name=area_name,
                revenue=revenue_dec,
                pct_of_total=pct_of_total,
                vs_prior_month=None  # TODO
            ))

        return locations

    def _get_revenue_by_category(self, start_date: date, end_date: date, area_id: Optional[int]) -> List:
        """Get revenue by category (net of discounts)"""
        from accounting.schemas.general_dashboard import RevenueCategory
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Getting revenue by category: start={start_date}, end={end_date}, area_id={area_id}")

        # Get revenue credits (gross) by account
        query = self.db.query(
            Account.account_name,
            func.sum(JournalEntryLine.credit_amount).label('credits'),
            func.sum(JournalEntryLine.debit_amount).label('debits')
        ).join(
            JournalEntryLine, Account.id == JournalEntryLine.account_id
        ).join(
            JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
        ).filter(
            Account.account_type == AccountType.REVENUE,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        if area_id:
            query = query.filter(JournalEntryLine.area_id == area_id)

        query = query.group_by(Account.account_name)
        results = query.all()

        logger.info(f"Query returned {len(results)} results")

        # Calculate net amounts (credits - debits) and total
        category_amounts = []
        total_revenue = Decimal('0.00')

        for account_name, credits, debits in results:
            credits_dec = Decimal(str(credits)) if credits else Decimal('0.00')
            debits_dec = Decimal(str(debits)) if debits else Decimal('0.00')
            net_amount = credits_dec - debits_dec

            if net_amount > 0:  # Only include positive net revenue (exclude contra-revenue with net negative)
                category_amounts.append((account_name, net_amount))
                total_revenue += net_amount

        # Sort by amount descending
        category_amounts.sort(key=lambda x: x[1], reverse=True)

        # Build response
        categories = []
        for category_name, amount in category_amounts:
            pct_of_total = (amount / total_revenue * 100) if total_revenue > 0 else Decimal('0.00')
            categories.append(RevenueCategory(
                category_name=category_name,
                amount=amount,
                pct_of_total=pct_of_total
            ))

        logger.info(f"Returning {len(categories)} revenue categories, total revenue: {total_revenue}")
        return categories

    def _determine_trend(self, values: List[Decimal]) -> str:
        """Determine if trend is up, down, or flat"""
        if len(values) < 2:
            return "flat"

        # Simple trend: compare first half to second half
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / mid
        second_half_avg = sum(values[mid:]) / (len(values) - mid)

        if second_half_avg > first_half_avg * Decimal('1.05'):
            return "up"
        elif second_half_avg < first_half_avg * Decimal('0.95'):
            return "down"
        else:
            return "flat"
