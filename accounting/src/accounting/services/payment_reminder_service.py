"""
Payment Reminder Service

Handles automated reminders for overdue invoices
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from accounting.models.customer_invoice import CustomerInvoice, InvoiceStatus
from accounting.models.customer import Customer
from accounting.models.payment_reminder import PaymentReminder
from accounting.services.email_service import EmailService
from accounting.services.invoice_pdf_service import InvoicePDFService

logger = logging.getLogger(__name__)


class PaymentReminderService:
    """Service for managing payment reminders"""

    def __init__(self, db: Session):
        self.db = db
        self._load_settings()

    def _load_settings(self):
        """Load reminder settings from database"""
        settings_query = text("""
            SELECT setting_key, setting_value
            FROM system_settings
            WHERE setting_key IN (
                'reminder_enabled',
                'reminder_days_1',
                'reminder_days_2',
                'reminder_days_3',
                'reminder_email_from',
                'reminder_subject_template',
                'reminder_min_amount'
            )
        """)

        results = self.db.execute(settings_query).fetchall()
        settings = {row[0]: row[1] for row in results}

        self.enabled = settings.get('reminder_enabled', 'true').lower() == 'true'
        self.reminder_days = [
            int(settings.get('reminder_days_1', '7')),
            int(settings.get('reminder_days_2', '14')),
            int(settings.get('reminder_days_3', '30'))
        ]
        self.email_from = settings.get('reminder_email_from', '')
        self.subject_template = settings.get('reminder_subject_template', 'Payment Reminder: Invoice {invoice_number}')
        self.min_amount = Decimal(settings.get('reminder_min_amount', '0.00'))

    def process_overdue_invoices(self) -> Dict[str, Any]:
        """
        Process all overdue invoices and send reminders

        Returns:
            Dictionary with processing statistics
        """
        if not self.enabled:
            logger.info("Payment reminders are disabled")
            return {
                'enabled': False,
                'processed': 0,
                'reminders_sent': 0,
                'errors': 0
            }

        today = date.today()
        stats = {
            'enabled': True,
            'processed': 0,
            'reminders_sent': 0,
            'errors': 0,
            'skipped': 0
        }

        # Find all overdue invoices
        overdue_invoices = self.db.query(CustomerInvoice).filter(
            and_(
                CustomerInvoice.status.in_([
                    InvoiceStatus.SENT,
                    InvoiceStatus.PARTIALLY_PAID,
                    InvoiceStatus.OVERDUE
                ]),
                CustomerInvoice.due_date < today
            )
        ).all()

        logger.info(f"Found {len(overdue_invoices)} overdue invoices to process")

        for invoice in overdue_invoices:
            stats['processed'] += 1

            try:
                # Calculate balance due
                balance_due = invoice.total_amount - invoice.deposit_amount - invoice.paid_amount

                # Skip if below minimum amount
                if balance_due < self.min_amount:
                    stats['skipped'] += 1
                    continue

                # Calculate days overdue
                days_overdue = (today - invoice.due_date).days

                # Determine which reminder to send
                reminder_number = self._get_reminder_number(invoice, days_overdue)

                if reminder_number:
                    success = self._send_reminder(invoice, reminder_number, days_overdue, balance_due)
                    if success:
                        stats['reminders_sent'] += 1
                    else:
                        stats['errors'] += 1
                else:
                    stats['skipped'] += 1

            except Exception as e:
                logger.error(f"Error processing invoice {invoice.id}: {str(e)}")
                stats['errors'] += 1
                continue

        logger.info(f"Payment reminder processing complete: {stats}")
        return stats

    def _get_reminder_number(self, invoice: CustomerInvoice, days_overdue: int) -> Optional[int]:
        """
        Determine which reminder number to send based on days overdue

        Returns:
            Reminder number (1, 2, or 3) or None if no reminder should be sent
        """
        # Get reminder history for this invoice
        reminders = self.db.query(PaymentReminder).filter(
            PaymentReminder.invoice_id == invoice.id
        ).order_by(PaymentReminder.reminder_number.desc()).all()

        # Determine which reminders have been sent
        sent_reminders = set(r.reminder_number for r in reminders)

        # Check each reminder threshold
        for i, threshold in enumerate(self.reminder_days, start=1):
            if days_overdue >= threshold and i not in sent_reminders:
                # Check if we've recently sent this reminder (within last 24 hours)
                recent = [r for r in reminders if r.reminder_number == i]
                if recent:
                    last_sent = recent[0].sent_at
                    if (get_now() - last_sent).days < 1:
                        logger.debug(f"Skipping reminder {i} for invoice {invoice.id} - recently sent")
                        return None

                return i

        return None

    def _send_reminder(
        self,
        invoice: CustomerInvoice,
        reminder_number: int,
        days_overdue: int,
        balance_due: Decimal
    ) -> bool:
        """
        Send a payment reminder email

        Args:
            invoice: Invoice to send reminder for
            reminder_number: Which reminder (1, 2, or 3)
            days_overdue: Number of days overdue
            balance_due: Amount still owed

        Returns:
            True if email sent successfully
        """
        customer = invoice.customer

        # Determine recipient email
        to_email = customer.billing_email or customer.email
        if not to_email:
            logger.warning(f"No email address for customer {customer.id}, skipping reminder")
            return False

        # Generate email content
        subject = self.subject_template.format(
            invoice_number=invoice.invoice_number,
            customer_name=customer.customer_name,
            days_overdue=days_overdue
        )

        # Create email body based on reminder number
        if reminder_number == 1:
            urgency = "friendly"
            message = f"""
            <p>This is a friendly reminder that Invoice <strong>{invoice.invoice_number}</strong> is now {days_overdue} days overdue.</p>
            <p>We would appreciate your prompt attention to this matter.</p>
            """
        elif reminder_number == 2:
            urgency = "second"
            message = f"""
            <p>This is our second reminder that Invoice <strong>{invoice.invoice_number}</strong> is now {days_overdue} days overdue.</p>
            <p>Please remit payment at your earliest convenience to avoid any service interruption.</p>
            """
        else:  # reminder_number == 3
            urgency = "final"
            message = f"""
            <p>This is our <strong>final reminder</strong> that Invoice <strong>{invoice.invoice_number}</strong> is now {days_overdue} days overdue.</p>
            <p>Immediate payment is required. If payment is not received within 5 business days, we may need to suspend services and pursue collection activities.</p>
            """

        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #dc2626;">Payment Reminder - {urgency.title()}</h2>

                <p>Dear {customer.contact_name or customer.customer_name},</p>

                {message}

                <div style="background-color: #fee; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Invoice Number:</strong> {invoice.invoice_number}</p>
                    <p style="margin: 5px 0;"><strong>Invoice Date:</strong> {invoice.invoice_date.strftime('%B %d, %Y')}</p>
                    <p style="margin: 5px 0;"><strong>Due Date:</strong> {invoice.due_date.strftime('%B %d, %Y')}</p>
                    <p style="margin: 5px 0;"><strong>Days Overdue:</strong> {days_overdue}</p>
                    <p style="margin: 5px 0; font-size: 18px;"><strong>Amount Due:</strong> <span style="color: #dc2626;">${balance_due:,.2f}</span></p>
                </div>

                <p>If you have already sent payment, please disregard this notice. If you have any questions about this invoice, please contact us immediately.</p>

                <p>Thank you for your prompt attention to this matter.</p>

                <p style="margin-top: 30px;">
                    Best regards,<br>
                    <strong>SW Hospitality Group - Accounting</strong>
                </p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="font-size: 12px; color: #666;">
                    This is an automated reminder. Please do not reply to this email.
                </p>
            </div>
        </body>
        </html>
        """

        # Send email with invoice PDF attached
        try:
            email_service = EmailService(self.db)
            pdf_service = InvoicePDFService()

            # Generate PDF
            pdf_buffer = pdf_service.generate_invoice_pdf(
                invoice=invoice,
                customer=customer,
                line_items=invoice.line_items
            )

            # Override from email if configured
            if self.email_from:
                email_service.from_email = self.email_from

            # Send email
            success = email_service.send_email(
                to_email=to_email,
                subject=subject,
                html_body=email_body,
                pdf_buffer=pdf_buffer,
                pdf_filename=f"Invoice_{invoice.invoice_number}.pdf"
            )

            # Log reminder
            reminder = PaymentReminder(
                invoice_id=invoice.id,
                reminder_number=reminder_number,
                sent_at=get_now(),
                sent_to=to_email,
                days_overdue=days_overdue,
                amount_due=balance_due,
                email_subject=subject,
                email_body=email_body,
                email_status='sent' if success else 'failed',
                error_message=None if success else 'Email sending failed'
            )
            self.db.add(reminder)

            # Update invoice status to OVERDUE if not already
            if invoice.status != InvoiceStatus.OVERDUE:
                invoice.status = InvoiceStatus.OVERDUE

            self.db.commit()

            if success:
                logger.info(f"Sent reminder {reminder_number} for invoice {invoice.invoice_number} to {to_email}")
            else:
                logger.error(f"Failed to send reminder {reminder_number} for invoice {invoice.invoice_number}")

            return success

        except Exception as e:
            logger.error(f"Error sending reminder for invoice {invoice.id}: {str(e)}")

            # Log failed reminder
            try:
                reminder = PaymentReminder(
                    invoice_id=invoice.id,
                    reminder_number=reminder_number,
                    sent_at=get_now(),
                    sent_to=to_email,
                    days_overdue=days_overdue,
                    amount_due=balance_due,
                    email_subject=subject,
                    email_body=email_body,
                    email_status='failed',
                    error_message=str(e)
                )
                self.db.add(reminder)
                self.db.commit()
            except Exception as log_error:
                logger.error(f"Failed to log reminder error: {str(log_error)}")

            return False

    def get_reminder_history(self, invoice_id: int) -> List[Dict[str, Any]]:
        """Get reminder history for an invoice"""
        reminders = self.db.query(PaymentReminder).filter(
            PaymentReminder.invoice_id == invoice_id
        ).order_by(PaymentReminder.sent_at.desc()).all()

        return [
            {
                'id': r.id,
                'reminder_number': r.reminder_number,
                'sent_at': r.sent_at.isoformat(),
                'sent_to': r.sent_to,
                'days_overdue': r.days_overdue,
                'amount_due': float(r.amount_due),
                'email_status': r.email_status,
                'error_message': r.error_message
            }
            for r in reminders
        ]

    def get_reminder_stats(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
        """Get reminder statistics for a date range"""
        query = self.db.query(PaymentReminder)

        if start_date:
            query = query.filter(PaymentReminder.sent_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.filter(PaymentReminder.sent_at <= datetime.combine(end_date, datetime.max.time()))

        reminders = query.all()

        stats = {
            'total_reminders': len(reminders),
            'by_number': {
                1: len([r for r in reminders if r.reminder_number == 1]),
                2: len([r for r in reminders if r.reminder_number == 2]),
                3: len([r for r in reminders if r.reminder_number == 3])
            },
            'by_status': {
                'sent': len([r for r in reminders if r.email_status == 'sent']),
                'failed': len([r for r in reminders if r.email_status == 'failed']),
                'bounced': len([r for r in reminders if r.email_status == 'bounced'])
            },
            'total_amount': float(sum(r.amount_due for r in reminders))
        }

        return stats
