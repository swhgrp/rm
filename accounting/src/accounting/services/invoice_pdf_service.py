"""
Customer Invoice PDF Generator using ReportLab

Generates professional PDF invoices for Accounts Receivable
"""
from io import BytesIO
from datetime import date
from decimal import Decimal
from typing import Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import logging

logger = logging.getLogger(__name__)


class InvoicePDFService:
    """Generate PDF invoices for customers"""

    def __init__(self, company_name: str = "SW Hospitality Group"):
        self.company_name = company_name
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles for invoices"""
        # Company name style
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=4,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))

        # Invoice title style
        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=12,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold'
        ))

        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=6,
            spaceBefore=6,
            fontName='Helvetica-Bold'
        ))

        # Normal text style
        self.styles.add(ParagraphStyle(
            name='InvoiceText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            fontName='Helvetica'
        ))

        # Small text style
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#666666'),
            fontName='Helvetica'
        ))

        # Right-aligned number style
        self.styles.add(ParagraphStyle(
            name='NumberRight',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
            fontName='Helvetica'
        ))

        # Bold text style
        self.styles.add(ParagraphStyle(
            name='BoldText',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold'
        ))

    def generate_invoice_pdf(
        self,
        invoice,
        customer,
        line_items: list,
        output_buffer: Optional[BytesIO] = None
    ) -> BytesIO:
        """
        Generate a professional PDF invoice

        Args:
            invoice: CustomerInvoice object
            customer: Customer object
            line_items: List of CustomerInvoiceLine objects
            output_buffer: Optional BytesIO buffer to write to

        Returns:
            BytesIO buffer containing the PDF
        """
        if output_buffer is None:
            output_buffer = BytesIO()

        # Create the PDF document
        doc = SimpleDocTemplate(
            output_buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Container for the 'Flowable' objects
        elements = []

        # Build header with company info and invoice title
        header_data = [[
            Paragraph(self.company_name, self.styles['CompanyName']),
            Paragraph("INVOICE", self.styles['InvoiceTitle'])
        ]]

        header_table = Table(header_data, colWidths=[4*inch, 2.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 0.2*inch))

        # Invoice details and customer info side by side
        invoice_details_text = f"""
        <b>Invoice Number:</b> {invoice.invoice_number}<br/>
        <b>Invoice Date:</b> {invoice.invoice_date.strftime('%B %d, %Y')}<br/>
        <b>Due Date:</b> {invoice.due_date.strftime('%B %d, %Y')}<br/>
        """

        if invoice.po_number:
            invoice_details_text += f"<b>PO Number:</b> {invoice.po_number}<br/>"

        if invoice.event_date:
            invoice_details_text += f"<b>Event Date:</b> {invoice.event_date.strftime('%B %d, %Y')}<br/>"

        # Customer address
        customer_address = f"""
        <b>Bill To:</b><br/>
        {customer.customer_name}<br/>
        """

        if customer.contact_name:
            customer_address += f"{customer.contact_name}<br/>"

        if customer.address_line1:
            customer_address += f"{customer.address_line1}<br/>"

        if customer.address_line2:
            customer_address += f"{customer.address_line2}<br/>"

        # City, State ZIP
        city_state_zip = []
        if customer.city:
            city_state_zip.append(customer.city)
        if customer.state:
            city_state_zip.append(customer.state)
        if customer.zip_code:
            city_state_zip.append(customer.zip_code)

        if city_state_zip:
            customer_address += f"{', '.join(city_state_zip)}<br/>"

        if customer.email:
            customer_address += f"<b>Email:</b> {customer.email}<br/>"

        if customer.phone:
            customer_address += f"<b>Phone:</b> {customer.phone}"

        info_data = [[
            Paragraph(customer_address, self.styles['InvoiceText']),
            Paragraph(invoice_details_text, self.styles['InvoiceText'])
        ]]

        info_table = Table(info_data, colWidths=[3.25*inch, 3.25*inch])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.3*inch))

        # Event details if applicable
        if invoice.event_type or invoice.event_location or invoice.guest_count:
            event_info = "<b>Event Details:</b><br/>"
            if invoice.event_type:
                event_info += f"Type: {invoice.event_type}<br/>"
            if invoice.event_location:
                event_info += f"Location: {invoice.event_location}<br/>"
            if invoice.guest_count:
                event_info += f"Guest Count: {invoice.guest_count}"

            elements.append(Paragraph(event_info, self.styles['InvoiceText']))
            elements.append(Spacer(1, 0.2*inch))

        # Line items table
        line_items_data = [[
            Paragraph("<b>Description</b>", self.styles['BoldText']),
            Paragraph("<b>Qty</b>", self.styles['BoldText']),
            Paragraph("<b>Unit Price</b>", self.styles['BoldText']),
            Paragraph("<b>Amount</b>", self.styles['BoldText'])
        ]]

        for line in line_items:
            description = line.description or f"Account {line.account_id}"

            line_items_data.append([
                Paragraph(description, self.styles['InvoiceText']),
                Paragraph(f"{float(line.quantity):.2f}", self.styles['NumberRight']),
                Paragraph(f"${float(line.unit_price):,.2f}", self.styles['NumberRight']),
                Paragraph(f"${float(line.amount):,.2f}", self.styles['NumberRight'])
            ])

            # Add discount if applicable
            if line.discount_amount and line.discount_amount > 0:
                discount_desc = f"  Discount ({float(line.discount_percentage)}%)" if line.discount_percentage else "  Discount"
                line_items_data.append([
                    Paragraph(discount_desc, self.styles['InvoiceText']),
                    '',
                    '',
                    Paragraph(f"-${float(line.discount_amount):,.2f}", self.styles['NumberRight'])
                ])

        # Line items table styling
        line_items_table = Table(line_items_data, colWidths=[3.5*inch, 0.75*inch, 1*inch, 1.25*inch])
        line_items_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            # Grid
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#d1d5db')),
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ]))
        elements.append(line_items_table)
        elements.append(Spacer(1, 0.2*inch))

        # Totals section
        totals_data = []

        # Subtotal
        totals_data.append([
            Paragraph("Subtotal:", self.styles['InvoiceText']),
            Paragraph(f"${float(invoice.subtotal):,.2f}", self.styles['NumberRight'])
        ])

        # Discount
        if invoice.discount_amount and invoice.discount_amount > 0:
            totals_data.append([
                Paragraph("Discount:", self.styles['InvoiceText']),
                Paragraph(f"-${float(invoice.discount_amount):,.2f}", self.styles['NumberRight'])
            ])

        # Tax
        if invoice.tax_amount and invoice.tax_amount > 0:
            tax_label = f"Tax ({float(invoice.tax_rate)}%):" if invoice.tax_rate else "Tax:"
            totals_data.append([
                Paragraph(tax_label, self.styles['InvoiceText']),
                Paragraph(f"${float(invoice.tax_amount):,.2f}", self.styles['NumberRight'])
            ])
        elif invoice.is_tax_exempt:
            totals_data.append([
                Paragraph("Tax:", self.styles['InvoiceText']),
                Paragraph("Tax Exempt", self.styles['InvoiceText'])
            ])

        # Total
        totals_data.append([
            Paragraph("<b>Total Amount:</b>", self.styles['BoldText']),
            Paragraph(f"<b>${float(invoice.total_amount):,.2f}</b>", self.styles['BoldText'])
        ])

        # Deposit
        if invoice.deposit_amount and invoice.deposit_amount > 0:
            totals_data.append([
                Paragraph("Deposit/Prepayment:", self.styles['InvoiceText']),
                Paragraph(f"-${float(invoice.deposit_amount):,.2f}", self.styles['NumberRight'])
            ])

        # Payments
        if invoice.paid_amount and invoice.paid_amount > 0:
            totals_data.append([
                Paragraph("Payments:", self.styles['InvoiceText']),
                Paragraph(f"-${float(invoice.paid_amount):,.2f}", self.styles['NumberRight'])
            ])

        # Balance Due
        balance_due = invoice.total_amount - invoice.deposit_amount - invoice.paid_amount
        if balance_due > 0:
            totals_data.append([
                Paragraph("<b>Balance Due:</b>", self.styles['BoldText']),
                Paragraph(f"<b>${float(balance_due):,.2f}</b>", self.styles['BoldText'])
            ])
        else:
            totals_data.append([
                Paragraph("<b>Balance Due:</b>", self.styles['BoldText']),
                Paragraph("<b>PAID</b>", self.styles['BoldText'])
            ])

        # Create totals table aligned to right
        totals_table = Table(totals_data, colWidths=[1.5*inch, 1.25*inch])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('LINEABOVE', (0, -2), (-1, -2), 1, colors.HexColor('#d1d5db')),
        ]))

        # Wrap totals table in a larger table to right-align it
        totals_wrapper = Table([[totals_table]], colWidths=[6.5*inch])
        totals_wrapper.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(totals_wrapper)
        elements.append(Spacer(1, 0.3*inch))

        # Payment terms
        if customer.payment_terms:
            elements.append(Paragraph(f"<b>Payment Terms:</b> {customer.payment_terms}", self.styles['InvoiceText']))
            elements.append(Spacer(1, 0.1*inch))

        # Notes
        if invoice.notes:
            elements.append(Paragraph("<b>Notes:</b>", self.styles['InvoiceText']))
            elements.append(Paragraph(invoice.notes, self.styles['InvoiceText']))
            elements.append(Spacer(1, 0.1*inch))

        # Footer
        elements.append(Spacer(1, 0.3*inch))
        footer_text = "Thank you for your business!"
        elements.append(Paragraph(footer_text, self.styles['SmallText']))

        # Build PDF
        try:
            doc.build(elements)
            output_buffer.seek(0)
            logger.info(f"Generated PDF for invoice {invoice.invoice_number}")
            return output_buffer
        except Exception as e:
            logger.error(f"Error generating PDF for invoice {invoice.invoice_number}: {str(e)}")
            raise
