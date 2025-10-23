"""
Check printing service for EnDoc 1-per-page check stock
"""
import logging
from decimal import Decimal
from datetime import date
from typing import List, Dict, Optional
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

logger = logging.getLogger(__name__)


class CheckPrinter:
    """
    Generate PDF checks for EnDoc check stock (1 check per page)
    Format: Check on top half, stub on bottom half
    """

    # Page dimensions (8.5" x 11")
    PAGE_WIDTH, PAGE_HEIGHT = letter

    # Layout constants (in points, 72 points = 1 inch)
    CHECK_TOP = PAGE_HEIGHT / 2  # Check starts at 5.5" from bottom
    STUB_BOTTOM = 0
    STUB_TOP = PAGE_HEIGHT / 2  # 5.5" from bottom

    # Margins
    LEFT_MARGIN = 0.5 * inch
    RIGHT_MARGIN = 0.5 * inch
    TOP_MARGIN = 0.5 * inch
    BOTTOM_MARGIN = 0.5 * inch

    # MICR line position (bottom of check)
    MICR_Y = CHECK_TOP + 0.625 * inch  # 0.625" from bottom of check

    def __init__(self, output_path: str):
        """
        Initialize check printer

        Args:
            output_path: Path where PDF will be saved
        """
        self.output_path = output_path
        self.pdf = canvas.Canvas(output_path, pagesize=letter)

    def generate_checks(
        self,
        checks: List[Dict],
        company_info: Dict,
        bank_info: Dict,
        print_alignment_test: bool = False
    ) -> str:
        """
        Generate PDF with multiple checks (1 per page)

        Args:
            checks: List of check data dictionaries
            company_info: Company information
            bank_info: Bank account information
            print_alignment_test: If True, print alignment test page

        Returns:
            Path to generated PDF file
        """
        if print_alignment_test:
            self._draw_alignment_test()
            self.pdf.showPage()

        for check_data in checks:
            self._draw_single_check(check_data, company_info, bank_info)
            self.pdf.showPage()  # New page for next check

        self.pdf.save()
        logger.info(f"Generated {len(checks)} checks at {self.output_path}")
        return self.output_path

    def _draw_single_check(
        self,
        check_data: Dict,
        company_info: Dict,
        bank_info: Dict
    ):
        """Draw a single check on the current page"""
        # Draw check (top half)
        self._draw_check_section(check_data, company_info, bank_info)

        # Draw perforated line separator
        self._draw_perforation_line()

        # Draw stub (bottom half)
        self._draw_stub_section(check_data)

    def _draw_check_section(
        self,
        check_data: Dict,
        company_info: Dict,
        bank_info: Dict
    ):
        """Draw the actual check (top half - to be mailed)"""
        c = self.pdf

        # Starting Y position (top of check section)
        y = self.PAGE_HEIGHT - self.TOP_MARGIN

        # Company name and address (top left)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(self.LEFT_MARGIN, y, company_info.get('legal_name', ''))

        y -= 14
        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN, y, company_info.get('address_line1', ''))

        y -= 12
        city_state_zip = f"{company_info.get('city', '')}, {company_info.get('state', '')} {company_info.get('zip_code', '')}"
        c.drawString(self.LEFT_MARGIN, y, city_state_zip)

        # Check number (top right)
        check_number = check_data.get('check_number', '')
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            self.PAGE_HEIGHT - self.TOP_MARGIN,
            f"CHECK # {check_number}"
        )

        # Date (below check number)
        payment_date = check_data.get('payment_date', '')
        if isinstance(payment_date, date):
            payment_date = payment_date.strftime("%m/%d/%Y")
        c.setFont("Helvetica", 9)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            self.PAGE_HEIGHT - self.TOP_MARGIN - 20,
            f"Date: {payment_date}"
        )

        # "Pay to the Order of" line
        y = self.PAGE_HEIGHT - 2.0 * inch
        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN, y, "Pay to the")

        y -= 14
        c.drawString(self.LEFT_MARGIN, y, "Order of")

        # Payee name
        payee = check_data.get('payee_name', '')
        c.setFont("Helvetica-Bold", 11)
        c.drawString(self.LEFT_MARGIN + 0.8 * inch, y, payee)

        # Draw line under payee
        c.line(
            self.LEFT_MARGIN + 0.8 * inch,
            y - 2,
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y - 2
        )

        # Amount box (right side)
        y -= 0.5 * inch
        amount = check_data.get('amount', Decimal('0'))
        if isinstance(amount, (int, float, Decimal)):
            amount_str = f"$ {amount:,.2f}"
        else:
            amount_str = f"$ {amount}"

        # Draw amount box
        box_width = 1.5 * inch
        box_height = 0.3 * inch
        box_x = self.PAGE_WIDTH - self.RIGHT_MARGIN - box_width
        box_y = y

        c.rect(box_x, box_y, box_width, box_height)
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(
            box_x + box_width - 5,
            box_y + 8,
            amount_str
        )

        # Amount in words
        amount_words = self._amount_to_words(amount)
        y -= 0.6 * inch
        c.setFont("Helvetica", 10)
        c.drawString(self.LEFT_MARGIN, y, amount_words)

        # Draw line under amount words
        c.line(
            self.LEFT_MARGIN,
            y - 2,
            self.PAGE_WIDTH - self.RIGHT_MARGIN - 1.6 * inch,
            y - 2
        )

        c.setFont("Helvetica", 9)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y - 2,
            "Dollars"
        )

        # Bank information (lower left)
        y -= 0.8 * inch
        c.setFont("Helvetica", 8)
        c.drawString(self.LEFT_MARGIN + 2.5 * inch, y, bank_info.get('bank_name', ''))
        y -= 10
        if bank_info.get('bank_address'):
            c.drawString(self.LEFT_MARGIN + 2.5 * inch, y, bank_info['bank_address'])

        # Memo line
        y -= 0.4 * inch
        memo = check_data.get('memo', '')
        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN, y, f"Memo: {memo}")

        # Signature line (right side)
        sig_y = y
        sig_x = self.PAGE_WIDTH - self.RIGHT_MARGIN - 2.0 * inch
        c.line(sig_x, sig_y, self.PAGE_WIDTH - self.RIGHT_MARGIN, sig_y)
        c.setFont("Helvetica", 8)
        c.drawString(sig_x + 0.3 * inch, sig_y - 12, "Authorized Signature")

        # MICR line (bottom of check)
        self._draw_micr_line(check_data, bank_info)

    def _draw_micr_line(self, check_data: Dict, bank_info: Dict):
        """Draw MICR line at bottom of check"""
        c = self.pdf

        routing = bank_info.get('routing_number', '000000000')
        account = bank_info.get('account_number', '000000000')
        check_num = check_data.get('check_number', '0000')

        # MICR format: ⑆ Routing ⑆  ⑈ Account ⑈  Check Number
        micr_text = f"⑆{routing}⑆  ⑈{account}⑈  {check_num}"

        c.setFont("Helvetica", 10)
        c.drawString(self.LEFT_MARGIN, self.MICR_Y, micr_text)

    def _draw_perforation_line(self):
        """Draw perforated line separator between check and stub"""
        c = self.pdf

        # Dashed line at middle of page
        c.setDash(3, 3)  # 3 points on, 3 points off
        c.setStrokeColor(colors.grey)
        c.line(
            self.LEFT_MARGIN,
            self.STUB_TOP,
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            self.STUB_TOP
        )
        c.setDash()  # Reset to solid line
        c.setStrokeColor(colors.black)

        # "DETACH ABOVE" text
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            self.STUB_TOP + 3,
            "═══════ PERFORATED LINE - DETACH ABOVE ═══════"
        )
        c.setFillColor(colors.black)

    def _draw_stub_section(self, check_data: Dict):
        """Draw the stub (bottom half - keep for records)"""
        c = self.pdf

        # Starting Y position (from bottom)
        y = self.STUB_TOP - 0.3 * inch

        # Header
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            y,
            "═══ PAYMENT RECORD - KEEP FOR YOUR FILES ═══"
        )

        y -= 0.4 * inch

        # Check number and date
        check_num = check_data.get('check_number', '')
        payment_date = check_data.get('payment_date', '')
        if isinstance(payment_date, date):
            payment_date = payment_date.strftime("%m/%d/%Y")

        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN, y, f"Check Number: {check_num}")
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y,
            f"Date: {payment_date}"
        )

        y -= 0.25 * inch

        # Payee
        payee = check_data.get('payee_name', '')
        c.drawString(self.LEFT_MARGIN, y, f"Payee: {payee}")

        y -= 0.2 * inch

        # Amount
        amount = check_data.get('amount', Decimal('0'))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(self.LEFT_MARGIN, y, f"Amount: ${amount:,.2f}")

        y -= 0.3 * inch

        # Invoice details header
        c.setFont("Helvetica-Bold", 9)
        c.drawString(self.LEFT_MARGIN, y, "Invoices Paid:")

        y -= 0.25 * inch

        # Invoice table
        invoices = check_data.get('invoices', [])
        if invoices:
            self._draw_invoice_table(y, invoices)
            y -= (len(invoices) + 2) * 0.2 * inch  # Adjust for table height
        else:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN + 0.2 * inch, y, "No invoice details available")
            y -= 0.3 * inch

        # Bank account
        bank_account = check_data.get('bank_account_name', '')
        if bank_account:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN, y, f"Account: {bank_account}")
            y -= 0.2 * inch

        # Memo
        memo = check_data.get('memo', '')
        if memo:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN, y, f"Memo: {memo}")

    def _draw_invoice_table(self, start_y: float, invoices: List[Dict]):
        """Draw invoice table on stub"""
        c = self.pdf

        # Table headers
        headers = ["Invoice #", "Date", "Amount", "Discount"]
        col_widths = [1.5 * inch, 1.0 * inch, 1.0 * inch, 0.8 * inch]
        col_x = [
            self.LEFT_MARGIN + 0.2 * inch,
            self.LEFT_MARGIN + 0.2 * inch + col_widths[0],
            self.LEFT_MARGIN + 0.2 * inch + col_widths[0] + col_widths[1],
            self.LEFT_MARGIN + 0.2 * inch + col_widths[0] + col_widths[1] + col_widths[2]
        ]

        y = start_y

        # Draw header row
        c.setFont("Helvetica-Bold", 8)
        for i, header in enumerate(headers):
            c.drawString(col_x[i], y, header)

        y -= 0.15 * inch

        # Draw separator line
        c.line(
            self.LEFT_MARGIN + 0.2 * inch,
            y,
            self.LEFT_MARGIN + 0.2 * inch + sum(col_widths),
            y
        )

        y -= 0.15 * inch

        # Draw invoice rows
        c.setFont("Helvetica", 8)
        total_amount = Decimal('0')
        total_discount = Decimal('0')

        for inv in invoices:
            invoice_num = inv.get('invoice_number', '')
            invoice_date = inv.get('invoice_date', '')
            if isinstance(invoice_date, date):
                invoice_date = invoice_date.strftime("%m/%d/%Y")
            amount = inv.get('amount', Decimal('0'))
            discount = inv.get('discount', Decimal('0'))

            c.drawString(col_x[0], y, invoice_num)
            c.drawString(col_x[1], y, invoice_date)
            c.drawRightString(col_x[2] + col_widths[2] - 5, y, f"${amount:,.2f}")
            c.drawRightString(col_x[3] + col_widths[3] - 5, y, f"${discount:,.2f}")

            total_amount += amount
            total_discount += discount
            y -= 0.15 * inch

        # Draw total line
        y -= 0.05 * inch
        c.line(
            self.LEFT_MARGIN + 0.2 * inch,
            y,
            self.LEFT_MARGIN + 0.2 * inch + sum(col_widths),
            y
        )

        y -= 0.15 * inch

        # Draw totals
        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_x[0], y, "Total:")
        c.drawRightString(col_x[2] + col_widths[2] - 5, y, f"${total_amount:,.2f}")
        c.drawRightString(col_x[3] + col_widths[3] - 5, y, f"${total_discount:,.2f}")

    def _draw_alignment_test(self):
        """Draw alignment test page"""
        c = self.pdf

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            self.PAGE_HEIGHT - 0.5 * inch,
            "CHECK ALIGNMENT TEST PAGE"
        )

        c.setFont("Helvetica", 10)
        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            self.PAGE_HEIGHT - 0.8 * inch,
            "Print this page on plain paper and overlay on check stock to verify alignment"
        )

        # Draw check section outline
        c.setStrokeColor(colors.blue)
        c.rect(
            self.LEFT_MARGIN,
            self.CHECK_TOP,
            self.PAGE_WIDTH - self.LEFT_MARGIN - self.RIGHT_MARGIN,
            self.PAGE_HEIGHT - self.CHECK_TOP - self.TOP_MARGIN
        )

        # Draw stub section outline
        c.rect(
            self.LEFT_MARGIN,
            self.BOTTOM_MARGIN,
            self.PAGE_WIDTH - self.LEFT_MARGIN - self.RIGHT_MARGIN,
            self.STUB_TOP - self.BOTTOM_MARGIN
        )

        # Draw perforation line
        c.setDash(3, 3)
        c.line(
            0,
            self.STUB_TOP,
            self.PAGE_WIDTH,
            self.STUB_TOP
        )
        c.setDash()

        # Add alignment marks at corners
        mark_size = 0.25 * inch
        marks = [
            (self.LEFT_MARGIN, self.PAGE_HEIGHT - self.TOP_MARGIN),  # Top left
            (self.PAGE_WIDTH - self.RIGHT_MARGIN, self.PAGE_HEIGHT - self.TOP_MARGIN),  # Top right
            (self.LEFT_MARGIN, self.BOTTOM_MARGIN),  # Bottom left
            (self.PAGE_WIDTH - self.RIGHT_MARGIN, self.BOTTOM_MARGIN),  # Bottom right
        ]

        c.setStrokeColor(colors.red)
        for x, y in marks:
            c.line(x - mark_size, y, x + mark_size, y)
            c.line(x, y - mark_size, x, y + mark_size)

        c.setStrokeColor(colors.black)

    @staticmethod
    def _amount_to_words(amount: Decimal) -> str:
        """
        Convert numeric amount to words for check

        Args:
            amount: Dollar amount

        Returns:
            Amount in words (e.g., "One Thousand Two Hundred Thirty-Four and 56/100")
        """
        if isinstance(amount, (int, float)):
            amount = Decimal(str(amount))

        dollars = int(amount)
        cents = int((amount - dollars) * 100)

        # Simple implementation - can be enhanced with full number-to-words library
        if dollars == 0:
            words = "Zero"
        elif dollars < 1000:
            words = str(dollars)  # TODO: Implement full number-to-words
        else:
            # For now, use numeric with commas
            words = f"{dollars:,}"

        return f"{words} and {cents:02d}/100 Dollars"
