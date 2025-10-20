"""
Account Group model for organizing accounts in financial reports
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class ReportSection(str, enum.Enum):
    """Major sections in financial reports"""
    REVENUE = "REVENUE"
    COGS = "COGS"  # Cost of Goods Sold / Cost of Revenue
    OPERATING_EXPENSES = "OPERATING_EXPENSES"
    OTHER_INCOME = "OTHER_INCOME"
    OTHER_EXPENSES = "OTHER_EXPENSES"


class AccountGroup(Base):
    """
    Account groups for organizing accounts in financial reports.

    Examples:
    - "4100-4103 Food Sale" (Revenue group)
    - "5100-5120 Food Cost" (COGS group)
    - "6105-6133 Payroll" (Operating Expense group)
    """
    __tablename__ = "account_groups"

    id = Column(Integer, primary_key=True, index=True)

    # Group identification
    name = Column(String(200), nullable=False)  # e.g., "Food Sale", "Payroll"
    code = Column(String(50), unique=True, nullable=False, index=True)  # e.g., "4100-4103", "6105-6133"

    # Display formatting
    display_name = Column(String(250), nullable=False)  # e.g., "4100-4103 Food Sale"
    description = Column(Text, nullable=True)

    # Report organization
    report_section = Column(Enum(ReportSection), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)  # Order within section

    # Optional parent for nested groups
    parent_group_id = Column(Integer, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    accounts = relationship("Account", back_populates="account_group", lazy="dynamic")

    def __repr__(self):
        return f"<AccountGroup {self.display_name}>"
