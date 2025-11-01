"""
Customer Statement Service

Generates customer account statements showing invoices, payments, and aging
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from accounting.models.customer import Customer
from accounting.models.customer_invoice import CustomerInvoice, InvoiceStatus
from accounting.models.payment import Payment, PaymentStatus
from accounting.models.journal_entry import JournalEntry, JournalEntryLine


class CustomerStatementService:
    """Generates customer account statements"""

    def __init__(self, db: Session):
        self.db = db

    def generate_statement_data(
        self,
        customer_id: int,
        start_date: date,
        end_date: date,
        include_paid: bool = True
    ) -> Dict[str, Any]:
        """
        Generate statement data for a customer

        Args:
            customer_id: Customer ID
            start_date: Statement period start date
            end_date: Statement period end date
            include_paid: Include fully paid invoices (default True)

        Returns:
            Dictionary with statement data
        """
        customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # Get beginning balance (before start_date)
        beginning_balance = self._calculate_balance_as_of(customer_id, start_date - timedelta(days=1))

        # Get transactions during period
        transactions = self._get_transactions(customer_id, start_date, end_date, include_paid)

        # Calculate ending balance
        ending_balance = self._calculate_balance_as_of(customer_id, end_date)

        # Get aging as of end_date
        aging = self._calculate_aging(customer_id, end_date)

        # Get open invoices as of end_date
        open_invoices = self._get_open_invoices(customer_id, end_date)

        return {
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'email': customer.email,
                'billing_email': customer.billing_email,
                'phone': customer.phone,
                'billing_address': customer.billing_address,
                'credit_limit': customer.credit_limit
            },
            'statement_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'balances': {
                'beginning_balance': float(beginning_balance),
                'ending_balance': float(ending_balance),
                'change': float(ending_balance - beginning_balance)
            },
            'transactions': transactions,
            'aging': aging,
            'open_invoices': open_invoices
        }

    def _calculate_balance_as_of(self, customer_id: int, as_of_date: date) -> Decimal:
        """Calculate customer balance as of a specific date"""
        invoices = self.db.query(CustomerInvoice).filter(
            CustomerInvoice.customer_id == customer_id,
            CustomerInvoice.invoice_date <= as_of_date,
            CustomerInvoice.status.in_([
                InvoiceStatus.SENT,
                InvoiceStatus.PARTIALLY_PAID,
                InvoiceStatus.OVERDUE,
                InvoiceStatus.PAID
            ])
        ).all()

        balance = Decimal('0.00')
        for invoice in invoices:
            balance += (invoice.total_amount - invoice.deposit_amount - invoice.paid_amount)

        return balance

    def _get_transactions(
        self,
        customer_id: int,
        start_date: date,
        end_date: date,
        include_paid: bool
    ) -> List[Dict[str, Any]]:
        """Get all transactions for customer during period"""
        transactions = []

        # Get invoices
        invoice_query = self.db.query(CustomerInvoice).filter(
            CustomerInvoice.customer_id == customer_id,
            CustomerInvoice.invoice_date >= start_date,
            CustomerInvoice.invoice_date <= end_date
        )

        if not include_paid:
            invoice_query = invoice_query.filter(
                CustomerInvoice.status != InvoiceStatus.PAID
            )

        invoices = invoice_query.order_by(CustomerInvoice.invoice_date).all()

        for invoice in invoices:
            transactions.append({
                'date': invoice.invoice_date.isoformat(),
                'type': 'Invoice',
                'reference': invoice.invoice_number,
                'description': invoice.description or f"Invoice {invoice.invoice_number}",
                'amount': float(invoice.total_amount),
                'balance': float(invoice.total_amount - invoice.deposit_amount - invoice.paid_amount)
            })

        # Get payments (from Payment model)
        payments = self.db.query(Payment).filter(
            Payment.customer_id == customer_id,
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date,
            Payment.status == PaymentStatus.COMPLETED
        ).order_by(Payment.payment_date).all()

        for payment in payments:
            transactions.append({
                'date': payment.payment_date.isoformat(),
                'type': 'Payment',
                'reference': payment.reference_number or f"PMT-{payment.id}",
                'description': payment.notes or "Payment received",
                'amount': float(-payment.amount),  # Negative for payment
                'balance': None  # Payments don't have a balance
            })

        # Sort all transactions by date
        transactions.sort(key=lambda x: x['date'])

        return transactions

    def _get_open_invoices(self, customer_id: int, as_of_date: date) -> List[Dict[str, Any]]:
        """Get all open invoices as of date"""
        invoices = self.db.query(CustomerInvoice).filter(
            CustomerInvoice.customer_id == customer_id,
            CustomerInvoice.invoice_date <= as_of_date,
            CustomerInvoice.status.in_([
                InvoiceStatus.SENT,
                InvoiceStatus.PARTIALLY_PAID,
                InvoiceStatus.OVERDUE
            ])
        ).order_by(CustomerInvoice.invoice_date).all()

        open_invoices = []
        for invoice in invoices:
            balance = invoice.total_amount - invoice.deposit_amount - invoice.paid_amount
            if balance > 0:
                open_invoices.append({
                    'invoice_number': invoice.invoice_number,
                    'invoice_date': invoice.invoice_date.isoformat(),
                    'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
                    'amount': float(invoice.total_amount),
                    'paid': float(invoice.paid_amount + invoice.deposit_amount),
                    'balance': float(balance),
                    'days_outstanding': (as_of_date - invoice.invoice_date).days
                })

        return open_invoices

    def _calculate_aging(self, customer_id: int, as_of_date: date) -> Dict[str, Any]:
        """Calculate aging buckets as of date"""
        invoices = self._get_open_invoices(customer_id, as_of_date)

        aging = {
            'current': Decimal('0.00'),      # 0-30 days
            'days_31_60': Decimal('0.00'),   # 31-60 days
            'days_61_90': Decimal('0.00'),   # 61-90 days
            'over_90': Decimal('0.00'),      # 90+ days
            'total': Decimal('0.00')
        }

        for invoice in invoices:
            balance = Decimal(str(invoice['balance']))
            days = invoice['days_outstanding']

            if days <= 30:
                aging['current'] += balance
            elif days <= 60:
                aging['days_31_60'] += balance
            elif days <= 90:
                aging['days_61_90'] += balance
            else:
                aging['over_90'] += balance

            aging['total'] += balance

        # Convert to float for JSON serialization
        return {
            'current': float(aging['current']),
            'days_31_60': float(aging['days_31_60']),
            'days_61_90': float(aging['days_61_90']),
            'over_90': float(aging['over_90']),
            'total': float(aging['total'])
        }

    def generate_statement_pdf(
        self,
        customer_id: int,
        start_date: date,
        end_date: date,
        include_paid: bool = True,
        output_buffer: Optional[BytesIO] = None
    ) -> BytesIO:
        """
        Generate PDF statement

        Args:
            customer_id: Customer ID
            start_date: Statement period start
            end_date: Statement period end
            include_paid: Include paid invoices
            output_buffer: Optional buffer to write to

        Returns:
            BytesIO buffer containing PDF
        """
        if output_buffer is None:
            output_buffer = BytesIO()

        # Get statement data
        data = self.generate_statement_data(customer_id, start_date, end_date, include_paid)

        # Create PDF
        doc = SimpleDocTemplate(output_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=12,
            alignment=TA_CENTER
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=8
        )

        # Title
        story.append(Paragraph("CUSTOMER ACCOUNT STATEMENT", title_style))
        story.append(Spacer(1, 0.3*inch))

        # Company and Customer Info
        customer = data['customer']
        period = data['statement_period']

        info_data = [
            ['SW Hospitality Group - Accounting', '', 'STATEMENT FOR:'],
            ['', '', customer['name']],
            ['', '', customer.get('billing_address', '') or ''],
            ['', '', ''],
            ['Statement Period:', f"{period['start_date']} to {period['end_date']}", ''],
            ['Statement Date:', end_date.isoformat(), '']
        ]

        info_table = Table(info_data, colWidths=[2.5*inch, 2*inch, 2.5*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTNAME', (2, 1), (2, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (2, 1), (2, 1), 12),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.3*inch))

        # Account Summary
        balances = data['balances']
        aging = data['aging']

        story.append(Paragraph("Account Summary", heading_style))
        summary_data = [
            ['Beginning Balance:', f"${balances['beginning_balance']:,.2f}"],
            ['Charges This Period:', f"${max(0, balances['change']):,.2f}"],
            ['Payments This Period:', f"${abs(min(0, balances['change'])):,.2f}"],
            ['Current Balance:', f"${balances['ending_balance']:,.2f}"]
        ]

        summary_table = Table(summary_data, colWidths=[4*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
            ('FONTNAME', (1, -1), (1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (1, -1), (1, -1), 12),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.2*inch))

        # Aging Summary
        story.append(Paragraph("Aging Summary", heading_style))
        aging_data = [
            ['Current (0-30)', '31-60 Days', '61-90 Days', 'Over 90 Days', 'Total'],
            [
                f"${aging['current']:,.2f}",
                f"${aging['days_31_60']:,.2f}",
                f"${aging['days_61_90']:,.2f}",
                f"${aging['over_90']:,.2f}",
                f"${aging['total']:,.2f}"
            ]
        ]

        aging_table = Table(aging_data, colWidths=[1.4*inch, 1.4*inch, 1.4*inch, 1.4*inch, 1.4*inch])
        aging_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (4, 1), (4, 1), 'Helvetica-Bold'),
        ]))
        story.append(aging_table)
        story.append(Spacer(1, 0.3*inch))

        # Transaction Detail
        if data['transactions']:
            story.append(Paragraph("Transaction Detail", heading_style))

            trans_data = [['Date', 'Type', 'Reference', 'Description', 'Amount', 'Balance']]
            for trans in data['transactions']:
                trans_data.append([
                    trans['date'],
                    trans['type'],
                    trans['reference'],
                    trans['description'][:40],  # Truncate long descriptions
                    f"${trans['amount']:,.2f}",
                    f"${trans['balance']:,.2f}" if trans['balance'] is not None else '-'
                ])

            trans_table = Table(trans_data, colWidths=[0.8*inch, 0.8*inch, 1*inch, 2.4*inch, 1*inch, 1*inch])
            trans_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (4, 0), (5, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')])
            ]))
            story.append(trans_table)

        # Build PDF
        doc.build(story)
        output_buffer.seek(0)
        return output_buffer
