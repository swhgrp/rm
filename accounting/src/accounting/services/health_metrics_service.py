"""Service for calculating and storing reconciliation health metrics"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Optional
from datetime import date, datetime, timedelta
from decimal import Decimal

from accounting.models.bank_account import BankAccount, BankTransaction
from accounting.models.account import Account
from accounting.models.account_balance import AccountBalance
from accounting.models.banking_dashboard import ReconciliationHealthMetric
from accounting.schemas.banking_dashboard import ReconciliationHealthMetricCreate


class HealthMetricsService:
    """Service for calculating reconciliation health metrics"""

    def __init__(self, db: Session):
        self.db = db

    def calculate_daily_metrics(
        self,
        target_date: date,
        area_id: Optional[int] = None
    ) -> ReconciliationHealthMetric:
        """
        Calculate and store daily reconciliation health metrics.

        Args:
            target_date: Date to calculate metrics for
            area_id: Specific location (None = aggregate all locations)

        Returns:
            ReconciliationHealthMetric object
        """
        # Base transaction query
        txn_query = self.db.query(BankTransaction).join(BankAccount)

        if area_id:
            txn_query = txn_query.filter(BankAccount.area_id == area_id)

        # Filter to transactions up to target date
        txn_query = txn_query.filter(BankTransaction.transaction_date <= target_date)

        # Count total transactions
        total_transactions = txn_query.count()

        # Count reconciled vs unreconciled
        reconciled_transactions = txn_query.filter(BankTransaction.status == 'reconciled').count()
        unreconciled_transactions = total_transactions - reconciled_transactions

        # Calculate reconciliation rate
        reconciliation_rate = round(Decimal(
            reconciled_transactions / total_transactions * 100
        ), 2) if total_transactions > 0 else Decimal("0.00")

        # Calculate average days to reconcile
        avg_days = self._calculate_avg_days_to_reconcile(txn_query, target_date)

        # Count transactions by age
        over_30 = self._count_transactions_over_days(txn_query, target_date, 30)
        over_60 = self._count_transactions_over_days(txn_query, target_date, 60)
        over_90 = self._count_transactions_over_days(txn_query, target_date, 90)

        # Calculate auto-match statistics
        auto_matched, manual_matched = self._calculate_match_statistics(txn_query)
        total_matched = auto_matched + manual_matched
        auto_match_rate = Decimal(
            auto_matched / total_matched * 100
        ) if total_matched > 0 else Decimal("0")

        # Calculate GL variance metrics
        gl_variance_count, total_variance, avg_variance = self._calculate_gl_variances(area_id)

        # Count active alerts
        from accounting.models.banking_dashboard import BankingAlert, AlertSeverity

        alert_query = self.db.query(BankingAlert).filter(BankingAlert.is_active == True)
        if area_id:
            alert_query = alert_query.filter(BankingAlert.area_id == area_id)

        critical_alerts = alert_query.filter(BankingAlert.severity == AlertSeverity.CRITICAL).count()
        warning_alerts = alert_query.filter(BankingAlert.severity == AlertSeverity.WARNING).count()

        # Create or update metric
        existing = self.db.query(ReconciliationHealthMetric).filter(
            ReconciliationHealthMetric.metric_date == target_date,
            ReconciliationHealthMetric.area_id == area_id
        ).first()

        if existing:
            # Update existing metric
            existing.total_transactions = total_transactions
            existing.reconciled_transactions = reconciled_transactions
            existing.unreconciled_transactions = unreconciled_transactions
            existing.reconciliation_rate = reconciliation_rate
            existing.avg_days_to_reconcile = avg_days
            existing.transactions_over_30_days = over_30
            existing.transactions_over_60_days = over_60
            existing.transactions_over_90_days = over_90
            existing.auto_matched_count = auto_matched
            existing.manual_matched_count = manual_matched
            existing.auto_match_rate = auto_match_rate
            existing.gl_variance_count = gl_variance_count
            existing.total_gl_variance = total_variance
            existing.avg_gl_variance = avg_variance
            existing.critical_alerts = critical_alerts
            existing.warning_alerts = warning_alerts
            existing.updated_at = func.now()

            metric = existing
        else:
            # Create new metric
            metric = ReconciliationHealthMetric(
                metric_date=target_date,
                area_id=area_id,
                total_transactions=total_transactions,
                reconciled_transactions=reconciled_transactions,
                unreconciled_transactions=unreconciled_transactions,
                reconciliation_rate=reconciliation_rate,
                avg_days_to_reconcile=avg_days,
                transactions_over_30_days=over_30,
                transactions_over_60_days=over_60,
                transactions_over_90_days=over_90,
                auto_matched_count=auto_matched,
                manual_matched_count=manual_matched,
                auto_match_rate=auto_match_rate,
                gl_variance_count=gl_variance_count,
                total_gl_variance=total_variance,
                avg_gl_variance=avg_variance,
                critical_alerts=critical_alerts,
                warning_alerts=warning_alerts
            )
            self.db.add(metric)

        self.db.commit()
        self.db.refresh(metric)

        return metric

    def _calculate_avg_days_to_reconcile(self, txn_query, target_date: date) -> Optional[Decimal]:
        """Calculate average days between transaction date and reconciliation date"""
        # Get reconciled transactions with reconciliation dates
        reconciled = txn_query.filter(
            BankTransaction.status == 'reconciled',
            BankTransaction.reconciled_at != None
        ).all()

        if not reconciled:
            return None

        total_days = 0
        count = 0

        for txn in reconciled:
            # Calculate days between transaction date and reconciliation date
            days = (txn.reconciled_at.date() - txn.transaction_date).days
            if days >= 0:  # Only count if reconciled after transaction date
                total_days += days
                count += 1

        return Decimal(total_days / count) if count > 0 else None

    def _count_transactions_over_days(self, txn_query, target_date: date, days: int) -> int:
        """Count unreconciled transactions older than specified days"""
        cutoff_date = target_date - timedelta(days=days)

        return txn_query.filter(
            BankTransaction.status == 'unreconciled',
            BankTransaction.transaction_date <= cutoff_date
        ).count()

    def _calculate_match_statistics(self, txn_query) -> tuple[int, int]:
        """Calculate auto-matched vs manual-matched transaction counts"""
        # Auto-matched transactions have suggested_account_id set and status = reconciled
        auto_matched = txn_query.filter(
            BankTransaction.status == 'reconciled',
            BankTransaction.suggested_account_id != None
        ).count()

        # Manual-matched transactions are reconciled but don't have suggested_account_id
        manual_matched = txn_query.filter(
            BankTransaction.status == 'reconciled',
            BankTransaction.suggested_account_id == None
        ).count()

        return auto_matched, manual_matched

    def _calculate_gl_variances(self, area_id: Optional[int]) -> tuple[int, Optional[Decimal], Optional[Decimal]]:
        """Calculate GL variance metrics across bank accounts"""
        # Get all bank accounts
        account_query = self.db.query(BankAccount)

        if area_id:
            account_query = account_query.filter(BankAccount.area_id == area_id)

        bank_accounts = account_query.all()

        variances = []

        for bank_acc in bank_accounts:
            # Get bank balance
            bank_balance = bank_acc.current_balance or Decimal("0")

            # Get GL balance for corresponding GL account
            if bank_acc.gl_account_id:
                gl_balance_record = self.db.query(AccountBalance).filter(
                    AccountBalance.account_id == bank_acc.gl_account_id,
                    AccountBalance.location_id == bank_acc.area_id
                ).first()

                gl_balance = gl_balance_record.net_balance if gl_balance_record else Decimal("0")

                # Calculate variance
                variance = abs(bank_balance - gl_balance)

                # Only count significant variances (> $100)
                if variance > 100:
                    variances.append(variance)

        variance_count = len(variances)
        total_variance = sum(variances) if variances else None
        avg_variance = Decimal(sum(variances) / len(variances)) if variances else None

        return variance_count, total_variance, avg_variance

    def calculate_metrics_for_date_range(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int] = None
    ) -> list[ReconciliationHealthMetric]:
        """
        Calculate daily metrics for a range of dates.

        Args:
            start_date: Start date
            end_date: End date
            area_id: Specific location (None = aggregate all locations)

        Returns:
            List of ReconciliationHealthMetric objects
        """
        metrics = []
        current_date = start_date

        while current_date <= end_date:
            metric = self.calculate_daily_metrics(current_date, area_id)
            metrics.append(metric)
            current_date += timedelta(days=1)

        return metrics
