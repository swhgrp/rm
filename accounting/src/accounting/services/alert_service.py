"""Service for generating and managing banking alerts"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Optional, List
from datetime import date, datetime, timedelta
from decimal import Decimal

from accounting.models.bank_account import BankAccount, BankTransaction
from accounting.models.account import Account
from accounting.models.account_balance import AccountBalance
from accounting.models.banking_dashboard import BankingAlert, AlertSeverity, AlertType
from accounting.schemas.banking_dashboard import BankingAlertCreate


class AlertService:
    """Service for generating and managing banking alerts"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Alert Generation
    # ========================================================================

    def generate_all_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """
        Generate all types of alerts for all locations or specific location.

        Returns list of newly created alerts.
        """
        alerts = []

        # Run all alert checks
        alerts.extend(self.check_gl_variance_alerts(area_id))
        alerts.extend(self.check_low_balance_alerts(area_id))
        alerts.extend(self.check_old_unreconciled_alerts(area_id))
        alerts.extend(self.check_negative_balance_alerts(area_id))
        alerts.extend(self.check_large_transaction_alerts(area_id))
        alerts.extend(self.check_reconciliation_stuck_alerts(area_id))

        return alerts

    def check_gl_variance_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for GL vs Bank variance alerts"""
        alerts = []

        # Get all bank accounts
        account_query = self.db.query(BankAccount)
        if area_id:
            account_query = account_query.filter(BankAccount.area_id == area_id)

        bank_accounts = account_query.all()

        for bank_acc in bank_accounts:
            # Get bank balance
            bank_balance = bank_acc.current_balance or Decimal("0")

            # Get GL balance for corresponding GL account
            if not bank_acc.gl_account_id:
                continue

            gl_balance_record = self.db.query(AccountBalance).filter(
                AccountBalance.account_id == bank_acc.gl_account_id,
                AccountBalance.location_id == bank_acc.area_id
            ).first()

            gl_balance = gl_balance_record.net_balance if gl_balance_record else Decimal("0")

            # Calculate variance
            variance = bank_balance - gl_balance

            # Alert threshold: $1,000
            if abs(variance) > 1000:
                # Check if alert already exists
                existing = self._find_existing_alert(
                    alert_type=AlertType.GL_VARIANCE,
                    area_id=bank_acc.area_id,
                    bank_account_id=bank_acc.id
                )

                if not existing:
                    severity = AlertSeverity.CRITICAL if abs(variance) > 5000 else AlertSeverity.WARNING

                    alert = BankingAlert(
                        alert_type=AlertType.GL_VARIANCE,
                        severity=severity,
                        area_id=bank_acc.area_id,
                        bank_account_id=bank_acc.id,
                        title=f"GL Variance Detected: {bank_acc.account_name}",
                        message=f"Bank balance (${bank_balance:,.2f}) differs from GL balance (${gl_balance:,.2f}) by ${abs(variance):,.2f}. Please review and reconcile.",
                        amount=abs(variance),
                        is_active=True
                    )

                    self.db.add(alert)
                    alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    def check_low_balance_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for low balance alerts"""
        alerts = []

        # Get all bank accounts
        account_query = self.db.query(BankAccount)
        if area_id:
            account_query = account_query.filter(BankAccount.area_id == area_id)

        bank_accounts = account_query.all()

        for bank_acc in bank_accounts:
            balance = bank_acc.current_balance or Decimal("0")

            # Alert if balance < $5,000
            if balance < 5000:
                # Check if alert already exists
                existing = self._find_existing_alert(
                    alert_type=AlertType.LOW_BALANCE,
                    area_id=bank_acc.area_id,
                    bank_account_id=bank_acc.id
                )

                if not existing:
                    severity = AlertSeverity.CRITICAL if balance < 1000 else AlertSeverity.WARNING

                    alert = BankingAlert(
                        alert_type=AlertType.LOW_BALANCE,
                        severity=severity,
                        area_id=bank_acc.area_id,
                        bank_account_id=bank_acc.id,
                        title=f"Low Balance Warning: {bank_acc.account_name}",
                        message=f"Account balance is ${balance:,.2f}, which is below the recommended minimum.",
                        amount=balance,
                        is_active=True
                    )

                    self.db.add(alert)
                    alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    def check_old_unreconciled_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for old unreconciled transactions"""
        alerts = []

        # Find unreconciled transactions older than 60 days
        cutoff_date = date.today() - timedelta(days=60)

        txn_query = self.db.query(BankTransaction).join(BankAccount)
        txn_query = txn_query.filter(
            BankTransaction.status == 'unreconciled',
            BankTransaction.transaction_date <= cutoff_date
        )

        if area_id:
            txn_query = txn_query.filter(BankAccount.area_id == area_id)

        old_transactions = txn_query.all()

        # Group by area
        area_counts = {}
        for txn in old_transactions:
            area = txn.bank_account.area_id
            if area not in area_counts:
                area_counts[area] = {'count': 0, 'area_obj': txn.bank_account.area}
            area_counts[area]['count'] += 1

        # Create alerts for each area with old transactions
        for area, data in area_counts.items():
            count = data['count']

            # Check if alert already exists
            existing = self._find_existing_alert(
                alert_type=AlertType.UNRECONCILED_OLD,
                area_id=area
            )

            if not existing:
                severity = AlertSeverity.CRITICAL if count > 50 else AlertSeverity.WARNING

                alert = BankingAlert(
                    alert_type=AlertType.UNRECONCILED_OLD,
                    severity=severity,
                    area_id=area,
                    title=f"{count} Old Unreconciled Transactions",
                    message=f"There are {count} unreconciled transactions older than 60 days at {data['area_obj'].name}. Please review and reconcile.",
                    is_active=True
                )

                self.db.add(alert)
                alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    def check_negative_balance_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for negative balance alerts"""
        alerts = []

        # Get all bank accounts
        account_query = self.db.query(BankAccount)
        if area_id:
            account_query = account_query.filter(BankAccount.area_id == area_id)

        bank_accounts = account_query.all()

        for bank_acc in bank_accounts:
            balance = bank_acc.current_balance or Decimal("0")

            # Alert if balance is negative
            if balance < 0:
                # Check if alert already exists
                existing = self._find_existing_alert(
                    alert_type=AlertType.NEGATIVE_BALANCE,
                    area_id=bank_acc.area_id,
                    bank_account_id=bank_acc.id
                )

                if not existing:
                    alert = BankingAlert(
                        alert_type=AlertType.NEGATIVE_BALANCE,
                        severity=AlertSeverity.CRITICAL,
                        area_id=bank_acc.area_id,
                        bank_account_id=bank_acc.id,
                        title=f"Negative Balance: {bank_acc.account_name}",
                        message=f"Account has a negative balance of ${balance:,.2f}. Immediate attention required.",
                        amount=abs(balance),
                        is_active=True
                    )

                    self.db.add(alert)
                    alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    def check_large_transaction_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for unusually large transactions"""
        alerts = []

        # Find transactions > $10,000 from last 7 days
        cutoff_date = date.today() - timedelta(days=7)

        txn_query = self.db.query(BankTransaction).join(BankAccount)
        txn_query = txn_query.filter(
            BankTransaction.transaction_date >= cutoff_date,
            or_(
                BankTransaction.amount > 10000,
                BankTransaction.amount < -10000
            )
        )

        if area_id:
            txn_query = txn_query.filter(BankAccount.area_id == area_id)

        large_transactions = txn_query.all()

        for txn in large_transactions:
            # Check if alert already exists for this transaction
            existing = self._find_existing_alert(
                alert_type=AlertType.LARGE_TRANSACTION,
                bank_transaction_id=txn.id
            )

            if not existing:
                alert = BankingAlert(
                    alert_type=AlertType.LARGE_TRANSACTION,
                    severity=AlertSeverity.INFO,
                    area_id=txn.bank_account.area_id,
                    bank_account_id=txn.bank_account_id,
                    bank_transaction_id=txn.id,
                    title=f"Large Transaction Detected",
                    message=f"Transaction of ${abs(txn.amount):,.2f} on {txn.transaction_date} at {txn.bank_account.account_name}. Description: {txn.description}",
                    amount=abs(txn.amount),
                    is_active=True
                )

                self.db.add(alert)
                alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    def check_reconciliation_stuck_alerts(self, area_id: Optional[int] = None) -> List[BankingAlert]:
        """Check for locations with no reconciliation activity in 7+ days"""
        alerts = []

        # Get areas
        area_query = self.db.query(BankAccount.area_id).distinct()
        if area_id:
            area_query = area_query.filter(BankAccount.area_id == area_id)

        area_ids = [a[0] for a in area_query.all()]

        cutoff_date = datetime.now() - timedelta(days=7)

        for aid in area_ids:
            # Check if any transactions were reconciled in last 7 days
            recent_recon = self.db.query(BankTransaction).join(BankAccount).filter(
                BankAccount.area_id == aid,
                BankTransaction.status == 'reconciled',
                BankTransaction.reconciled_at >= cutoff_date
            ).first()

            # Check if there are unreconciled transactions
            has_unreconciled = self.db.query(BankTransaction).join(BankAccount).filter(
                BankAccount.area_id == aid,
                BankTransaction.status == 'unreconciled'
            ).first()

            # Alert if no recent reconciliation but there are unreconciled transactions
            if not recent_recon and has_unreconciled:
                # Check if alert already exists
                existing = self._find_existing_alert(
                    alert_type=AlertType.RECONCILIATION_STUCK,
                    area_id=aid
                )

                if not existing:
                    area_obj = self.db.query(BankAccount.area).filter(BankAccount.area_id == aid).first()

                    alert = BankingAlert(
                        alert_type=AlertType.RECONCILIATION_STUCK,
                        severity=AlertSeverity.WARNING,
                        area_id=aid,
                        title=f"No Recent Reconciliation Activity",
                        message=f"No transactions have been reconciled at {area_obj[0].name if area_obj else f'Area {aid}'} in the last 7 days. Please review reconciliation status.",
                        is_active=True
                    )

                    self.db.add(alert)
                    alerts.append(alert)

        if alerts:
            self.db.commit()

        return alerts

    # ========================================================================
    # Alert Management
    # ========================================================================

    def acknowledge_alert(self, alert_id: int, user_id: int) -> BankingAlert:
        """Acknowledge an alert"""
        alert = self.db.query(BankingAlert).filter(BankingAlert.id == alert_id).first()

        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        alert.acknowledge(user_id)
        self.db.commit()
        self.db.refresh(alert)

        return alert

    def resolve_alert(self, alert_id: int, user_id: int, notes: Optional[str] = None) -> BankingAlert:
        """Resolve an alert"""
        alert = self.db.query(BankingAlert).filter(BankingAlert.id == alert_id).first()

        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        alert.resolve(user_id, notes)
        self.db.commit()
        self.db.refresh(alert)

        return alert

    def get_active_alerts(
        self,
        area_id: Optional[int] = None,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None
    ) -> List[BankingAlert]:
        """Get active alerts with optional filters"""
        query = self.db.query(BankingAlert).filter(BankingAlert.is_active == True)

        if area_id:
            query = query.filter(BankingAlert.area_id == area_id)

        if severity:
            query = query.filter(BankingAlert.severity == severity)

        if alert_type:
            query = query.filter(BankingAlert.alert_type == alert_type)

        query = query.order_by(BankingAlert.severity.desc(), BankingAlert.created_at.desc())

        return query.all()

    def _find_existing_alert(
        self,
        alert_type: AlertType,
        area_id: Optional[int] = None,
        bank_account_id: Optional[int] = None,
        bank_transaction_id: Optional[int] = None
    ) -> Optional[BankingAlert]:
        """Find existing active alert with same parameters"""
        query = self.db.query(BankingAlert).filter(
            BankingAlert.alert_type == alert_type,
            BankingAlert.is_active == True
        )

        if area_id:
            query = query.filter(BankingAlert.area_id == area_id)

        if bank_account_id:
            query = query.filter(BankingAlert.bank_account_id == bank_account_id)

        if bank_transaction_id:
            query = query.filter(BankingAlert.bank_transaction_id == bank_transaction_id)

        return query.first()

    def auto_resolve_alerts(self) -> int:
        """
        Auto-resolve alerts that are no longer relevant.

        Returns count of auto-resolved alerts.
        """
        resolved_count = 0

        # Resolve GL variance alerts if variance is now < $100
        gl_alerts = self.get_active_alerts(alert_type=AlertType.GL_VARIANCE)
        for alert in gl_alerts:
            if alert.bank_account:
                bank_balance = alert.bank_account.current_balance or Decimal("0")

                if alert.bank_account.gl_account_id:
                    gl_balance_record = self.db.query(AccountBalance).filter(
                        AccountBalance.account_id == alert.bank_account.gl_account_id,
                        AccountBalance.location_id == alert.bank_account.area_id
                    ).first()

                    gl_balance = gl_balance_record.net_balance if gl_balance_record else Decimal("0")
                    variance = abs(bank_balance - gl_balance)

                    if variance < 100:
                        alert.is_active = False
                        alert.is_resolved = True
                        alert.resolution_notes = "Auto-resolved: Variance is now below threshold"
                        resolved_count += 1

        # Resolve low balance alerts if balance is now > $5,000
        low_balance_alerts = self.get_active_alerts(alert_type=AlertType.LOW_BALANCE)
        for alert in low_balance_alerts:
            if alert.bank_account:
                balance = alert.bank_account.current_balance or Decimal("0")
                if balance >= 5000:
                    alert.is_active = False
                    alert.is_resolved = True
                    alert.resolution_notes = "Auto-resolved: Balance is now above threshold"
                    resolved_count += 1

        # Resolve negative balance alerts if balance is now positive
        neg_balance_alerts = self.get_active_alerts(alert_type=AlertType.NEGATIVE_BALANCE)
        for alert in neg_balance_alerts:
            if alert.bank_account:
                balance = alert.bank_account.current_balance or Decimal("0")
                if balance >= 0:
                    alert.is_active = False
                    alert.is_resolved = True
                    alert.resolution_notes = "Auto-resolved: Balance is now positive"
                    resolved_count += 1

        if resolved_count > 0:
            self.db.commit()

        return resolved_count
