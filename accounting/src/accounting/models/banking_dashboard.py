"""Models for Banking Dashboard metrics and alerts"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Boolean, Text, func, Enum as SQLEnum
from sqlalchemy.orm import relationship
from accounting.db.database import Base
from decimal import Decimal
from datetime import date, timedelta
import enum


class CashFlowCategory(str, enum.Enum):
    """Categories for cash flow classification"""
    OPERATING_INFLOW = "operating_inflow"
    OPERATING_OUTFLOW = "operating_outflow"
    INVESTING_INFLOW = "investing_inflow"
    INVESTING_OUTFLOW = "investing_outflow"
    FINANCING_INFLOW = "financing_inflow"
    FINANCING_OUTFLOW = "financing_outflow"
    TRANSFER = "transfer"


class AlertSeverity(str, enum.Enum):
    """Alert severity levels"""
    CRITICAL = "critical"  # Requires immediate attention
    WARNING = "warning"    # Should be reviewed soon
    INFO = "info"          # Informational only


class AlertType(str, enum.Enum):
    """Types of banking alerts"""
    GL_VARIANCE = "gl_variance"
    LOW_BALANCE = "low_balance"
    UNRECONCILED_OLD = "unreconciled_old"
    MISSING_TRANSACTION = "missing_transaction"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    UNUSUAL_AMOUNT = "unusual_amount"
    RECONCILIATION_STUCK = "reconciliation_stuck"
    NEGATIVE_BALANCE = "negative_balance"
    LARGE_TRANSACTION = "large_transaction"


class DailyCashPosition(Base):
    """
    Daily snapshot of cash position by location.

    Stores end-of-day balances for all bank accounts to enable
    historical trending and cash flow analysis.
    """
    __tablename__ = "daily_cash_positions"

    id = Column(Integer, primary_key=True, index=True)
    position_date = Column(Date, nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False, index=True)

    # Balances
    opening_balance = Column(Numeric(15, 2), nullable=False)
    closing_balance = Column(Numeric(15, 2), nullable=False)

    # Daily activity
    total_inflows = Column(Numeric(15, 2), nullable=False, default=0)
    total_outflows = Column(Numeric(15, 2), nullable=False, default=0)
    net_change = Column(Numeric(15, 2), nullable=False, default=0)

    # Transaction counts
    transaction_count = Column(Integer, nullable=False, default=0)
    reconciled_count = Column(Integer, nullable=False, default=0)
    unreconciled_count = Column(Integer, nullable=False, default=0)

    # GL comparison
    gl_balance = Column(Numeric(15, 2), nullable=True)  # GL cash account balance
    variance = Column(Numeric(15, 2), nullable=True)  # Bank - GL

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")
    bank_account = relationship("BankAccount")

    def calculate_net_change(self):
        """Calculate net change for the day"""
        self.net_change = self.closing_balance - self.opening_balance

    def calculate_variance(self):
        """Calculate variance between bank and GL"""
        if self.gl_balance is not None:
            self.variance = self.closing_balance - self.gl_balance


class CashFlowTransaction(Base):
    """
    Categorized cash flow transactions for cash flow statement generation.

    Links bank transactions to cash flow categories to enable
    operating/investing/financing cash flow reporting.
    """
    __tablename__ = "cash_flow_transactions"

    id = Column(Integer, primary_key=True, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)

    # Classification
    category = Column(SQLEnum(CashFlowCategory), nullable=False, index=True)
    subcategory = Column(String(100), nullable=True)  # e.g., "Food Purchases", "Equipment", "Loan Payment"

    # Transaction details
    amount = Column(Numeric(15, 2), nullable=False)
    transaction_date = Column(Date, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Auto-classification metadata
    is_auto_classified = Column(Boolean, nullable=False, default=False)
    classification_confidence = Column(Numeric(5, 2), nullable=True)  # 0-100%

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    bank_transaction = relationship("BankTransaction")
    area = relationship("Area")


class BankingAlert(Base):
    """
    Banking alerts and notifications.

    Stores alerts for various banking issues that require attention:
    - GL variances
    - Low balances
    - Old unreconciled transactions
    - Missing expected transactions
    - Unusual amounts
    """
    __tablename__ = "banking_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(SQLEnum(AlertType), nullable=False, index=True)
    severity = Column(SQLEnum(AlertSeverity), nullable=False, index=True)

    # Scope
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True, index=True)
    bank_transaction_id = Column(Integer, ForeignKey("bank_transactions.id"), nullable=True, index=True)

    # Alert details
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    amount = Column(Numeric(15, 2), nullable=True)  # Relevant amount (variance, balance, etc.)

    # Alert state
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    # Resolution
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")
    bank_account = relationship("BankAccount")
    bank_transaction = relationship("BankTransaction")
    acknowledged_user = relationship("User", foreign_keys=[acknowledged_by])
    resolved_user = relationship("User", foreign_keys=[resolved_by])

    def acknowledge(self, user_id: int):
        """Mark alert as acknowledged"""
        self.is_acknowledged = True
        self.acknowledged_by = user_id
        self.acknowledged_at = func.current_timestamp()

    def resolve(self, user_id: int, notes: str = None):
        """Mark alert as resolved"""
        self.is_resolved = True
        self.is_active = False
        self.resolved_by = user_id
        self.resolved_at = func.current_timestamp()
        if notes:
            self.resolution_notes = notes


class ReconciliationHealthMetric(Base):
    """
    Daily reconciliation health metrics.

    Tracks reconciliation quality metrics over time:
    - Reconciliation rate
    - Average time to reconcile
    - Accuracy metrics
    - Automation effectiveness
    """
    __tablename__ = "reconciliation_health_metrics"

    id = Column(Integer, primary_key=True, index=True)
    metric_date = Column(Date, nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)

    # Reconciliation metrics
    total_transactions = Column(Integer, nullable=False, default=0)
    reconciled_transactions = Column(Integer, nullable=False, default=0)
    unreconciled_transactions = Column(Integer, nullable=False, default=0)
    reconciliation_rate = Column(Numeric(5, 2), nullable=True)  # Percentage

    # Timeliness metrics
    avg_days_to_reconcile = Column(Numeric(10, 2), nullable=True)
    transactions_over_30_days = Column(Integer, nullable=False, default=0)
    transactions_over_60_days = Column(Integer, nullable=False, default=0)
    transactions_over_90_days = Column(Integer, nullable=False, default=0)

    # Automation metrics
    auto_matched_count = Column(Integer, nullable=False, default=0)
    manual_matched_count = Column(Integer, nullable=False, default=0)
    auto_match_rate = Column(Numeric(5, 2), nullable=True)  # Percentage

    # Accuracy metrics
    gl_variance_count = Column(Integer, nullable=False, default=0)  # Number of accounts with variance
    total_gl_variance = Column(Numeric(15, 2), nullable=True)  # Sum of all variances
    avg_gl_variance = Column(Numeric(15, 2), nullable=True)

    # Active alerts
    critical_alerts = Column(Integer, nullable=False, default=0)
    warning_alerts = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")

    def calculate_reconciliation_rate(self):
        """Calculate reconciliation rate percentage"""
        if self.total_transactions > 0:
            self.reconciliation_rate = (self.reconciled_transactions / self.total_transactions) * 100
        else:
            self.reconciliation_rate = 0

    def calculate_auto_match_rate(self):
        """Calculate auto-match rate percentage"""
        total_matched = self.auto_matched_count + self.manual_matched_count
        if total_matched > 0:
            self.auto_match_rate = (self.auto_matched_count / total_matched) * 100
        else:
            self.auto_match_rate = 0


class LocationCashFlowSummary(Base):
    """
    Monthly cash flow summary by location.

    Aggregates cash flow metrics by month and location for
    trending and forecasting.
    """
    __tablename__ = "location_cash_flow_summaries"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False, index=True)
    summary_month = Column(Date, nullable=False, index=True)  # First day of month

    # Opening/closing balances
    opening_balance = Column(Numeric(15, 2), nullable=False)
    closing_balance = Column(Numeric(15, 2), nullable=False)

    # Operating cash flow
    operating_inflows = Column(Numeric(15, 2), nullable=False, default=0)
    operating_outflows = Column(Numeric(15, 2), nullable=False, default=0)
    net_operating_cash_flow = Column(Numeric(15, 2), nullable=False, default=0)

    # Investing cash flow
    investing_inflows = Column(Numeric(15, 2), nullable=False, default=0)
    investing_outflows = Column(Numeric(15, 2), nullable=False, default=0)
    net_investing_cash_flow = Column(Numeric(15, 2), nullable=False, default=0)

    # Financing cash flow
    financing_inflows = Column(Numeric(15, 2), nullable=False, default=0)
    financing_outflows = Column(Numeric(15, 2), nullable=False, default=0)
    net_financing_cash_flow = Column(Numeric(15, 2), nullable=False, default=0)

    # Total net change
    net_cash_change = Column(Numeric(15, 2), nullable=False, default=0)

    # Burn rate metrics
    daily_burn_rate = Column(Numeric(15, 2), nullable=True)  # Average daily cash consumption
    runway_days = Column(Integer, nullable=True)  # Days until cash runs out at current burn rate

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")

    def calculate_net_cash_flows(self):
        """Calculate net cash flows for each category"""
        self.net_operating_cash_flow = self.operating_inflows - self.operating_outflows
        self.net_investing_cash_flow = self.investing_inflows - self.investing_outflows
        self.net_financing_cash_flow = self.financing_inflows - self.financing_outflows
        self.net_cash_change = (
            self.net_operating_cash_flow +
            self.net_investing_cash_flow +
            self.net_financing_cash_flow
        )

    def calculate_burn_rate(self):
        """Calculate daily burn rate and runway"""
        # Burn rate is negative net operating cash flow divided by days in month
        if self.net_operating_cash_flow < 0:
            # Assuming 30 days per month for simplicity
            self.daily_burn_rate = abs(self.net_operating_cash_flow) / 30

            # Runway is current balance divided by daily burn rate
            if self.daily_burn_rate > 0:
                self.runway_days = int(self.closing_balance / self.daily_burn_rate)
            else:
                self.runway_days = None
        else:
            self.daily_burn_rate = 0
            self.runway_days = None  # Positive cash flow means no runway concern
