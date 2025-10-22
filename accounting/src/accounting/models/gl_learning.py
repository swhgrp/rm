"""Models for GL learning and intelligent suggestions"""
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import relationship
from accounting.db.database import Base
from decimal import Decimal


class VendorGLMapping(Base):
    """
    Tracks vendor-to-GL account mappings learned from user behavior.

    When a user assigns a transaction from a vendor to a GL account,
    we record it here. Over time, we learn which GL accounts are typically
    used for each vendor.
    """
    __tablename__ = "vendor_gl_mappings"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    # Usage statistics
    times_used = Column(Integer, nullable=False, default=1)
    times_accepted = Column(Integer, nullable=False, default=0)  # User confirmed suggestion
    times_rejected = Column(Integer, nullable=False, default=0)  # User chose different GL

    # Amount tracking (Phase 2)
    min_amount = Column(Numeric(15, 2), nullable=True)
    max_amount = Column(Numeric(15, 2), nullable=True)
    avg_amount = Column(Numeric(15, 2), nullable=True)

    # Metadata
    last_used_date = Column(Date, nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=True, index=True)  # 0-100%

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    vendor = relationship("Vendor", back_populates="gl_mappings")
    account = relationship("Account")

    def calculate_confidence(self):
        """Calculate confidence score based on acceptance rate"""
        total_decisions = self.times_accepted + self.times_rejected
        if total_decisions == 0:
            # No explicit decisions yet, use usage count as indicator
            # First use: 50%, 2+ uses: 70%, 5+ uses: 80%
            if self.times_used >= 5:
                return 80.0
            elif self.times_used >= 2:
                return 70.0
            else:
                return 50.0

        # Calculate acceptance rate
        acceptance_rate = (self.times_accepted / total_decisions) * 100

        # Boost confidence if used many times
        usage_boost = min(self.times_used * 2, 20)  # Max 20% boost

        return min(acceptance_rate + usage_boost, 100.0)


class DescriptionPatternMapping(Base):
    """
    Tracks description patterns to GL account mappings.

    For transactions without recognized vendors, we extract patterns
    from descriptions (keywords, prefixes, etc.) and learn which GL
    accounts are typically used for each pattern.
    """
    __tablename__ = "description_pattern_mappings"

    id = Column(Integer, primary_key=True, index=True)
    pattern = Column(String(255), nullable=False, index=True)
    pattern_type = Column(String(50), nullable=False, default='keyword')  # keyword, prefix, suffix, regex
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)

    # Usage statistics
    times_used = Column(Integer, nullable=False, default=1)
    times_accepted = Column(Integer, nullable=False, default=0)
    times_rejected = Column(Integer, nullable=False, default=0)

    # Amount tracking (Phase 2)
    min_amount = Column(Numeric(15, 2), nullable=True)
    max_amount = Column(Numeric(15, 2), nullable=True)
    avg_amount = Column(Numeric(15, 2), nullable=True)

    # Metadata
    confidence_score = Column(Numeric(5, 2), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    account = relationship("Account")

    def calculate_confidence(self):
        """Calculate confidence score based on acceptance rate"""
        total_decisions = self.times_accepted + self.times_rejected
        if total_decisions == 0:
            # Pattern matches get lower initial confidence than vendor matches
            # First use: 30%, 2+ uses: 50%, 5+ uses: 60%
            if self.times_used >= 5:
                return 60.0
            elif self.times_used >= 2:
                return 50.0
            else:
                return 30.0

        # Calculate acceptance rate
        acceptance_rate = (self.times_accepted / total_decisions) * 100

        # Smaller usage boost for patterns
        usage_boost = min(self.times_used * 1, 10)  # Max 10% boost

        return min(acceptance_rate + usage_boost, 100.0)


class RecurringTransactionPattern(Base):
    """
    Tracks recurring transaction patterns (Phase 2).

    Identifies monthly recurring transactions like:
    - Rent payments
    - Utility bills
    - Subscriptions
    - Regular vendor payments

    Uses frequency and amount consistency to predict future transactions.
    """
    __tablename__ = "recurring_transaction_patterns"

    id = Column(Integer, primary_key=True, index=True)
    description_pattern = Column(String(255), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    # Amount tracking
    expected_amount = Column(Numeric(15, 2), nullable=True)
    amount_variance = Column(Numeric(15, 2), nullable=False, default=0.00)  # Acceptable +/- variance

    # Frequency tracking
    frequency_days = Column(Integer, nullable=True)  # Expected days between occurrences (e.g., 30 for monthly)
    last_occurrence_date = Column(Date, nullable=True)
    next_expected_date = Column(Date, nullable=True)
    occurrence_count = Column(Integer, nullable=False, default=0)

    # Confidence and status
    confidence_score = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    vendor = relationship("Vendor")
    account = relationship("Account")

    def calculate_confidence(self):
        """Calculate confidence based on consistency of recurrence"""
        if self.occurrence_count < 2:
            return 30.0  # Not enough data

        # Base confidence on number of occurrences
        base_confidence = min(40 + (self.occurrence_count * 10), 90)

        # Bonus if amount is consistent
        if self.expected_amount and self.amount_variance:
            variance_pct = (abs(self.amount_variance) / abs(self.expected_amount)) * 100
            if variance_pct < 5:  # Less than 5% variance
                base_confidence += 10

        return min(base_confidence, 100.0)

    def is_due_soon(self, check_date=None):
        """Check if this recurring transaction is due soon (within 3 days)"""
        if not self.next_expected_date:
            return False

        from datetime import date, timedelta
        check_date = check_date or date.today()

        # Due if expected date is within next 3 days
        return self.next_expected_date <= (check_date + timedelta(days=3))
