"""
PDF Report Generator using ReportLab
"""
from io import BytesIO
from datetime import date
from decimal import Decimal
from typing import List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


class PDFReportGenerator:
    """Generate PDF reports for financial statements"""

    def __init__(self, company_name: str = "SW Hospitality Group"):
        self.company_name = company_name
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        # Company name style
        self.styles.add(ParagraphStyle(
            name='CompanyName',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Report title style
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#666666'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica'
        ))

        # Right-aligned number style
        self.styles.add(ParagraphStyle(
            name='NumberRight',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
            fontName='Courier'
        ))

    def generate_hierarchical_pl(
        self,
        data: dict,
        output_buffer: Optional[BytesIO] = None
    ) -> BytesIO:
        """
        Generate hierarchical Profit & Loss PDF report

        Args:
            data: Dictionary with P&L data from API
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

        # Add header based on location or consolidated
        if data.get('area_name'):
            # Single location - show legal name (if available), DBA, and address
            if data.get('area_legal_name'):
                elements.append(Paragraph(data['area_legal_name'], self.styles['CompanyName']))
                elements.append(Paragraph(f"DBA: {data['area_name']}", self.styles['Subtitle']))
            else:
                elements.append(Paragraph(data['area_name'], self.styles['CompanyName']))

            # Add address if available
            address_parts = []
            if data.get('area_address_line1'):
                address_parts.append(data['area_address_line1'])
            if data.get('area_address_line2'):
                address_parts.append(data['area_address_line2'])

            if address_parts:
                elements.append(Paragraph(', '.join(address_parts), self.styles['Subtitle']))

            # City, State ZIP
            city_state_zip = []
            if data.get('area_city'):
                city_state_zip.append(data['area_city'])
            if data.get('area_state'):
                city_state_zip.append(data['area_state'])
            if data.get('area_zip_code'):
                city_state_zip.append(data['area_zip_code'])

            if city_state_zip:
                elements.append(Paragraph(', '.join(city_state_zip), self.styles['Subtitle']))
        else:
            # Consolidated report
            elements.append(Paragraph(f"{self.company_name} - Consolidated", self.styles['CompanyName']))

        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Profit & Loss Statement", self.styles['ReportTitle']))

        # Add date range
        start_date = date.fromisoformat(data['start_date']).strftime('%B %d, %Y')
        end_date = date.fromisoformat(data['end_date']).strftime('%B %d, %Y')
        date_range = f"{start_date} to {end_date}"
        elements.append(Paragraph(date_range, self.styles['Subtitle']))

        elements.append(Spacer(1, 0.2*inch))

        # Build table data
        table_data = []

        # Revenue Section
        table_data.extend(self._build_section_rows(
            data['revenue_section'],
            "REVENUE"
        ))

        # COGS Section
        if data['cogs_section']['accounts']:
            table_data.extend(self._build_section_rows(
                data['cogs_section'],
                "COST OF GOODS SOLD"
            ))

        # Gross Profit
        table_data.append([
            Paragraph("<b>GROSS PROFIT</b>", self.styles['Normal']),
            Paragraph(f"<b>${float(data['gross_profit']):,.2f}</b>", self.styles['NumberRight'])
        ])
        table_data.append(['', ''])  # Spacer row

        # Expenses Section
        if data['expense_section']['accounts']:
            table_data.extend(self._build_section_rows(
                data['expense_section'],
                "OPERATING EXPENSES"
            ))

        # Net Income
        table_data.append([
            Paragraph("<b>NET INCOME</b>", self.styles['Normal']),
            Paragraph(f"<b>${float(data['net_income']):,.2f}</b>", self.styles['NumberRight'])
        ])

        # Create the table
        col_widths = [4.5*inch, 2*inch]
        table = Table(table_data, colWidths=col_widths)

        # Apply table styling
        style = TableStyle([
            # General styling
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),

            # Grid lines
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
        ])

        table.setStyle(style)
        elements.append(table)

        # Build PDF
        doc.build(elements)
        output_buffer.seek(0)

        return output_buffer

    def _build_section_rows(self, section_data: dict, section_title: str) -> List:
        """Build table rows for a P&L section with hierarchy"""
        rows = []

        # Section header
        rows.append([
            Paragraph(f"<b>{section_title}</b>", self.styles['Normal']),
            ''
        ])

        # Process accounts recursively
        for account in section_data['accounts']:
            rows.extend(self._build_account_rows(account, 0))

        # Section total
        total = float(section_data['total'])
        rows.append([
            Paragraph(f"<b>Total {section_data['section_name']}</b>", self.styles['Normal']),
            Paragraph(f"<b>${total:,.2f}</b>", self.styles['NumberRight'])
        ])
        rows.append(['', ''])  # Spacer row

        return rows

    def _build_account_rows(self, account: dict, level: int) -> List:
        """Recursively build rows for an account and its children"""
        rows = []
        indent = "&nbsp;" * (level * 8)  # 8 spaces per level

        # Account name and amount
        account_name = f"{indent}{account['account_number']} - {account['account_name']}"
        amount = float(account['amount'])

        if account['is_summary'] and account.get('children'):
            # Summary account - bold
            rows.append([
                Paragraph(f"<b>{account_name}</b>", self.styles['Normal']),
                Paragraph(f"<b>${amount:,.2f}</b>", self.styles['NumberRight'])
            ])
        else:
            # Regular account
            rows.append([
                Paragraph(account_name, self.styles['Normal']),
                Paragraph(f"${amount:,.2f}", self.styles['NumberRight'])
            ])

        # Process children recursively
        if account.get('children'):
            for child in account['children']:
                rows.extend(self._build_account_rows(child, level + 1))

            # Add subtotal for summary accounts
            if account['is_summary']:
                subtotal_indent = "&nbsp;" * ((level + 1) * 8)
                rows.append([
                    Paragraph(f"<i>{subtotal_indent}Total {account['account_name']}</i>", self.styles['Normal']),
                    Paragraph(f"<b>${amount:,.2f}</b>", self.styles['NumberRight'])
                ])

        return rows


    def generate_hierarchical_bs(
        self,
        data: dict,
        output_buffer: Optional[BytesIO] = None
    ) -> BytesIO:
        """
        Generate hierarchical Balance Sheet PDF report

        Args:
            data: Dictionary with Balance Sheet data from API
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

        elements = []

        # Add header based on location or consolidated
        if data.get('area_name'):
            # Single location - show legal name (if available), DBA, and address
            if data.get('area_legal_name'):
                elements.append(Paragraph(data['area_legal_name'], self.styles['CompanyName']))
                elements.append(Paragraph(f"DBA: {data['area_name']}", self.styles['Subtitle']))
            else:
                elements.append(Paragraph(data['area_name'], self.styles['CompanyName']))

            # Add address if available
            address_parts = []
            if data.get('area_address_line1'):
                address_parts.append(data['area_address_line1'])
            if data.get('area_address_line2'):
                address_parts.append(data['area_address_line2'])

            if address_parts:
                elements.append(Paragraph(', '.join(address_parts), self.styles['Subtitle']))

            # City, State ZIP
            city_state_zip = []
            if data.get('area_city'):
                city_state_zip.append(data['area_city'])
            if data.get('area_state'):
                city_state_zip.append(data['area_state'])
            if data.get('area_zip_code'):
                city_state_zip.append(data['area_zip_code'])

            if city_state_zip:
                elements.append(Paragraph(', '.join(city_state_zip), self.styles['Subtitle']))
        else:
            # Consolidated report
            elements.append(Paragraph(f"{self.company_name} - Consolidated", self.styles['CompanyName']))

        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Balance Sheet", self.styles['ReportTitle']))

        # Add as of date
        as_of = date.fromisoformat(data['as_of_date']).strftime('%B %d, %Y')
        elements.append(Paragraph(f"As of {as_of}", self.styles['Subtitle']))

        elements.append(Spacer(1, 0.2*inch))

        # Build table data
        table_data = []

        # Assets Section
        table_data.extend(self._build_section_rows(
            data['asset_section'],
            "ASSETS"
        ))

        # Liabilities Section
        if data['liability_section']['accounts']:
            table_data.extend(self._build_section_rows(
                data['liability_section'],
                "LIABILITIES"
            ))

        # Equity Section
        if data['equity_section']['accounts']:
            table_data.extend(self._build_section_rows(
                data['equity_section'],
                "EQUITY"
            ))

        # Total Liabilities & Equity
        table_data.append([
            Paragraph("<b>TOTAL LIABILITIES & EQUITY</b>", self.styles['Normal']),
            Paragraph(f"<b>${float(data['total_liabilities_equity']):,.2f}</b>", self.styles['NumberRight'])
        ])

        # Balance check
        balance_text = "BALANCED ✓" if data['is_balanced'] else "NOT BALANCED ✗"
        table_data.append(['', ''])
        table_data.append([
            Paragraph(f"<b>{balance_text}</b>", self.styles['Normal']),
            Paragraph(f"<b>Assets: ${float(data['total_assets']):,.2f}</b>", self.styles['NumberRight'])
        ])

        # Create the table
        col_widths = [4.5*inch, 2*inch]
        table = Table(table_data, colWidths=col_widths)

        # Apply table styling
        style = TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
        ])

        table.setStyle(style)
        elements.append(table)

        # Build PDF
        doc.build(elements)
        output_buffer.seek(0)

        return output_buffer
