"""
Fiscal Period model
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class FiscalPeriodStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"

    id = Column(Integer, primary_key=True, index=True)
    period_name = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=True)  # 1-4 or NULL for annual
    status = Column(Enum(FiscalPeriodStatus), default=FiscalPeriodStatus.OPEN, nullable=False)

    # Closing information
    closed_by = Column(Integer, nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    balances = relationship("AccountBalance", back_populates="fiscal_period")
