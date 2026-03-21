"""
POS Integration Models
Handles Point of Sale system configurations and sales data
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from accounting.db.database import Base


class POSConfiguration(Base):
    """POS system configuration per location"""
    __tablename__ = "pos_configurations"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="clover")  # clover, square, toast, manual
    merchant_id = Column(String(255))
    access_token = Column(Text)  # Should be encrypted in production
    api_environment = Column(String(20), nullable=False, default="production")  # sandbox or production
    auto_sync_enabled = Column(Boolean, nullable=False, default=False)
    sync_time = Column(String(5), nullable=False, default="02:00")  # HH:MM format for daily sync time
    last_sync_date = Column(DateTime)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    area = relationship("Area", back_populates="pos_configuration")
    daily_sales_cache = relationship(
        "POSDailySalesCache",
        foreign_keys="[POSDailySalesCache.area_id]",
        primaryjoin="POSConfiguration.area_id == POSDailySalesCache.area_id",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<POSConfiguration(area_id={self.area_id}, provider={self.provider}, merchant_id={self.merchant_id})>"


class POSDailySalesCache(Base):
    """Cached daily sales summaries from POS system"""
    __tablename__ = "pos_daily_sales_cache"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="clover")

    # Aggregated totals
    total_sales = Column(Numeric(12, 2), nullable=False, default=0)  # Subtotal (before tax)
    total_tax = Column(Numeric(12, 2), nullable=False, default=0)
    total_tips = Column(Numeric(12, 2), nullable=False, default=0)
    total_discounts = Column(Numeric(12, 2), nullable=False, default=0)
    total_refunds = Column(Numeric(12, 2), nullable=False, default=0)  # Total refunded amount
    gross_sales = Column(Numeric(12, 2), nullable=False, default=0)  # Grand total (sales + tax + tips)
    transaction_count = Column(Integer, nullable=False, default=0)

    # JSON breakdown fields
    order_types = Column(JSONB)  # {"dine-in": 1200.50, "takeout": 800.00, "delivery": 300.00}
    payment_methods = Column(JSONB)  # {"credit_card": 1800.00, "cash": 500.50}
    categories = Column(JSONB)  # {"Food": 1500.00, "Beverages": 800.50}
    discounts = Column(JSONB)  # {"Employee Discount": 50.00, "Happy Hour": 100.00}
    refunds = Column(JSONB)  # {"Merchandise": 25.00, "Food": 10.00} - refunds by category

    # Deposit calculation fields
    card_deposit = Column(Numeric(12, 2))  # Card payments (amount + tips - card refunds)
    cash_tips_paid = Column(Numeric(12, 2), default=0)  # Cash tips paid out to employees
    cash_payouts = Column(Numeric(12, 2), default=0)  # Cash payouts/adjustments (money taken from drawer)
    expected_cash_deposit = Column(Numeric(12, 2))  # Cash Sales - Cash Tips - Payouts
    payout_breakdown = Column(JSONB)  # Details of each payout: [{"amount": 50.00, "note": "Bank run", "employee": "John"}]

    # Metadata
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    raw_summary = Column(JSONB)  # Store complete POS API response for audit
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    area = relationship("Area", overlaps="daily_sales_cache")

    def __repr__(self):
        return f"<POSDailySalesCache(area_id={self.area_id}, date={self.sale_date}, sales={self.total_sales})>"


class POSCategoryGLMapping(Base):
    """Mapping from POS categories to GL revenue accounts"""
    __tablename__ = "pos_category_gl_mappings"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), index=True)
    pos_category = Column(String(255), nullable=False)  # e.g., "Food", "Beverages", "Alcohol"
    revenue_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    tax_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))  # Sales tax payable account
    discount_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"))  # Contra-revenue account for discounts on this category
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    area = relationship("Area")
    revenue_account = relationship("Account", foreign_keys=[revenue_account_id])
    tax_account = relationship("Account", foreign_keys=[tax_account_id])
    discount_account = relationship("Account", foreign_keys=[discount_account_id])

    def __repr__(self):
        return f"<POSCategoryGLMapping(category={self.pos_category}, revenue_account_id={self.revenue_account_id})>"


class POSDiscountGLMapping(Base):
    """Mapping from POS discounts to GL accounts.

    When is_override=True, this discount always posts to the mapped account
    regardless of which sales category the discounted item belongs to.
    (e.g., Staff Meal → 4102 Employee Meals, Waste → 4818)

    When is_override=False (default), category-based routing is used instead
    and the category's discount_account_id determines the GL account.
    These mappings serve as fallback for old data without category prefixes.
    """
    __tablename__ = "pos_discount_gl_mappings"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), index=True)
    pos_discount_name = Column(String(255), nullable=False)  # e.g., "Employee Discount", "Happy Hour"
    discount_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)  # Contra-revenue or expense account
    is_override = Column(Boolean, nullable=False, default=False)  # True = always use this account, False = use category routing
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    area = relationship("Area")
    discount_account = relationship("Account", foreign_keys=[discount_account_id])

    def __repr__(self):
        return f"<POSDiscountGLMapping(discount={self.pos_discount_name}, account_id={self.discount_account_id})>"


class POSPaymentGLMapping(Base):
    """Mapping from POS payment types to GL deposit accounts"""
    __tablename__ = "pos_payment_gl_mappings"

    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="CASCADE"), index=True)
    pos_payment_type = Column(String(255), nullable=False)  # e.g., "CASH", "CREDIT_CARD", "GIFT_CARD"
    deposit_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)  # Asset account (Cash, Bank)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    area = relationship("Area")
    deposit_account = relationship("Account", foreign_keys=[deposit_account_id])

    def __repr__(self):
        return f"<POSPaymentGLMapping(payment={self.pos_payment_type}, account_id={self.deposit_account_id})>"
