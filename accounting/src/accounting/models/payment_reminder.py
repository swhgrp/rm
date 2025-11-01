"""
Payment Reminder Model

Tracks history of payment reminder emails sent for overdue invoices
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
from accounting.db.database import Base


class PaymentReminder(Base):
    """
    Payment reminder log

    Tracks when reminder emails are sent for overdue invoices
    """
    __tablename__ = "payment_reminders"

    id = Column(Integer, primary_key=True, index=True)

    # Invoice reference
    invoice_id = Column(Integer, ForeignKey("customer_invoices.id", ondelete="CASCADE"), nullable=False)

    # Reminder details
    reminder_number = Column(Integer, nullable=False)  # 1, 2, or 3
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sent_to = Column(String(255), nullable=False)
    days_overdue = Column(Integer, nullable=False)
    amount_due = Column(Numeric(10, 2), nullable=False)

    # Email content
    email_subject = Column(Text, nullable=True)
    email_body = Column(Text, nullable=True)

    # Status
    email_status = Column(String(20), nullable=False, default='sent')  # sent, failed, bounced
    error_message = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    invoice = relationship("CustomerInvoice")

    def __repr__(self):
        return f"<PaymentReminder {self.id}: Invoice {self.invoice_id} - Reminder {self.reminder_number}>"
