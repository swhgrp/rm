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

# Register MICR font for check printing
_micr_font_registered = False
def _register_micr_font():
    global _micr_font_registered
    if not _micr_font_registered:
        font_path = os.path.join(os.path.dirname(__file__), '..', 'fonts', 'micrenc.ttf')
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('MICR', font_path))
            _micr_font_registered = True
            logger.info(f"Registered MICR font from {font_path}")
        else:
            logger.warning(f"MICR font not found at {font_path}")
    return _micr_font_registered


class CheckPrinter:
    """
    Generate PDF checks for EnDoc check stock (1 check per page)
    Format: Check on top half, stub on bottom half
    """

    # Page dimensions (8.5" x 11")
    PAGE_WIDTH, PAGE_HEIGHT = letter

    # Layout constants for check-on-top stock (in points, 72 points = 1 inch)
    # Check area: top 3.5 inches of page
    # Stub area: bottom 7.5 inches of page
    CHECK_HEIGHT = 3.5 * inch
    STUB_TOP = PAGE_HEIGHT - CHECK_HEIGHT  # Perforation line at 7.5" from bottom
    STUB_BOTTOM = 0

    # Margins
    LEFT_MARGIN = 0.5 * inch
    RIGHT_MARGIN = 0.5 * inch
    TOP_MARGIN = 0.5 * inch  # Top margin for check area
    BOTTOM_MARGIN = 0.5 * inch

    # MICR line position (bottom of check area, 0.25" above perforation per ANSI X9.27)
    MICR_Y = STUB_TOP + 0.25 * inch

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
        """Draw the actual check (top 3.5 inches - to be mailed)"""
        c = self.pdf

        # Starting Y position (top of page)
        y = self.PAGE_HEIGHT - self.TOP_MARGIN

        # Check number (top right) - prominent
        check_number = check_data.get('check_number', '')
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y,
            f"{check_number}"
        )

        # Date (below check number on right)
        payment_date = check_data.get('payment_date', '')
        if isinstance(payment_date, date):
            payment_date = payment_date.strftime("%m/%d/%Y")
        c.setFont("Helvetica", 9)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y - 14,
            f"DATE: {payment_date}"
        )

        # Company name and address (top left)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(self.LEFT_MARGIN, y, company_info.get('legal_name', ''))

        y -= 11
        c.setFont("Helvetica", 8)
        c.drawString(self.LEFT_MARGIN, y, company_info.get('address_line1', ''))

        y -= 10
        city_state_zip = f"{company_info.get('city', '')}, {company_info.get('state', '')} {company_info.get('zip_code', '')}"
        c.drawString(self.LEFT_MARGIN, y, city_state_zip)

        # Bank name and account number (top center)
        bank_y = self.PAGE_HEIGHT - self.TOP_MARGIN
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(self.PAGE_WIDTH / 2, bank_y, bank_info.get('bank_name', ''))
        c.setFont("Helvetica", 8)
        c.drawCentredString(self.PAGE_WIDTH / 2, bank_y - 12, bank_info.get('account_number', ''))

        # "PAY TO THE ORDER OF" section - position carefully
        y = self.PAGE_HEIGHT - 1.1 * inch
        c.setFont("Helvetica", 8)
        c.drawString(self.LEFT_MARGIN, y, "PAY TO THE")
        c.drawString(self.LEFT_MARGIN, y - 10, "ORDER OF")

        # Payee name - larger and bold
        payee = check_data.get('payee_name', '')
        c.setFont("Helvetica-Bold", 10)
        c.drawString(self.LEFT_MARGIN + 0.75 * inch, y - 5, payee)

        # Draw line under payee (extends to amount box)
        c.line(
            self.LEFT_MARGIN + 0.75 * inch,
            y - 18,
            self.PAGE_WIDTH - self.RIGHT_MARGIN - 1.6 * inch,
            y - 18
        )

        # Amount box (right side, aligned with payee line)
        amount = check_data.get('amount', Decimal('0'))
        if isinstance(amount, (int, float, Decimal)):
            amount_str = f"${amount:,.2f}"
        else:
            amount_str = f"${amount}"

        box_width = 1.4 * inch
        box_height = 0.25 * inch
        box_x = self.PAGE_WIDTH - self.RIGHT_MARGIN - box_width
        box_y = y - 18

        c.rect(box_x, box_y, box_width, box_height)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(
            box_x + box_width - 4,
            box_y + 6,
            amount_str
        )

        # Amount in words line
        y = self.PAGE_HEIGHT - 1.55 * inch
        amount_words = self._amount_to_words(amount)
        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN, y, amount_words)

        # Draw line after amount words to "DOLLARS"
        c.line(
            self.LEFT_MARGIN + len(amount_words) * 4.5 + 10,
            y - 2,
            self.PAGE_WIDTH - self.RIGHT_MARGIN - 0.6 * inch,
            y - 2
        )

        c.setFont("Helvetica", 8)
        c.drawRightString(
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            y - 2,
            "DOLLARS"
        )

        # Payee address (below amount in words)
        payee_address = check_data.get('payee_address', {})
        y = self.PAGE_HEIGHT - 1.85 * inch
        c.setFont("Helvetica", 9)

        # Payee name repeated
        payee = check_data.get('payee_name', '')
        c.drawString(self.LEFT_MARGIN, y, payee)
        y -= 11

        # Address line 1
        addr1 = payee_address.get('address_line1', '')
        if addr1:
            c.drawString(self.LEFT_MARGIN, y, addr1)
            y -= 11

        # Address line 2 (if exists)
        addr2 = payee_address.get('address_line2', '')
        if addr2:
            c.drawString(self.LEFT_MARGIN, y, addr2)
            y -= 11

        # City, State ZIP
        city = payee_address.get('city', '')
        state = payee_address.get('state', '')
        zip_code = payee_address.get('zip_code', '')
        if city or state or zip_code:
            city_state_zip = f"{city} {state} {zip_code}".strip()
            c.drawString(self.LEFT_MARGIN, y, city_state_zip)

        # Memo line (bottom left of check area)
        y = self.PAGE_HEIGHT - 2.8 * inch
        memo = check_data.get('memo', '')
        c.setFont("Helvetica", 8)
        c.drawString(self.LEFT_MARGIN, y, "MEMO")
        c.setFont("Helvetica", 9)
        c.drawString(self.LEFT_MARGIN + 0.5 * inch, y, memo[:40] if memo else '')
        c.line(
            self.LEFT_MARGIN + 0.5 * inch,
            y - 2,
            self.LEFT_MARGIN + 3.5 * inch,
            y - 2
        )

        # Signature line (bottom right of check area)
        sig_y = y
        sig_x = self.PAGE_WIDTH - self.RIGHT_MARGIN - 2.5 * inch
        c.line(sig_x, sig_y - 2, self.PAGE_WIDTH - self.RIGHT_MARGIN, sig_y - 2)

        # "AUTHORIZED SIGNATURE" label under signature line
        c.setFont("Helvetica", 6)
        c.drawCentredString(
            sig_x + (self.PAGE_WIDTH - self.RIGHT_MARGIN - sig_x) / 2,
            sig_y - 12,
            "AUTHORIZED SIGNATURE"
        )

        # Draw MICR line at bottom of check
        self._draw_micr_line(check_data, bank_info)

    def _draw_micr_line(self, check_data: Dict, bank_info: Dict):
        """Draw MICR line at bottom of check

        Uses MICR E-13B font for blank check stock.
        Standard MICR format (left to right): Transit routing Transit  account On-Us  On-Us check_number On-Us
        """
        c = self.pdf

        routing = bank_info.get('routing_number', '') or ''
        account = bank_info.get('account_number', '') or ''
        check_num = str(check_data.get('check_number', ''))

        # MICR E-13B font character mappings (micrenc.ttf):
        # Transit symbol = 'A' (surrounds routing number)
        # On-Us symbol = 'C' (surrounds check number, ends account)
        # Amount symbol = 'B'
        # Dash symbol = 'D'
        transit = 'A'
        on_us = 'C'

        # Standard MICR format: Arouting_numberA accountC Ccheck_numberC
        micr_text = f"{transit}{routing}{transit} {account}{on_us} {on_us}{check_num}{on_us}"

        # Try to use MICR font, fall back to Courier if not available
        if _register_micr_font():
            c.setFont("MICR", 18)
        else:
            c.setFont("Courier-Bold", 18)

        # MICR line positioned per ANSI X9.27 specs, centered on page
        micr_width = c.stringWidth(micr_text, c._fontname, c._fontsize)
        micr_x = (self.PAGE_WIDTH - micr_width) / 2
        c.drawString(micr_x, self.MICR_Y, micr_text)

    def _draw_perforation_line(self):
        """Draw perforated line separator between check and stub"""
        c = self.pdf

        # Dashed line at perforation (moved down slightly to align with actual perforation)
        perf_y = self.STUB_TOP - 0.2 * inch
        c.setDash(3, 3)  # 3 points on, 3 points off
        c.setStrokeColor(colors.grey)
        c.line(
            self.LEFT_MARGIN,
            perf_y,
            self.PAGE_WIDTH - self.RIGHT_MARGIN,
            perf_y
        )
        c.setDash()  # Reset to solid line
        c.setStrokeColor(colors.black)

        # "DETACH ABOVE" text - positioned below perforation line on stub
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            self.STUB_TOP - 0.35 * inch,
            "═══════ PERFORATED LINE - DETACH ABOVE ═══════"
        )
        c.setFillColor(colors.black)

    def _draw_stub_section(self, check_data: Dict):
        """Draw the stub (bottom half - keep for records)"""
        c = self.pdf

        # Starting Y position (from bottom)
        y = self.STUB_TOP - 0.6 * inch

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
            y = self._draw_invoice_table(y, invoices)
        else:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN + 0.2 * inch, y, "No invoice details available")
            y -= 0.3 * inch

        y -= 0.2 * inch  # Extra spacing after table

        # Bank account
        bank_account = check_data.get('bank_account_name', '')
        if bank_account:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN, y, f"Account: {bank_account}")
            y -= 0.15 * inch

        # Memo
        memo = check_data.get('memo', '')
        if memo:
            c.setFont("Helvetica", 8)
            c.drawString(self.LEFT_MARGIN, y, f"Memo: {memo}")

    def _draw_invoice_table(self, start_y: float, invoices: List[Dict]) -> float:
        """Draw invoice table on stub. Returns final Y position."""
        c = self.pdf

        # Table headers
        headers = ["Invoice #", "Date", "Amount", "Discount"]
        col_widths = [2.5 * inch, 1.0 * inch, 1.0 * inch, 0.8 * inch]
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
            # Truncate long invoice numbers
            if len(invoice_num) > 30:
                invoice_num = invoice_num[:27] + '...'
            invoice_date = inv.get('invoice_date', '')
            if isinstance(invoice_date, date):
                invoice_date = invoice_date.strftime("%m/%d/%Y")
            amount = inv.get('amount', Decimal('0'))
            discount = inv.get('discount', Decimal('0'))

            c.drawString(col_x[0], y, invoice_num)
            c.drawString(col_x[1], y, str(invoice_date))
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

        return y

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

        c.drawCentredString(
            self.PAGE_WIDTH / 2,
            self.PAGE_HEIGHT - 1.0 * inch,
            f"Check area: Top 3.5 inches | Stub area: Bottom 7.5 inches"
        )

        # Draw check section outline (top 3.5 inches)
        c.setStrokeColor(colors.blue)
        c.rect(
            self.LEFT_MARGIN,
            self.STUB_TOP,  # Bottom of check area
            self.PAGE_WIDTH - self.LEFT_MARGIN - self.RIGHT_MARGIN,
            self.CHECK_HEIGHT - self.TOP_MARGIN
        )

        # Label the check area
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.blue)
        c.drawString(self.LEFT_MARGIN + 5, self.STUB_TOP + 5, "CHECK AREA (3.5\")")
        c.setFillColor(colors.black)

        # Draw stub section outline (bottom 7.5 inches)
        c.setStrokeColor(colors.green)
        c.rect(
            self.LEFT_MARGIN,
            self.BOTTOM_MARGIN,
            self.PAGE_WIDTH - self.LEFT_MARGIN - self.RIGHT_MARGIN,
            self.STUB_TOP - self.BOTTOM_MARGIN
        )

        # Label the stub area
        c.setFillColor(colors.green)
        c.drawString(self.LEFT_MARGIN + 5, self.STUB_TOP - 15, "STUB/VOUCHER AREA (7.5\")")
        c.setFillColor(colors.black)

        # Draw perforation line
        c.setStrokeColor(colors.red)
        c.setDash(3, 3)
        c.line(
            0,
            self.STUB_TOP,
            self.PAGE_WIDTH,
            self.STUB_TOP
        )
        c.setDash()

        # Label perforation
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.red)
        c.drawCentredString(self.PAGE_WIDTH / 2, self.STUB_TOP + 3, "PERFORATION LINE")
        c.setFillColor(colors.black)

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
            Amount in words (e.g., "Five Thousand, Six Hundred And Twenty-Seven Dollars and Fifty-Five Cents")
        """
        if isinstance(amount, (int, float)):
            amount = Decimal(str(amount))

        dollars = int(amount)
        cents = int((amount - dollars) * 100)

        # Number to words conversion
        ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
                'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
                'Seventeen', 'Eighteen', 'Nineteen']
        tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

        def two_digits(n):
            if n < 20:
                return ones[n]
            elif n % 10 == 0:
                return tens[n // 10]
            else:
                return f"{tens[n // 10]}-{ones[n % 10]}"

        def three_digits(n):
            if n == 0:
                return ''
            elif n < 100:
                return two_digits(n)
            else:
                remainder = n % 100
                if remainder == 0:
                    return f"{ones[n // 100]} Hundred"
                else:
                    return f"{ones[n // 100]} Hundred And {two_digits(remainder)}"

        def convert_dollars(n):
            if n == 0:
                return 'Zero'

            parts = []

            # Millions
            if n >= 1000000:
                millions = n // 1000000
                parts.append(f"{three_digits(millions)} Million")
                n %= 1000000

            # Thousands
            if n >= 1000:
                thousands = n // 1000
                parts.append(f"{three_digits(thousands)} Thousand")
                n %= 1000

            # Hundreds/tens/ones
            if n > 0:
                parts.append(three_digits(n))

            return ', '.join(parts)

        # Build the full amount string
        dollar_words = convert_dollars(dollars)

        if cents == 0:
            cents_words = "Zero Cents"
        else:
            cents_words = f"{two_digits(cents)} Cents"

        return f"{dollar_words} Dollars and {cents_words}*****"
