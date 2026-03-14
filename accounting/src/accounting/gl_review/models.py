"""
SQLAlchemy models for GL Anomaly Review system.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Date, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from accounting.db.database import Base


# --- Flag type constants ---
UNBALANCED_ENTRY = "UNBALANCED_ENTRY"
DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
WRONG_NORMAL_BALANCE = "WRONG_NORMAL_BALANCE"
MISSING_DESCRIPTION = "MISSING_DESCRIPTION"
ROUND_NUMBER_ANOMALY = "ROUND_NUMBER_ANOMALY"
OUT_OF_HOURS_POSTING = "OUT_OF_HOURS_POSTING"
STATISTICAL_OUTLIER = "STATISTICAL_OUTLIER"
NEGATIVE_BALANCE = "NEGATIVE_BALANCE"
FOOD_COST_SPIKE = "FOOD_COST_SPIKE"

ALL_FLAG_TYPES = [
    UNBALANCED_ENTRY,
    DUPLICATE_ENTRY,
    WRONG_NORMAL_BALANCE,
    MISSING_DESCRIPTION,
    ROUND_NUMBER_ANOMALY,
    OUT_OF_HOURS_POSTING,
    STATISTICAL_OUTLIER,
    NEGATIVE_BALANCE,
    FOOD_COST_SPIKE,
]

# --- Severity constants ---
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# --- Status constants ---
STATUS_OPEN = "open"
STATUS_REVIEWED = "reviewed"
STATUS_DISMISSED = "dismissed"
STATUS_ESCALATED = "escalated"
STATUS_SUPERSEDED = "superseded"


class GLAnomalyFlag(Base):
    __tablename__ = "gl_anomaly_flags"

    id = Column(Integer, primary_key=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    journal_entry_line_id = Column(Integer, ForeignKey("journal_entry_lines.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    flag_type = Column(String(60), nullable=False)
    severity = Column(String(20), nullable=False, default=SEVERITY_WARNING)
    title = Column(String(255), nullable=False)
    detail = Column(Text)
    flagged_value = Column(Numeric(15, 2))
    expected_range_low = Column(Numeric(15, 2))
    expected_range_high = Column(Numeric(15, 2))
    period_date = Column(Date, index=True)
    status = Column(String(30), nullable=False, default=STATUS_OPEN, index=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True))
    review_note = Column(Text)
    ai_reasoning = Column(Text)
    ai_confidence = Column(String(20))
    run_id = Column(String(36), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    area = relationship("Area", foreign_keys=[area_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
    journal_entry_line = relationship("JournalEntryLine", foreign_keys=[journal_entry_line_id])
    account = relationship("Account", foreign_keys=[account_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class GLAccountBaseline(Base):
    __tablename__ = "gl_account_baselines"
    __table_args__ = (UniqueConstraint("area_id", "account_id"),)

    id = Column(Integer, primary_key=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    account_code = Column(String(30))
    months_of_data = Column(Integer)
    avg_monthly_balance = Column(Numeric(15, 2))
    stddev_monthly_balance = Column(Numeric(15, 2))
    avg_monthly_activity = Column(Numeric(15, 2))
    stddev_monthly_activity = Column(Numeric(15, 2))
    min_observed = Column(Numeric(15, 2))
    max_observed = Column(Numeric(15, 2))
    typical_posting_days = Column(JSONB)
    last_computed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    area = relationship("Area", foreign_keys=[area_id])
    account = relationship("Account", foreign_keys=[account_id])
