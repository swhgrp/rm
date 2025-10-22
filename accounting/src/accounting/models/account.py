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


class CashFlowClass(str, enum.Enum):
    """Cash flow statement classification for accounts"""
    OPERATING = "OPERATING"      # Operating activities (normal business operations)
    INVESTING = "INVESTING"      # Investing activities (assets, investments)
    FINANCING = "FINANCING"      # Financing activities (debt, equity)
    NON_CASH = "NON_CASH"       # Non-cash items (depreciation, etc.)
    NONE = "NONE"                # Not applicable to cash flow (e.g., cash accounts)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String(20), unique=True, nullable=False, index=True)
    account_name = Column(String(200), nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    parent_account_id = Column(Integer, ForeignKey('accounts.id'), nullable=True, index=True)
    account_group_id = Column(Integer, ForeignKey('account_groups.id'), nullable=True, index=True)
    is_summary = Column(Boolean, default=False, nullable=False)  # True = parent/summary account, False = detail account
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    cash_flow_class = Column(Enum(CashFlowClass), nullable=True)  # Cash flow statement classification
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships (using lazy loading to avoid circular imports)
    parent_account = relationship("Account", remote_side=[id], backref="sub_accounts")
    account_group = relationship("AccountGroup", back_populates="accounts")
    journal_entry_lines = relationship("JournalEntryLine", back_populates="account", lazy="dynamic")
    balances = relationship("AccountBalance", back_populates="account", lazy="dynamic")

    def get_hierarchy_level(self):
        """Get the depth level in the account hierarchy (0 = top level)"""
        level = 0
        current = self
        while current.parent_account_id:
            level += 1
            current = current.parent_account
        return level

    def get_all_children(self, db_session):
        """Recursively get all child accounts (direct and nested)"""
        children = []
        for child in self.sub_accounts:
            children.append(child)
            children.extend(child.get_all_children(db_session))
        return children

    def would_create_cycle(self, new_parent_id):
        """Check if setting new_parent_id would create a circular reference"""
        if not new_parent_id:
            return False
        if new_parent_id == self.id:
            return True
        # Check if new_parent is already a descendant
        current = self.parent_account
        while current:
            if current.id == new_parent_id:
                return True
            current = current.parent_account
        return False
