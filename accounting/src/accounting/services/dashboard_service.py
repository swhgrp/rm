"""Service layer for Banking Dashboard calculations and aggregations"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import Optional, List, Tuple
from datetime import date, datetime, timedelta
from decimal import Decimal

from accounting.models.bank_account import BankAccount, BankTransaction
from accounting.models.account import Account
from accounting.models.area import Area
from accounting.models.banking_dashboard import (
    DailyCashPosition,
    CashFlowTransaction,
    BankingAlert,
    ReconciliationHealthMetric,
    LocationCashFlowSummary,
    CashFlowCategory,
    AlertSeverity,
    AlertType
)
from accounting.schemas.banking_dashboard import (
    DashboardKPI,
    LocationSummary,
    DashboardSummaryResponse,
    CashFlowSummary,
    CashFlowTrendPoint,
    CashFlowTrendResponse,
    ReconciliationTrendPoint,
    ReconciliationTrendResponse
)


class DashboardService:
    """Service for generating dashboard metrics and summaries"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Dashboard Summary
    # ========================================================================

    def get_dashboard_summary(
        self,
        area_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> DashboardSummaryResponse:
        """
        Generate complete dashboard summary.

        Args:
            area_id: Filter by specific location (None = all locations)
            start_date: Start date for metrics (default: 30 days ago)
            end_date: End date for metrics (default: today)

        Returns:
            Complete dashboard summary with KPIs, locations, cash flow, and alerts
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get top-level KPIs
        total_cash = self._calculate_total_cash_kpi(area_id)
        gl_variance = self._calculate_gl_variance_kpi(area_id, start_date, end_date)
        recon_rate = self._calculate_reconciliation_rate_kpi(area_id, start_date, end_date)
        unrecon_txns = self._calculate_unreconciled_transactions_kpi(area_id, start_date, end_date)

        # Get location breakdown
        locations = self._get_location_summaries(start_date, end_date)

        # Get cash flow summary
        cash_flow = self._calculate_cash_flow_summary(area_id, start_date, end_date)

        # Get active alerts summary
        critical, warning, info = self._count_active_alerts(area_id)

        # Get reconciliation health metrics
        health_metrics = self._get_latest_health_metrics(area_id)

        return DashboardSummaryResponse(
            total_cash_balance=total_cash,
            gl_variance=gl_variance,
            reconciliation_rate=recon_rate,
            unreconciled_transactions=unrecon_txns,
            locations=locations,
            cash_flow=cash_flow,
            critical_alerts=critical,
            warning_alerts=warning,
            info_alerts=info,
            avg_days_to_reconcile=health_metrics.get('avg_days_to_reconcile'),
            transactions_over_30_days=health_metrics.get('transactions_over_30_days', 0),
            auto_match_rate=health_metrics.get('auto_match_rate')
        )

    def _calculate_total_cash_kpi(self, area_id: Optional[int] = None) -> DashboardKPI:
        """Calculate total cash balance across all bank accounts"""
        query = self.db.query(func.sum(BankAccount.current_balance))

        if area_id:
            query = query.filter(BankAccount.area_id == area_id)

        total = query.scalar() or Decimal("0")

        # Calculate change vs yesterday
        yesterday = date.today() - timedelta(days=1)
        yesterday_total = self._get_historical_cash_balance(area_id, yesterday)
        change = total - yesterday_total if yesterday_total else None
        change_percent = (change / yesterday_total * 100) if yesterday_total and yesterday_total != 0 else None

        return DashboardKPI(
            label="Total Cash Balance",
            value=total,
            change=change,
            change_percent=change_percent,
            trend="up" if change and change > 0 else "down" if change and change < 0 else "neutral"
        )

    def _calculate_gl_variance_kpi(
        self,
        area_id: Optional[int] = None,
        start_date: date = None,
        end_date: date = None
    ) -> DashboardKPI:
        """Calculate GL variance as the total amount of unreconciled bank transactions.

        This represents bank activity not yet recorded in the GL.
        As transactions are reconciled, this approaches $0.
        """
        query = self.db.query(
            func.coalesce(func.sum(BankTransaction.amount), 0)
        ).join(BankAccount).filter(
            BankTransaction.status == 'unreconciled'
        )

        if area_id:
            query = query.filter(BankAccount.area_id == area_id)
        if start_date:
            query = query.filter(BankTransaction.transaction_date >= start_date)
        if end_date:
            query = query.filter(BankTransaction.transaction_date <= end_date)

        variance = query.scalar() or Decimal("0")

        return DashboardKPI(
            label="GL vs Bank Variance",
            value=variance,
            trend="neutral" if abs(variance) < 1000 else "down"  # Variance should be close to zero
        )

    def _calculate_reconciliation_rate_kpi(
        self,
        area_id: Optional[int] = None,
        start_date: date = None,
        end_date: date = None
    ) -> DashboardKPI:
        """Calculate reconciliation rate percentage"""
        query = self.db.query(BankTransaction)

        if area_id:
            query = query.join(BankAccount).filter(BankAccount.area_id == area_id)

        if start_date:
            query = query.filter(BankTransaction.transaction_date >= start_date)
        if end_date:
            query = query.filter(BankTransaction.transaction_date <= end_date)

        total = query.count()
        reconciled = query.filter(BankTransaction.status == 'reconciled').count()

        rate = round(Decimal(reconciled / total * 100), 2) if total > 0 else Decimal("0.00")

        # Compare to last period
        if start_date and end_date:
            period_length = (end_date - start_date).days
            prev_start = start_date - timedelta(days=period_length)
            prev_end = start_date - timedelta(days=1)

            prev_query = self.db.query(BankTransaction)
            if area_id:
                prev_query = prev_query.join(BankAccount).filter(BankAccount.area_id == area_id)
            prev_query = prev_query.filter(
                BankTransaction.transaction_date >= prev_start,
                BankTransaction.transaction_date <= prev_end
            )

            prev_total = prev_query.count()
            prev_reconciled = prev_query.filter(BankTransaction.status == 'reconciled').count()
            prev_rate = round(Decimal(prev_reconciled / prev_total * 100), 2) if prev_total > 0 else Decimal("0.00")

            change = round(rate - prev_rate, 2)
        else:
            change = None

        return DashboardKPI(
            label="Reconciliation Rate",
            value=rate,
            change=change,
            trend="up" if change and change > 0 else "down" if change and change < 0 else "neutral"
        )

    def _calculate_unreconciled_transactions_kpi(
        self,
        area_id: Optional[int] = None,
        start_date: date = None,
        end_date: date = None
    ) -> DashboardKPI:
        """Calculate number of unreconciled transactions"""
        query = self.db.query(func.count(BankTransaction.id))

        if area_id:
            query = query.join(BankAccount).filter(BankAccount.area_id == area_id)

        if start_date:
            query = query.filter(BankTransaction.transaction_date >= start_date)
        if end_date:
            query = query.filter(BankTransaction.transaction_date <= end_date)

        query = query.filter(BankTransaction.status == 'unreconciled')

        count = query.scalar() or 0

        return DashboardKPI(
            label="Unreconciled Transactions",
            value=Decimal(count),
            trend="down" if count < 100 else "up"  # Fewer unreconciled is better
        )

    def _get_location_summaries(self, start_date: date, end_date: date) -> List[LocationSummary]:
        """Get summary for each location"""
        areas = self.db.query(Area).all()
        summaries = []

        for area in areas:
            # Get bank accounts for this area
            accounts = self.db.query(BankAccount).filter(BankAccount.area_id == area.id).all()
            total_balance = sum(acc.current_balance or Decimal("0") for acc in accounts)

            # Get transaction counts
            txn_query = self.db.query(BankTransaction).join(BankAccount)
            txn_query = txn_query.filter(BankAccount.area_id == area.id)
            txn_query = txn_query.filter(
                BankTransaction.transaction_date >= start_date,
                BankTransaction.transaction_date <= end_date
            )

            reconciled = txn_query.filter(BankTransaction.status == 'reconciled').count()
            unreconciled = txn_query.filter(BankTransaction.status == 'unreconciled').count()
            total_txns = reconciled + unreconciled

            recon_rate = round(Decimal(reconciled / total_txns * 100), 2) if total_txns > 0 else Decimal("0.00")

            # Get active alerts
            active_alerts = self.db.query(func.count(BankingAlert.id)).filter(
                BankingAlert.area_id == area.id,
                BankingAlert.is_active == True
            ).scalar() or 0

            # GL variance = sum of unreconciled transaction amounts for this location (date-filtered)
            account_ids = [acc.id for acc in accounts]
            variance = Decimal("0")
            if account_ids:
                var_query = self.db.query(
                    func.coalesce(func.sum(BankTransaction.amount), 0)
                ).filter(
                    BankTransaction.bank_account_id.in_(account_ids),
                    BankTransaction.status == 'unreconciled',
                    BankTransaction.transaction_date >= start_date,
                    BankTransaction.transaction_date <= end_date
                )
                variance = var_query.scalar() or Decimal("0")

            summaries.append(LocationSummary(
                area_id=area.id,
                area_name=area.name,
                total_balance=total_balance,
                reconciled_transactions=reconciled,
                unreconciled_transactions=unreconciled,
                reconciliation_rate=recon_rate,
                active_alerts=active_alerts,
                gl_variance=variance
            ))

        return summaries

    def _calculate_cash_flow_summary(
        self,
        area_id: Optional[int] = None,
        start_date: date = None,
        end_date: date = None
    ) -> CashFlowSummary:
        """Calculate cash flow summary for the period"""
        query = self.db.query(
            CashFlowTransaction.category,
            func.sum(CashFlowTransaction.amount).label('total')
        )

        if area_id:
            query = query.filter(CashFlowTransaction.area_id == area_id)

        if start_date:
            query = query.filter(CashFlowTransaction.transaction_date >= start_date)
        if end_date:
            query = query.filter(CashFlowTransaction.transaction_date <= end_date)

        results = query.group_by(CashFlowTransaction.category).all()

        # Initialize summary
        summary = CashFlowSummary()

        # Aggregate by category
        for category, total in results:
            if category == CashFlowCategory.OPERATING_INFLOW:
                summary.operating_inflows = total or Decimal("0")
            elif category == CashFlowCategory.OPERATING_OUTFLOW:
                summary.operating_outflows = abs(total) or Decimal("0")
            elif category == CashFlowCategory.INVESTING_INFLOW:
                summary.investing_inflows = total or Decimal("0")
            elif category == CashFlowCategory.INVESTING_OUTFLOW:
                summary.investing_outflows = abs(total) or Decimal("0")
            elif category == CashFlowCategory.FINANCING_INFLOW:
                summary.financing_inflows = total or Decimal("0")
            elif category == CashFlowCategory.FINANCING_OUTFLOW:
                summary.financing_outflows = abs(total) or Decimal("0")

        # Calculate net amounts
        summary.net_operating = summary.operating_inflows - summary.operating_outflows
        summary.net_investing = summary.investing_inflows - summary.investing_outflows
        summary.net_financing = summary.financing_inflows - summary.financing_outflows
        summary.net_change = summary.net_operating + summary.net_investing + summary.net_financing

        return summary

    def _count_active_alerts(self, area_id: Optional[int] = None) -> Tuple[int, int, int]:
        """Count active alerts by severity"""
        query = self.db.query(
            BankingAlert.severity,
            func.count(BankingAlert.id).label('count')
        ).filter(BankingAlert.is_active == True)

        if area_id:
            query = query.filter(BankingAlert.area_id == area_id)

        results = query.group_by(BankingAlert.severity).all()

        critical = 0
        warning = 0
        info = 0

        for severity, count in results:
            if severity == AlertSeverity.CRITICAL:
                critical = count
            elif severity == AlertSeverity.WARNING:
                warning = count
            elif severity == AlertSeverity.INFO:
                info = count

        return critical, warning, info

    def _get_latest_health_metrics(self, area_id: Optional[int] = None) -> dict:
        """Get latest reconciliation health metrics"""
        query = self.db.query(ReconciliationHealthMetric)

        if area_id:
            query = query.filter(ReconciliationHealthMetric.area_id == area_id)
        else:
            # For all locations, get latest metrics and aggregate
            query = query.filter(ReconciliationHealthMetric.area_id == None)

        query = query.order_by(desc(ReconciliationHealthMetric.metric_date))
        latest = query.first()

        if not latest:
            return {}

        return {
            'avg_days_to_reconcile': latest.avg_days_to_reconcile,
            'transactions_over_30_days': latest.transactions_over_30_days,
            'auto_match_rate': latest.auto_match_rate
        }

    def _get_historical_cash_balance(self, area_id: Optional[int], target_date: date) -> Decimal:
        """Get historical cash balance for a specific date"""
        query = self.db.query(func.sum(DailyCashPosition.closing_balance)).filter(
            DailyCashPosition.position_date == target_date
        )

        if area_id:
            query = query.filter(DailyCashPosition.area_id == area_id)

        return query.scalar() or Decimal("0")

    # ========================================================================
    # Cash Flow Trends
    # ========================================================================

    def get_cash_flow_trend(
        self,
        area_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> CashFlowTrendResponse:
        """Get cash flow trend over time"""
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get daily cash positions
        query = self.db.query(DailyCashPosition).filter(
            DailyCashPosition.position_date >= start_date,
            DailyCashPosition.position_date <= end_date
        )

        if area_id:
            query = query.filter(DailyCashPosition.area_id == area_id)

        query = query.order_by(DailyCashPosition.position_date)
        positions = query.all()

        # Aggregate by date if multiple accounts
        daily_data = {}
        for pos in positions:
            date_key = pos.position_date
            if date_key not in daily_data:
                daily_data[date_key] = {
                    'opening': Decimal("0"),
                    'closing': Decimal("0"),
                    'inflows': Decimal("0"),
                    'outflows': Decimal("0")
                }

            daily_data[date_key]['opening'] += pos.opening_balance
            daily_data[date_key]['closing'] += pos.closing_balance
            daily_data[date_key]['inflows'] += pos.total_inflows
            daily_data[date_key]['outflows'] += pos.total_outflows

        # Convert to trend points
        data_points = []
        for dt, data in sorted(daily_data.items()):
            data_points.append(CashFlowTrendPoint(
                date=dt,
                opening_balance=data['opening'],
                closing_balance=data['closing'],
                net_change=data['closing'] - data['opening'],
                inflows=data['inflows'],
                outflows=data['outflows']
            ))

        # Get area name if specified
        area_name = None
        if area_id:
            area = self.db.query(Area).filter(Area.id == area_id).first()
            area_name = area.name if area else None

        return CashFlowTrendResponse(
            area_id=area_id,
            area_name=area_name,
            start_date=start_date,
            end_date=end_date,
            data_points=data_points
        )

    # ========================================================================
    # Reconciliation Trends
    # ========================================================================

    def get_reconciliation_trend(
        self,
        area_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> ReconciliationTrendResponse:
        """Get reconciliation health trend over time"""
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get health metrics
        query = self.db.query(ReconciliationHealthMetric).filter(
            ReconciliationHealthMetric.metric_date >= start_date,
            ReconciliationHealthMetric.metric_date <= end_date
        )

        if area_id:
            query = query.filter(ReconciliationHealthMetric.area_id == area_id)

        query = query.order_by(ReconciliationHealthMetric.metric_date)
        metrics = query.all()

        # Convert to trend points
        data_points = []
        for metric in metrics:
            data_points.append(ReconciliationTrendPoint(
                date=metric.metric_date,
                total_transactions=metric.total_transactions,
                reconciled_transactions=metric.reconciled_transactions,
                reconciliation_rate=metric.reconciliation_rate or Decimal("0"),
                avg_days_to_reconcile=metric.avg_days_to_reconcile
            ))

        # Get area name if specified
        area_name = None
        if area_id:
            area = self.db.query(Area).filter(Area.id == area_id).first()
            area_name = area.name if area else None

        return ReconciliationTrendResponse(
            area_id=area_id,
            area_name=area_name,
            start_date=start_date,
            end_date=end_date,
            data_points=data_points
        )
