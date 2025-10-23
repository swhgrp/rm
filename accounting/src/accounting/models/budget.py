"""Budget models for budget management system"""
import enum
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Numeric, Boolean, ForeignKey, Enum as SQLEnum, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from accounting.db.database import Base


class BudgetStatus(str, enum.Enum):
    """Budget status types"""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class BudgetPeriodType(str, enum.Enum):
    """Budget period types"""
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"


class Budget(Base):
    """Budget header"""
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True)
    budget_name = Column(String(200), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(SQLEnum(BudgetStatus), nullable=False, default=BudgetStatus.DRAFT)
    budget_type = Column(String(50), nullable=False, default="OPERATING")  # OPERATING, CAPITAL, CASH_FLOW
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    department = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Summary totals (computed from budget lines)
    total_revenue = Column(Numeric(15, 2), nullable=False, default=0)
    total_expenses = Column(Numeric(15, 2), nullable=False, default=0)
    net_income = Column(Numeric(15, 2), nullable=False, default=0)

    # Audit fields
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    area = relationship("Area", back_populates="budgets")
    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])
    periods = relationship("BudgetPeriod", back_populates="budget", cascade="all, delete-orphan")
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")
    revisions = relationship("BudgetRevision", back_populates="budget", cascade="all, delete-orphan")
    alerts = relationship("BudgetAlert", back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_budgets_fiscal_year', 'fiscal_year'),
        Index('idx_budgets_status', 'status'),
        Index('idx_budgets_area', 'area_id'),
        Index('idx_budgets_dates', 'start_date', 'end_date'),
    )

    def __repr__(self):
        return f"<Budget {self.budget_name} FY{self.fiscal_year}>"


class BudgetPeriod(Base):
    """Budget period (monthly/quarterly breakdown)"""
    __tablename__ = "budget_periods"

    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    period_type = Column(SQLEnum(BudgetPeriodType), nullable=False)
    period_number = Column(Integer, nullable=False)  # 1-12 for months, 1-4 for quarters
    period_name = Column(String(50), nullable=False)  # "January 2025", "Q1 2025"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_locked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    budget = relationship("Budget", back_populates="periods")
    lines = relationship("BudgetLine", back_populates="budget_period", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('budget_id', 'period_type', 'period_number', name='uq_budget_period'),
        Index('idx_budget_periods_budget', 'budget_id'),
        Index('idx_budget_periods_dates', 'start_date', 'end_date'),
    )

    def __repr__(self):
        return f"<BudgetPeriod {self.period_name}>"


class BudgetLine(Base):
    """Budget line item (account-level budget amount)"""
    __tablename__ = "budget_lines"

    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    budget_period_id = Column(Integer, ForeignKey("budget_periods.id", ondelete="CASCADE"), nullable=True)  # NULL = annual
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    budget = relationship("Budget", back_populates="lines")
    budget_period = relationship("BudgetPeriod", back_populates="lines")
    account = relationship("Account", back_populates="budget_lines")

    __table_args__ = (
        UniqueConstraint('budget_id', 'budget_period_id', 'account_id', name='uq_budget_line'),
        Index('idx_budget_lines_budget', 'budget_id'),
        Index('idx_budget_lines_period', 'budget_period_id'),
        Index('idx_budget_lines_account', 'account_id'),
    )

    def __repr__(self):
        return f"<BudgetLine Account#{self.account_id} ${self.amount}>"


class BudgetTemplate(Base):
    """Budget template for reuse"""
    __tablename__ = "budget_templates"

    id = Column(Integer, primary_key=True)
    template_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    budget_type = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("User")
    lines = relationship("BudgetTemplateLine", back_populates="template", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BudgetTemplate {self.template_name}>"


class BudgetTemplateLine(Base):
    """Budget template line item"""
    __tablename__ = "budget_template_lines"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("budget_templates.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    allocation_method = Column(String(20), nullable=False, default="EQUAL")  # EQUAL, WEIGHTED, MANUAL
    growth_rate = Column(Numeric(5, 2), nullable=True)  # % growth from prior year
    monthly_allocation = Column(JSONB, nullable=True)  # {1: 0.08, 2: 0.08, ...}
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    template = relationship("BudgetTemplate", back_populates="lines")
    account = relationship("Account")

    __table_args__ = (
        UniqueConstraint('template_id', 'account_id', name='uq_template_line'),
    )

    def __repr__(self):
        return f"<BudgetTemplateLine Account#{self.account_id}>"


class BudgetRevision(Base):
    """Budget revision tracking"""
    __tablename__ = "budget_revisions"

    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    revision_number = Column(Integer, nullable=False)
    revision_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    revised_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    total_revenue_change = Column(Numeric(15, 2), nullable=False, default=0)
    total_expense_change = Column(Numeric(15, 2), nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    budget = relationship("Budget", back_populates="revisions")
    reviser = relationship("User", foreign_keys=[revised_by])
    approver = relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        UniqueConstraint('budget_id', 'revision_number', name='uq_budget_revision'),
    )

    def __repr__(self):
        return f"<BudgetRevision #{self.revision_number} for Budget#{self.budget_id}>"


class BudgetAlert(Base):
    """Budget variance alert configuration"""
    __tablename__ = "budget_alerts"

    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)  # NULL = entire budget
    alert_type = Column(String(20), nullable=False)  # OVER_BUDGET, UNDER_BUDGET, VARIANCE
    threshold_percent = Column(Numeric(5, 2), nullable=False)  # Alert when variance exceeds %
    threshold_amount = Column(Numeric(15, 2), nullable=True)  # Alert when variance exceeds $
    notify_users = Column(ARRAY(Integer), nullable=True)  # Array of user IDs to notify
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    budget = relationship("Budget", back_populates="alerts")
    account = relationship("Account")

    def __repr__(self):
        return f"<BudgetAlert {self.alert_type} >{self.threshold_percent}%>"
