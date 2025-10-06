"""
Cost of Goods Sold Tracking model
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum, ForeignKey, DECIMAL
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class TransactionType(str, enum.Enum):
    SALE = "SALE"
    WASTE = "WASTE"
    TRANSFER_OUT = "TRANSFER_OUT"


class COGSTransaction(Base):
    __tablename__ = "cogs_transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_date = Column(Date, nullable=False, index=True)

    # Item reference (from inventory system)
    item_id = Column(Integer, nullable=False, index=True)
    item_name = Column(String(200), nullable=False)

    # Quantities and costs
    quantity = Column(DECIMAL(10, 3), nullable=False)
    unit_cost = Column(DECIMAL(10, 2), nullable=False)
    total_cost = Column(DECIMAL(12, 2), nullable=False)

    # Location reference
    location_id = Column(Integer, nullable=False, index=True)

    # Transaction type
    transaction_type = Column(Enum(TransactionType), nullable=False)

    # Link to journal entry
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
