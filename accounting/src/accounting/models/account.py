"""
Chart of Accounts model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class AccountType(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"
    COGS = "COGS"  # Cost of Goods Sold


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String(20), unique=True, nullable=False, index=True)
    account_name = Column(String(200), nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    parent_account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships (using lazy loading to avoid circular imports)
    parent_account = relationship("Account", remote_side=[id], backref="sub_accounts")
    journal_entry_lines = relationship("JournalEntryLine", back_populates="account", lazy="dynamic")
    balances = relationship("AccountBalance", back_populates="account", lazy="dynamic")
