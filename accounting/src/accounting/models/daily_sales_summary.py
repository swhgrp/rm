"""
Daily Sales Summary models for POS integration
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from accounting.db.database import Base


class DailySalesSummary(Base):
    """Daily sales summary from POS systems"""
    __tablename__ = "daily_sales_summaries"

    id = Column(Integer, primary_key=True, index=True)
    business_date = Column(Date, nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="RESTRICT"), nullable=False, index=True)
    pos_system = Column(String(50), nullable=True)  # 'CLOVER', 'SQUARE', etc.
    pos_location_id = Column(String(100), nullable=True)  # External POS location ID

    # Sales totals
    gross_sales = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    discounts = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    refunds = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    net_sales = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    tax_collected = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    tips = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    total_collected = Column(Numeric(15, 2), nullable=False, server_default="0.00")

    # Flexible breakdowns stored as JSONB
    payment_breakdown = Column(JSONB, nullable=True)
    # Example: {"cash": 500.00, "credit_card": 1200.00, "gift_card": 100.00}

    category_breakdown = Column(JSONB, nullable=True)
    # Example: {"food": 1200.00, "beverage": 400.00, "alcohol": 200.00}

    discount_breakdown = Column(JSONB, nullable=True)
    # Example: {"employee_discount": 50.00, "happy_hour": 100.00}

    refund_breakdown = Column(JSONB, nullable=True)
    # Example: {"Merchandise": 25.00, "Food": 10.00} - refunds by original sale category

    # Deposit fields - for reconciliation
    card_deposit = Column(Numeric(15, 2), nullable=True)  # Card payments (amount + tips - refunds)
    cash_tips_paid = Column(Numeric(15, 2), nullable=True, server_default="0.00")  # Cash tips paid out to employees
    cash_payouts = Column(Numeric(15, 2), nullable=True, server_default="0.00")  # Cash payouts/adjustments (money taken from drawer)
    payout_breakdown = Column(JSONB, nullable=True)  # Details of each payout: [{"amount": 50.00, "note": "Bank run", "employee": "John"}]

    # Cash reconciliation fields
    expected_cash_deposit = Column(Numeric(15, 2), nullable=True)  # Cash sales - cash tips - payouts
    actual_cash_deposit = Column(Numeric(15, 2), nullable=True)  # Actual cash deposited (manager entry)
    cash_variance = Column(Numeric(15, 2), nullable=True)  # Actual - Expected
    cash_reconciled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cash_reconciled_at = Column(DateTime, nullable=True)

    # Status workflow: draft -> verified -> posted
    status = Column(String(20), nullable=False, server_default="draft", index=True)

    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    imported_from = Column(String(100), nullable=True)  # Source system/file
    imported_at = Column(DateTime, nullable=True)

    # POS integration fields
    imported_from_pos = Column(Boolean, nullable=False, server_default="false")
    pos_sync_date = Column(DateTime, nullable=True)
    pos_transaction_count = Column(Integer, nullable=True)

    # AI review fields
    review_status = Column(String(20), nullable=True, index=True)  # null=not reviewed, 'clean'=auto-posted, 'flagged'=needs attention
    review_notes = Column(JSONB, nullable=True)  # List of issues found by AI review
    reviewed_at = Column(DateTime, nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    verified_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    posted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    posted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    area = relationship("Area", back_populates="daily_sales_summaries")
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
    line_items = relationship("SalesLineItem", back_populates="dss", cascade="all, delete-orphan")
    payments = relationship("SalesPayment", back_populates="dss", cascade="all, delete-orphan")

    creator = relationship("User", foreign_keys=[created_by])
    verifier = relationship("User", foreign_keys=[verified_by])
    poster = relationship("User", foreign_keys=[posted_by])

    def __repr__(self):
        return f"<DailySalesSummary {self.business_date} - Area {self.area_id}: ${self.net_sales}>"


class SalesLineItem(Base):
    """Detailed sales breakdown by category/item"""
    __tablename__ = "sales_line_items"

    id = Column(Integer, primary_key=True)
    dss_id = Column(Integer, ForeignKey("daily_sales_summaries.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(100), nullable=True)  # 'Food', 'Beverage', 'Alcohol'
    item_name = Column(String(200), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=True)
    gross_amount = Column(Numeric(15, 2), nullable=False)
    discount_amount = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    net_amount = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    revenue_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    dss = relationship("DailySalesSummary", back_populates="line_items")
    revenue_account = relationship("Account", foreign_keys=[revenue_account_id])

    def __repr__(self):
        return f"<SalesLineItem {self.category}: ${self.net_amount}>"


class SalesPayment(Base):
    """Payment method details for daily sales"""
    __tablename__ = "sales_payments"

    id = Column(Integer, primary_key=True)
    dss_id = Column(Integer, ForeignKey("daily_sales_summaries.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_type = Column(String(50), nullable=False)  # 'CASH', 'CREDIT_CARD', etc.
    amount = Column(Numeric(15, 2), nullable=False)
    tips = Column(Numeric(15, 2), nullable=False, server_default="0.00")
    deposit_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    processor = Column(String(100), nullable=True)  # 'Visa', 'Mastercard', 'Square'
    reference_number = Column(String(100), nullable=True)  # Batch number, etc.

    # Relationships
    dss = relationship("DailySalesSummary", back_populates="payments")
    deposit_account = relationship("Account", foreign_keys=[deposit_account_id])

    def __repr__(self):
        return f"<SalesPayment {self.payment_type}: ${self.amount}>"
