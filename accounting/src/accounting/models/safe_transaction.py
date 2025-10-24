"""
Safe Transaction models
Tracks cash movements in/out of the restaurant safe
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


class SafeTransaction(Base):
    """Cash transactions for the restaurant safe"""
    __tablename__ = "safe_transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Transaction type: 'deposit' (add to safe), 'withdrawal' (remove from safe), 'adjustment'
    transaction_type = Column(String(20), nullable=False, index=True)

    amount = Column(Numeric(15, 2), nullable=False)

    # Reference to what triggered this transaction
    reference_type = Column(String(50), nullable=True)  # 'cash_reconciliation', 'bank_withdrawal', 'tip_payout', 'manual'
    reference_id = Column(Integer, nullable=True)  # ID of related record (DSS, bank transaction, etc.)

    description = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)

    # Link to journal entry if posted
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)

    # Running balance after this transaction
    balance_after = Column(Numeric(15, 2), nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    is_posted = Column(Boolean, nullable=False, default=False, index=True)
    posted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    posted_at = Column(DateTime, nullable=True)

    # Relationships
    area = relationship("Area", back_populates="safe_transactions")
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])
    poster = relationship("User", foreign_keys=[posted_by])

    def __repr__(self):
        return f"<SafeTransaction {self.transaction_date} - {self.transaction_type}: ${self.amount}>"
