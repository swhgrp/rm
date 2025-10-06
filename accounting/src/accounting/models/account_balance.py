"""
Account Balance model (cached balances for performance)
"""
from sqlalchemy import Column, Integer, DateTime, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


class AccountBalance(Base):
    __tablename__ = "account_balances"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    fiscal_period_id = Column(Integer, ForeignKey('fiscal_periods.id'), nullable=False)
    location_id = Column(Integer, nullable=True, index=True)  # NULL = all locations

    debit_balance = Column(DECIMAL(15, 2), default=0)
    credit_balance = Column(DECIMAL(15, 2), default=0)
    net_balance = Column(DECIMAL(15, 2), default=0)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    account = relationship("Account", back_populates="balances")
    fiscal_period = relationship("FiscalPeriod", back_populates="balances")
