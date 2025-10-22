"""Models for General Accounting Dashboard metrics and alerts"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, ForeignKey, Text, func, Enum as SQLEnum
from sqlalchemy.orm import relationship
from accounting.db.database import Base
from decimal import Decimal
from datetime import date
import enum


class DashboardAlertType(str, enum.Enum):
    """Types of dashboard alerts"""
    UNPOSTED_JOURNAL = "UNPOSTED_JOURNAL"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"
    MISSING_DSS_MAPPING = "MISSING_DSS_MAPPING"
    GL_BALANCE_OUTLIER = "GL_BALANCE_OUTLIER"
    SALES_DROP = "SALES_DROP"
    COGS_HIGH = "COGS_HIGH"
    AP_AGING_HIGH = "AP_AGING_HIGH"
    MISSING_INVENTORY = "MISSING_INVENTORY"
    NEGATIVE_CASH = "NEGATIVE_CASH"
    PERIOD_NOT_CLOSED = "PERIOD_NOT_CLOSED"


class DailyFinancialSnapshot(Base):
    """
    Daily aggregated financial metrics.

    Stores daily snapshots of sales, COGS, expenses, and profitability
    to enable real-time dashboard views and trend analysis.
    """
    __tablename__ = "daily_financial_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)

    # Revenue metrics
    total_sales = Column(Numeric(15, 2), nullable=False, default=0)
    food_sales = Column(Numeric(15, 2), nullable=False, default=0)
    beverage_sales = Column(Numeric(15, 2), nullable=False, default=0)
    alcohol_sales = Column(Numeric(15, 2), nullable=False, default=0)

    # COGS metrics
    total_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    food_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    beverage_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    cogs_percentage = Column(Numeric(5, 2), nullable=True)

    # Gross profit
    gross_profit = Column(Numeric(15, 2), nullable=False, default=0)
    gross_profit_margin = Column(Numeric(5, 2), nullable=True)

    # Operating metrics
    total_expenses = Column(Numeric(15, 2), nullable=False, default=0)
    labor_expense = Column(Numeric(15, 2), nullable=True)
    labor_percentage = Column(Numeric(5, 2), nullable=True)

    # Net income
    net_income = Column(Numeric(15, 2), nullable=False, default=0)
    net_income_margin = Column(Numeric(5, 2), nullable=True)

    # Transaction counts
    transaction_count = Column(Integer, nullable=False, default=0)
    average_check = Column(Numeric(10, 2), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")

    def calculate_metrics(self):
        """Calculate derived metrics"""
        if self.total_sales and self.total_sales > 0:
            self.cogs_percentage = (self.total_cogs / self.total_sales) * 100
            self.gross_profit_margin = (self.gross_profit / self.total_sales) * 100
            self.net_income_margin = (self.net_income / self.total_sales) * 100
            if self.labor_expense:
                self.labor_percentage = (self.labor_expense / self.total_sales) * 100

        if self.transaction_count and self.transaction_count > 0:
            self.average_check = self.total_sales / self.transaction_count


class MonthlyPerformanceSummary(Base):
    """
    Monthly performance summary for closed periods.

    Stores comprehensive financial metrics for each closed month,
    including revenue, expenses, profitability, and comparisons to
    prior periods and budget.
    """
    __tablename__ = "monthly_performance_summaries"

    id = Column(Integer, primary_key=True, index=True)
    period_month = Column(Date, nullable=False, index=True)  # First day of month
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)
    is_closed = Column(Boolean, nullable=False, default=False)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Revenue
    total_revenue = Column(Numeric(15, 2), nullable=False, default=0)
    food_revenue = Column(Numeric(15, 2), nullable=False, default=0)
    beverage_revenue = Column(Numeric(15, 2), nullable=False, default=0)
    other_revenue = Column(Numeric(15, 2), nullable=False, default=0)

    # COGS
    total_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    food_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    beverage_cogs = Column(Numeric(15, 2), nullable=False, default=0)
    cogs_percentage = Column(Numeric(5, 2), nullable=True)

    # Operating Expenses by category
    labor_expense = Column(Numeric(15, 2), nullable=False, default=0)
    labor_percentage = Column(Numeric(5, 2), nullable=True)
    rent_expense = Column(Numeric(15, 2), nullable=False, default=0)
    utilities_expense = Column(Numeric(15, 2), nullable=False, default=0)
    marketing_expense = Column(Numeric(15, 2), nullable=False, default=0)
    repairs_expense = Column(Numeric(15, 2), nullable=False, default=0)
    other_expenses = Column(Numeric(15, 2), nullable=False, default=0)
    total_operating_expenses = Column(Numeric(15, 2), nullable=False, default=0)

    # Profitability
    gross_profit = Column(Numeric(15, 2), nullable=False, default=0)
    gross_profit_margin = Column(Numeric(5, 2), nullable=True)
    operating_income = Column(Numeric(15, 2), nullable=False, default=0)
    operating_margin = Column(Numeric(5, 2), nullable=True)
    net_income = Column(Numeric(15, 2), nullable=False, default=0)
    net_income_margin = Column(Numeric(5, 2), nullable=True)

    # Prime Cost (COGS + Labor)
    prime_cost = Column(Numeric(15, 2), nullable=False, default=0)
    prime_cost_percentage = Column(Numeric(5, 2), nullable=True)

    # Comparison to previous period
    revenue_vs_prior = Column(Numeric(5, 2), nullable=True)  # Percentage change
    cogs_vs_prior = Column(Numeric(5, 2), nullable=True)
    labor_vs_prior = Column(Numeric(5, 2), nullable=True)
    net_income_vs_prior = Column(Numeric(5, 2), nullable=True)

    # Budget variance
    budgeted_revenue = Column(Numeric(15, 2), nullable=True)
    revenue_variance = Column(Numeric(15, 2), nullable=True)
    revenue_variance_pct = Column(Numeric(5, 2), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")
    closed_by_user = relationship("User", foreign_keys=[closed_by])

    def calculate_metrics(self):
        """Calculate derived metrics"""
        # Gross profit
        self.gross_profit = self.total_revenue - self.total_cogs

        # Operating income
        self.operating_income = self.gross_profit - self.total_operating_expenses

        # Net income (simplified - no other income/expenses)
        self.net_income = self.operating_income

        # Prime cost
        self.prime_cost = self.total_cogs + self.labor_expense

        # Percentages
        if self.total_revenue and self.total_revenue > 0:
            self.cogs_percentage = (self.total_cogs / self.total_revenue) * 100
            self.gross_profit_margin = (self.gross_profit / self.total_revenue) * 100
            self.operating_margin = (self.operating_income / self.total_revenue) * 100
            self.net_income_margin = (self.net_income / self.total_revenue) * 100
            self.labor_percentage = (self.labor_expense / self.total_revenue) * 100
            self.prime_cost_percentage = (self.prime_cost / self.total_revenue) * 100

        # Budget variance
        if self.budgeted_revenue and self.budgeted_revenue > 0:
            self.revenue_variance = self.total_revenue - self.budgeted_revenue
            self.revenue_variance_pct = (self.revenue_variance / self.budgeted_revenue) * 100


class DashboardAlert(Base):
    """
    System-generated alerts for accounting control and exceptions.

    Monitors various accounting health metrics and generates alerts
    when issues are detected (unposted journals, pending reconciliations,
    anomalies, etc.)
    """
    __tablename__ = "dashboard_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(SQLEnum(DashboardAlertType), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # critical, warning, info
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)

    # Alert details
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    metric_value = Column(Numeric(15, 2), nullable=True)
    threshold_value = Column(Numeric(15, 2), nullable=True)

    # Related entity
    related_entity_type = Column(String(50), nullable=True)  # journal_entry, reconciliation, etc
    related_entity_id = Column(Integer, nullable=True)
    action_url = Column(String(500), nullable=True)  # Link to fix the issue

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


class ExpenseCategorySummary(Base):
    """
    Expense category summaries for dashboard visualization.

    Aggregates expenses by category to show top expense categories,
    trends, and budget variances.
    """
    __tablename__ = "expense_category_summaries"

    id = Column(Integer, primary_key=True, index=True)
    period_month = Column(Date, nullable=False, index=True)  # First day of month
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=True, index=True)
    category_name = Column(String(100), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    # Amounts
    current_month = Column(Numeric(15, 2), nullable=False, default=0)
    prior_month = Column(Numeric(15, 2), nullable=True)
    ytd_total = Column(Numeric(15, 2), nullable=False, default=0)
    budget_amount = Column(Numeric(15, 2), nullable=True)

    # Percentages
    pct_of_revenue = Column(Numeric(5, 2), nullable=True)
    pct_change_mom = Column(Numeric(5, 2), nullable=True)  # Month over month
    pct_of_total_expenses = Column(Numeric(5, 2), nullable=True)

    # Rankings
    rank_by_amount = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    area = relationship("Area")
    account = relationship("Account")

    def calculate_metrics(self, total_revenue: Decimal, total_expenses: Decimal):
        """Calculate derived metrics"""
        if total_revenue and total_revenue > 0:
            self.pct_of_revenue = (self.current_month / total_revenue) * 100

        if total_expenses and total_expenses > 0:
            self.pct_of_total_expenses = (self.current_month / total_expenses) * 100

        if self.prior_month and self.prior_month > 0:
            self.pct_change_mom = ((self.current_month - self.prior_month) / self.prior_month) * 100
