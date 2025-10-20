"""
Journal Entry models
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Enum, ForeignKey, Text, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class JournalEntryStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    entry_number = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text)

    # Reference to source transaction (from inventory system)
    reference_type = Column(String(50))  # 'INVOICE', 'TRANSFER', 'WASTE', 'SALE'
    reference_id = Column(Integer)

    # Location reference (from inventory system)
    location_id = Column(Integer, index=True)

    # User references (from inventory system)
    created_by = Column(Integer)
    approved_by = Column(Integer, nullable=True)

    # Status
    status = Column(Enum(JournalEntryStatus), default=JournalEntryStatus.DRAFT, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    posted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    lines = relationship("JournalEntryLine", back_populates="journal_entry", cascade="all, delete-orphan")


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"

    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    area_id = Column(Integer, ForeignKey('areas.id', ondelete='SET NULL'), nullable=True, index=True)

    debit_amount = Column(DECIMAL(15, 2), default=0)
    credit_amount = Column(DECIMAL(15, 2), default=0)
    description = Column(Text)
    line_number = Column(Integer)

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_entry_lines")
    area = relationship("Area", back_populates="journal_entry_lines")
