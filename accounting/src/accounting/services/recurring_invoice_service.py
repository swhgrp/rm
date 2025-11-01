"""
Recurring Invoice Service

Handles automatic generation of invoices from recurring templates
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
import logging

from accounting.models.recurring_invoice import (
    RecurringInvoice,
    RecurringInvoiceLineItem,
    RecurringFrequency,
    RecurringInvoiceStatus
)
from accounting.models.customer_invoice import CustomerInvoice, InvoiceStatus, CustomerInvoiceLine
from accounting.services.email_service import EmailService
from accounting.services.invoice_pdf_service import InvoicePDFService

logger = logging.getLogger(__name__)


class RecurringInvoiceService:
    """Service for managing recurring invoices"""

    def __init__(self, db: Session):
        self.db = db

    def process_due_invoices(self) -> List[CustomerInvoice]:
        """
        Process all recurring invoices that are due

        Returns:
            List of generated invoices
        """
        # Find all active recurring invoices that are due
        due_invoices = self.db.query(RecurringInvoice).filter(
            and_(
                RecurringInvoice.status == RecurringInvoiceStatus.ACTIVE,
                RecurringInvoice.next_invoice_date <= datetime.utcnow()
            )
        ).all()

        generated_invoices = []

        for recurring_invoice in due_invoices:
            try:
                # Generate invoice from template
                invoice = self.generate_invoice_from_template(recurring_invoice)
                generated_invoices.append(invoice)

                logger.info(f"Generated invoice {invoice.invoice_number} from recurring template {recurring_invoice.id}")

            except Exception as e:
                logger.error(f"Failed to generate invoice from recurring template {recurring_invoice.id}: {str(e)}")
                continue

        return generated_invoices

    def generate_invoice_from_template(
        self,
        recurring_invoice: RecurringInvoice,
        override_date: Optional[date] = None
    ) -> CustomerInvoice:
        """
        Generate a single invoice from a recurring template

        Args:
            recurring_invoice: The recurring invoice template
            override_date: Optional date to use instead of next_invoice_date

        Returns:
            Generated CustomerInvoice
        """
        invoice_date = override_date or recurring_invoice.next_invoice_date.date()

        # Calculate due date
        due_date = invoice_date + timedelta(days=recurring_invoice.terms_days)

        # Create invoice
        invoice = CustomerInvoice(
            customer_id=recurring_invoice.customer_id,
            invoice_date=invoice_date,
            due_date=due_date,
            description=recurring_invoice.invoice_description,
            notes=recurring_invoice.notes,
            subtotal=recurring_invoice.subtotal,
            discount_percent=recurring_invoice.discount_percent,
            discount_amount=recurring_invoice.discount_amount,
            tax_rate=recurring_invoice.tax_rate,
            tax_amount=recurring_invoice.tax_amount,
            total_amount=recurring_invoice.total_amount,
            status=InvoiceStatus.DRAFT,
            recurring_invoice_id=recurring_invoice.id,
            created_by=recurring_invoice.created_by
        )

        self.db.add(invoice)
        self.db.flush()  # Get the invoice ID

        # Copy line items
        for template_line in recurring_invoice.line_items:
            line_item = CustomerInvoiceLine(
                invoice_id=invoice.id,
                line_number=template_line.line_number,
                description=template_line.description,
                quantity=template_line.quantity,
                unit_price=template_line.unit_price,
                amount=template_line.amount,
                account_id=template_line.account_id
            )
            self.db.add(line_item)

        # Update recurring invoice
        recurring_invoice.invoices_generated += 1
        recurring_invoice.last_generated_at = datetime.utcnow()
        recurring_invoice.next_invoice_date = self._calculate_next_invoice_date(recurring_invoice)

        # Check if we should mark as completed
        if recurring_invoice.end_date and recurring_invoice.next_invoice_date > recurring_invoice.end_date:
            recurring_invoice.status = RecurringInvoiceStatus.COMPLETED

        self.db.commit()
        self.db.refresh(invoice)

        # Send invoice if auto_send_email is enabled
        if recurring_invoice.auto_send_email:
            try:
                invoice.status = InvoiceStatus.SENT
                self.db.commit()

                self._send_invoice_email(invoice, recurring_invoice)
            except Exception as e:
                logger.error(f"Failed to send email for invoice {invoice.id}: {str(e)}")

        return invoice

    def _calculate_next_invoice_date(self, recurring_invoice: RecurringInvoice) -> datetime:
        """Calculate the next invoice date based on frequency"""
        current_date = recurring_invoice.next_invoice_date

        if recurring_invoice.frequency == RecurringFrequency.WEEKLY:
            return current_date + timedelta(weeks=1)
        elif recurring_invoice.frequency == RecurringFrequency.BIWEEKLY:
            return current_date + timedelta(weeks=2)
        elif recurring_invoice.frequency == RecurringFrequency.MONTHLY:
            # Add one month (roughly 30 days, but handle month-end properly)
            if current_date.month == 12:
                return current_date.replace(year=current_date.year + 1, month=1)
            else:
                return current_date.replace(month=current_date.month + 1)
        elif recurring_invoice.frequency == RecurringFrequency.QUARTERLY:
            # Add 3 months
            new_month = current_date.month + 3
            new_year = current_date.year
            if new_month > 12:
                new_month -= 12
                new_year += 1
            return current_date.replace(year=new_year, month=new_month)
        elif recurring_invoice.frequency == RecurringFrequency.ANNUALLY:
            return current_date.replace(year=current_date.year + 1)

        return current_date

    def _send_invoice_email(self, invoice: CustomerInvoice, recurring_invoice: RecurringInvoice):
        """Send invoice email"""
        email_service = EmailService(self.db)
        pdf_service = InvoicePDFService()

        # Get customer
        customer = invoice.customer

        # Determine recipient email
        to_email = recurring_invoice.email_to or customer.billing_email or customer.email
        if not to_email:
            logger.warning(f"No email address for customer {customer.id}, skipping email")
            return

        # Parse CC emails
        cc_emails = []
        if recurring_invoice.email_cc:
            cc_emails = [email.strip() for email in recurring_invoice.email_cc.split(',')]

        # Generate PDF
        pdf_buffer = pdf_service.generate_invoice_pdf(
            invoice=invoice,
            customer=customer,
            line_items=invoice.line_items
        )

        # Send email
        success = email_service.send_invoice_email(
            to_email=to_email,
            customer_name=customer.name,
            invoice_number=invoice.invoice_number,
            invoice_amount=float(invoice.total_amount),
            due_date=invoice.due_date.isoformat(),
            pdf_buffer=pdf_buffer,
            cc_emails=cc_emails if cc_emails else None,
            additional_message="This is an automatically generated recurring invoice."
        )

        if success:
            logger.info(f"Sent invoice email for {invoice.invoice_number} to {to_email}")
        else:
            logger.error(f"Failed to send invoice email for {invoice.invoice_number}")

    def calculate_totals(self, recurring_invoice: RecurringInvoice):
        """Calculate and update totals for recurring invoice"""
        # Calculate subtotal from line items
        subtotal = Decimal("0.00")
        for line_item in recurring_invoice.line_items:
            line_item.amount = line_item.quantity * line_item.unit_price
            subtotal += line_item.amount

        recurring_invoice.subtotal = subtotal

        # Calculate discount
        if recurring_invoice.discount_percent > 0:
            recurring_invoice.discount_amount = (subtotal * recurring_invoice.discount_percent / 100).quantize(Decimal("0.01"))
        else:
            recurring_invoice.discount_amount = Decimal("0.00")

        # Calculate taxable amount
        taxable_amount = subtotal - recurring_invoice.discount_amount

        # Calculate tax
        if recurring_invoice.tax_rate > 0:
            recurring_invoice.tax_amount = (taxable_amount * recurring_invoice.tax_rate / 100).quantize(Decimal("0.01"))
        else:
            recurring_invoice.tax_amount = Decimal("0.00")

        # Calculate total
        recurring_invoice.total_amount = taxable_amount + recurring_invoice.tax_amount

        return recurring_invoice
