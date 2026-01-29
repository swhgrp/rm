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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import logging

logger = logging.getLogger(__name__)

# Brand colors
BRAND_BLUE = colors.HexColor('#1a3a5c')
BRAND_ACCENT = colors.HexColor('#2563eb')
DARK_TEXT = colors.HexColor('#1a1a1a')
MEDIUM_TEXT = colors.HexColor('#4a5568')
LIGHT_TEXT = colors.HexColor('#718096')
HEADER_BG = colors.HexColor('#1a3a5c')
ROW_ALT_BG = colors.HexColor('#f7fafc')
BORDER_COLOR = colors.HexColor('#e2e8f0')
TOTAL_BG = colors.HexColor('#edf2f7')


class InvoicePDFService:
    """Generate PDF invoices for customers"""

    def __init__(self, company_name: str = "SW Hospitality Group"):
        self.company_name = company_name
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles for invoices"""
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Heading1'],
            fontSize=22,
            textColor=BRAND_BLUE,
            spaceAfter=2,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold',
            leading=26
        ))

        self.styles.add(ParagraphStyle(
            name='LocationInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=MEDIUM_TEXT,
            fontName='Helvetica',
            leading=13
        ))

        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=BRAND_ACCENT,
            spaceAfter=4,
            alignment=TA_RIGHT,
            fontName='Helvetica-Bold',
            leading=32
        ))

        self.styles.add(ParagraphStyle(
            name='InvoiceNumber',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=MEDIUM_TEXT,
            alignment=TA_RIGHT,
            fontName='Helvetica',
            leading=14
        ))

        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=11,
            textColor=BRAND_BLUE,
            spaceAfter=6,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='InvoiceText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=DARK_TEXT,
            fontName='Helvetica',
            leading=14
        ))

        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=LIGHT_TEXT,
            fontName='Helvetica',
            leading=11
        ))

        self.styles.add(ParagraphStyle(
            name='NumberRight',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
            fontName='Helvetica',
            textColor=DARK_TEXT,
            leading=14
        ))

        self.styles.add(ParagraphStyle(
            name='BoldText',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=DARK_TEXT,
            leading=14
        ))

        self.styles.add(ParagraphStyle(
            name='BoldRight',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT,
            textColor=DARK_TEXT,
            leading=14
        ))

        self.styles.add(ParagraphStyle(
            name='BalanceDue',
            parent=self.styles['Normal'],
            fontSize=13,
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT,
            textColor=BRAND_BLUE,
            leading=16
        ))

        self.styles.add(ParagraphStyle(
            name='BalanceDueLabel',
            parent=self.styles['Normal'],
            fontSize=13,
            fontName='Helvetica-Bold',
            textColor=BRAND_BLUE,
            leading=16
        ))

        self.styles.add(ParagraphStyle(
            name='FooterText',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=MEDIUM_TEXT,
            fontName='Helvetica-Oblique',
            alignment=TA_CENTER
        ))

        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.white,
            leading=12
        ))

        self.styles.add(ParagraphStyle(
            name='TableHeaderRight',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.white,
            alignment=TA_RIGHT,
            leading=12
        ))

    def generate_invoice_pdf(
        self,
        invoice,
        customer,
        line_items: list,
        area=None,
        output_buffer: Optional[BytesIO] = None
    ) -> BytesIO:
        """
        Generate a professional PDF invoice

        Args:
            invoice: CustomerInvoice object
            customer: Customer object
            line_items: List of CustomerInvoiceLine objects
            area: Optional Area object for location branding
            output_buffer: Optional BytesIO buffer to write to

        Returns:
            BytesIO buffer containing the PDF
        """
        if output_buffer is None:
            output_buffer = BytesIO()

        doc = SimpleDocTemplate(
            output_buffer,
            pagesize=letter,
            rightMargin=0.6*inch,
            leftMargin=0.6*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )

        elements = []

        # === HEADER: Location/Company name + INVOICE title ===
        company_display = self.company_name
        if area and area.name:
            company_display = area.name

        location_info = ""
        if area:
            addr_parts = []
            if area.address_line1:
                addr_parts.append(area.address_line1)
            if area.address_line2:
                addr_parts.append(area.address_line2)
            csz = []
            if area.city:
                csz.append(area.city)
            if area.state:
                csz.append(area.state)
            if area.zip_code:
                csz.append(area.zip_code)
            if csz:
                addr_parts.append(', '.join(csz))
            if area.phone:
                addr_parts.append(area.phone)
            if area.email:
                addr_parts.append(area.email)
            location_info = '<br/>'.join(addr_parts)

        # Build left side: company name + location details
        left_content = [Paragraph(company_display, self.styles['CompanyName'])]
        if location_info:
            left_content.append(Paragraph(location_info, self.styles['LocationInfo']))

        # Build right side: INVOICE title + invoice number
        right_content = [
            Paragraph("INVOICE", self.styles['InvoiceTitle']),
            Paragraph(f"#{invoice.invoice_number}", self.styles['InvoiceNumber'])
        ]

        # Use nested tables for multi-line cells
        left_table = Table([[elem] for elem in left_content], colWidths=[3.8*inch])
        left_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        right_table = Table([[elem] for elem in right_content], colWidths=[3*inch])
        right_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        header_table = Table([[left_table, right_table]], colWidths=[3.8*inch, 3*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(header_table)

        # Divider line
        elements.append(Spacer(1, 0.15*inch))
        elements.append(HRFlowable(
            width="100%", thickness=2, color=BRAND_BLUE,
            spaceAfter=0.2*inch, spaceBefore=0
        ))

        # === BILL TO + INVOICE DETAILS side by side ===
        customer_address = f"<b>Bill To:</b><br/>"
        customer_address += f"<b>{customer.customer_name}</b><br/>"

        if customer.contact_name:
            customer_address += f"{customer.contact_name}<br/>"
        if customer.address_line1:
            customer_address += f"{customer.address_line1}<br/>"
        if customer.address_line2:
            customer_address += f"{customer.address_line2}<br/>"

        csz = []
        if customer.city:
            csz.append(customer.city)
        if customer.state:
            csz.append(customer.state)
        if customer.zip_code:
            csz.append(customer.zip_code)
        if csz:
            customer_address += f"{', '.join(csz)}<br/>"

        # Invoice details box
        detail_rows = [
            ("Invoice Date:", invoice.invoice_date.strftime('%B %d, %Y')),
            ("Due Date:", invoice.due_date.strftime('%B %d, %Y')),
        ]
        if invoice.po_number:
            detail_rows.append(("PO Number:", invoice.po_number))
        if invoice.event_date:
            detail_rows.append(("Event Date:", invoice.event_date.strftime('%B %d, %Y')))

        # Build details as a mini table with labels and values
        detail_data = []
        for label, value in detail_rows:
            detail_data.append([
                Paragraph(f"<b>{label}</b>", self.styles['SmallText']),
                Paragraph(value, self.styles['InvoiceText'])
            ])

        details_table = Table(detail_data, colWidths=[1.1*inch, 1.9*inch])
        details_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, -1), ROW_ALT_BG),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, BORDER_COLOR),
        ]))

        info_data = [[
            Paragraph(customer_address, self.styles['InvoiceText']),
            details_table
        ]]

        info_table = Table(info_data, colWidths=[3.6*inch, 3.2*inch])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.25*inch))

        # === EVENT DETAILS (if applicable) ===
        if invoice.event_type or invoice.event_location or invoice.guest_count:
            event_parts = []
            if invoice.event_type:
                event_parts.append(f"<b>Event:</b> {invoice.event_type}")
            if invoice.event_location:
                event_parts.append(f"<b>Location:</b> {invoice.event_location}")
            if invoice.guest_count:
                event_parts.append(f"<b>Guests:</b> {invoice.guest_count}")

            event_text = "&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;".join(event_parts)
            event_data = [[Paragraph(event_text, self.styles['InvoiceText'])]]
            event_table = Table(event_data, colWidths=[6.8*inch])
            event_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), ROW_ALT_BG),
                ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(event_table)
            elements.append(Spacer(1, 0.2*inch))

        # === LINE ITEMS TABLE ===
        line_items_data = [[
            Paragraph("Description", self.styles['TableHeader']),
            Paragraph("Qty", self.styles['TableHeaderRight']),
            Paragraph("Unit Price", self.styles['TableHeaderRight']),
            Paragraph("Discount", self.styles['TableHeaderRight']),
            Paragraph("Amount", self.styles['TableHeaderRight'])
        ]]

        for line in line_items:
            description = line.description or f"Account {line.account_id}"
            line_amount = float(line.amount)
            line_discount = float(line.discount_amount) if line.discount_amount else 0
            net_amount = line_amount - line_discount

            discount_text = ""
            if line_discount > 0:
                pct = f" ({float(line.discount_percentage)}%)" if line.discount_percentage else ""
                discount_text = f"-${line_discount:,.2f}{pct}"

            line_items_data.append([
                Paragraph(description, self.styles['InvoiceText']),
                Paragraph(f"{float(line.quantity):.2f}", self.styles['NumberRight']),
                Paragraph(f"${float(line.unit_price):,.2f}", self.styles['NumberRight']),
                Paragraph(discount_text, self.styles['NumberRight']),
                Paragraph(f"${net_amount:,.2f}", self.styles['NumberRight'])
            ])

        line_items_table = Table(
            line_items_data,
            colWidths=[2.8*inch, 0.7*inch, 1*inch, 1*inch, 1.1*inch]
        )

        # Build table style with alternating rows
        table_style = [
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

            # Grid lines
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, BRAND_BLUE),
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, BORDER_COLOR),

            # Box around entire table
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ]

        # Alternating row backgrounds
        for i in range(1, len(line_items_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT_BG))

        line_items_table.setStyle(TableStyle(table_style))
        elements.append(line_items_table)
        elements.append(Spacer(1, 0.2*inch))

        # === TOTALS SECTION ===
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
                Paragraph("Tax Exempt", self.styles['SmallText'])
            ])

        # Total
        totals_data.append([
            Paragraph("<b>Total Amount:</b>", self.styles['BoldText']),
            Paragraph(f"<b>${float(invoice.total_amount):,.2f}</b>", self.styles['BoldRight'])
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
                Paragraph("Payments Received:", self.styles['InvoiceText']),
                Paragraph(f"-${float(invoice.paid_amount):,.2f}", self.styles['NumberRight'])
            ])

        # Balance Due
        balance_due = invoice.total_amount - invoice.deposit_amount - invoice.paid_amount
        if balance_due > 0:
            totals_data.append([
                Paragraph("Balance Due:", self.styles['BalanceDueLabel']),
                Paragraph(f"${float(balance_due):,.2f}", self.styles['BalanceDue'])
            ])
        else:
            totals_data.append([
                Paragraph("Balance Due:", self.styles['BalanceDueLabel']),
                Paragraph("PAID IN FULL", self.styles['BalanceDue'])
            ])

        totals_table = Table(totals_data, colWidths=[1.5*inch, 1.3*inch])

        totals_style = [
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            # Line above Total Amount row
            ('LINEABOVE', (0, -2), (-1, -2), 1, BORDER_COLOR),
            # Balance Due row styling
            ('BACKGROUND', (0, -1), (-1, -1), TOTAL_BG),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, BRAND_BLUE),
            ('TOPPADDING', (0, -1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
            # Box around totals
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ]
        totals_table.setStyle(TableStyle(totals_style))

        # Right-align the totals table
        totals_wrapper = Table([[totals_table]], colWidths=[6.8*inch])
        totals_wrapper.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(totals_wrapper)
        elements.append(Spacer(1, 0.3*inch))

        # === PAYMENT TERMS & NOTES ===
        if customer.payment_terms:
            elements.append(Paragraph(
                f"<b>Payment Terms:</b> {customer.payment_terms}",
                self.styles['InvoiceText']
            ))
            elements.append(Spacer(1, 0.1*inch))

        if invoice.notes:
            elements.append(Paragraph("<b>Notes:</b>", self.styles['SectionHeader']))
            elements.append(Paragraph(invoice.notes, self.styles['InvoiceText']))
            elements.append(Spacer(1, 0.15*inch))

        # === FOOTER ===
        elements.append(Spacer(1, 0.3*inch))
        elements.append(HRFlowable(
            width="100%", thickness=0.5, color=BORDER_COLOR,
            spaceAfter=0.15*inch, spaceBefore=0
        ))
        elements.append(Paragraph(
            "Thank you for your business!",
            self.styles['FooterText']
        ))

        # Build PDF
        try:
            doc.build(elements)
            output_buffer.seek(0)
            logger.info(f"Generated PDF for invoice {invoice.invoice_number}")
            return output_buffer
        except Exception as e:
            logger.error(f"Error generating PDF for invoice {invoice.invoice_number}: {str(e)}")
            raise
