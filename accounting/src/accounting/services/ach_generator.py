"""
ACH/NACHA file generation service
Generates NACHA-formatted ACH files for bank submission
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict
import os

logger = logging.getLogger(__name__)


class ACHGenerator:
    """Generate NACHA-formatted ACH files"""

    RECORD_SIZE = 94  # NACHA standard record size

    def __init__(self, output_path: str):
        """
        Initialize ACH generator

        Args:
            output_path: Path where ACH file will be saved
        """
        self.output_path = output_path
        self.batch_count = 0
        self.total_debit_amount = Decimal('0')
        self.total_credit_amount = Decimal('0')
        self.entry_count = 0

    def generate_ach_file(
        self,
        payments: List[Dict],
        company_info: Dict,
        bank_info: Dict,
        batch_info: Dict
    ) -> str:
        """
        Generate NACHA ACH file

        Args:
            payments: List of payment dictionaries
            company_info: Company information
            bank_info: Originating bank information
            batch_info: Batch information

        Returns:
            Path to generated ACH file
        """
        lines = []

        # File Header Record (Type 1)
        lines.append(self._create_file_header(company_info, bank_info, batch_info))

        # Batch Header Record (Type 5)
        lines.append(self._create_batch_header(company_info, bank_info, batch_info))

        # Entry Detail Records (Type 6) - one per payment
        for payment in payments:
            lines.append(self._create_entry_detail(payment, company_info))
            self.entry_count += 1
            self.total_debit_amount += Decimal(str(payment.get('amount', 0)))

        # Batch Control Record (Type 8)
        lines.append(self._create_batch_control(company_info, bank_info))

        # File Control Record (Type 9)
        lines.append(self._create_file_control())

        # Pad to multiple of 10 records with 9s
        while len(lines) % 10 != 0:
            lines.append('9' * self.RECORD_SIZE)

        # Write to file
        with open(self.output_path, 'w') as f:
            f.write('\n'.join(lines))

        logger.info(f"Generated ACH file with {self.entry_count} payments at {self.output_path}")
        return self.output_path

    def _create_file_header(
        self,
        company_info: Dict,
        bank_info: Dict,
        batch_info: Dict
    ) -> str:
        """Create File Header Record (Type 1)"""
        record = '1'  # Record Type Code

        # Priority Code (01-99)
        record += '01'

        # Immediate Destination (bank routing, with leading space)
        routing = bank_info.get('routing_number', '000000000')
        record += f" {routing[:9]:9}"

        # Immediate Origin (company ID, with leading space)
        company_id = company_info.get('company_id', '0000000000')
        record += f" {company_id[:9]:9}"

        # File Creation Date (YYMMDD)
        creation_date = batch_info.get('batch_date', date.today())
        record += creation_date.strftime('%y%m%d')

        # File Creation Time (HHMM)
        record += datetime.now().strftime('%H%M')

        # File ID Modifier (A-Z, 0-9)
        record += 'A'

        # Record Size (094)
        record += '094'

        # Blocking Factor (10)
        record += '10'

        # Format Code (1)
        record += '1'

        # Immediate Destination Name (23 chars)
        bank_name = bank_info.get('bank_name', '')[:23]
        record += f"{bank_name:23}"

        # Immediate Origin Name (23 chars)
        company_name = company_info.get('legal_name', '')[:23]
        record += f"{company_name:23}"

        # Reference Code (8 chars)
        record += ' ' * 8

        return record[:self.RECORD_SIZE]

    def _create_batch_header(
        self,
        company_info: Dict,
        bank_info: Dict,
        batch_info: Dict
    ) -> str:
        """Create Batch Header Record (Type 5)"""
        self.batch_count += 1

        record = '5'  # Record Type Code

        # Service Class Code (200 = mixed debits/credits, 220 = credits only, 225 = debits only)
        record += '220'  # Credits only (vendor payments)

        # Company Name (16 chars)
        company_name = company_info.get('legal_name', '')[:16]
        record += f"{company_name:16}"

        # Company Discretionary Data (20 chars)
        record += ' ' * 20

        # Company Identification (10 chars) - EIN
        company_id = company_info.get('company_id', '0000000000')
        record += f"{company_id[:10]:10}"

        # Standard Entry Class Code (PPD, CCD, CTX, etc.)
        record += 'CCD'  # Cash Concentration or Disbursement

        # Company Entry Description (10 chars)
        record += f"{'PAYMENT':10}"

        # Company Descriptive Date (6 chars) - optional
        record += ' ' * 6

        # Effective Entry Date (YYMMDD)
        effective_date = batch_info.get('effective_date', date.today())
        record += effective_date.strftime('%y%m%d')

        # Settlement Date (3 chars) - leave blank
        record += '   '

        # Originator Status Code (1)
        record += '1'

        # Originating DFI Identification (8 chars) - first 8 of routing
        routing = bank_info.get('routing_number', '000000000')
        record += f"{routing[:8]:8}"

        # Batch Number (7 chars)
        record += f"{self.batch_count:07d}"

        return record[:self.RECORD_SIZE]

    def _create_entry_detail(
        self,
        payment: Dict,
        company_info: Dict
    ) -> str:
        """Create Entry Detail Record (Type 6)"""
        record = '6'  # Record Type Code

        # Transaction Code (22 = checking credit, 32 = savings credit, 27 = checking debit, 37 = savings debit)
        record += '22'  # Checking account credit (payment to vendor)

        # Receiving DFI Identification (8 chars) - vendor's bank routing
        vendor_routing = payment.get('vendor_routing', '000000000')
        record += f"{vendor_routing[:8]:8}"

        # Check Digit (1 char) - 9th digit of routing number
        record += vendor_routing[8:9] if len(vendor_routing) > 8 else '0'

        # DFI Account Number (17 chars)
        vendor_account = payment.get('vendor_account', '')
        record += f"{vendor_account[:17]:17}"

        # Amount (10 chars, no decimal point)
        amount = Decimal(str(payment.get('amount', 0)))
        amount_cents = int(amount * 100)
        record += f"{amount_cents:010d}"

        # Individual Identification Number (15 chars) - invoice/reference number
        reference = payment.get('reference', payment.get('payment_number', ''))[:15]
        record += f"{reference:15}"

        # Individual Name (22 chars) - vendor name
        vendor_name = payment.get('vendor_name', '')[:22]
        record += f"{vendor_name:22}"

        # Discretionary Data (2 chars)
        record += '  '

        # Addenda Record Indicator (0 = no addenda, 1 = addenda follows)
        record += '0'

        # Trace Number (15 chars) - routing (8) + sequence (7)
        company_routing = payment.get('company_routing', '000000000')
        trace_seq = payment.get('trace_sequence', 1)
        record += f"{company_routing[:8]:8}{trace_seq:07d}"

        return record[:self.RECORD_SIZE]

    def _create_batch_control(
        self,
        company_info: Dict,
        bank_info: Dict
    ) -> str:
        """Create Batch Control Record (Type 8)"""
        record = '8'  # Record Type Code

        # Service Class Code (same as batch header)
        record += '220'

        # Entry/Addenda Count (6 chars)
        record += f"{self.entry_count:06d}"

        # Entry Hash (10 chars) - sum of first 8 digits of all receiving DFI IDs
        # For now, simplified
        record += '0000000000'

        # Total Debit Entry Dollar Amount (12 chars)
        debit_cents = int(self.total_debit_amount * 100)
        record += f"{debit_cents:012d}"

        # Total Credit Entry Dollar Amount (12 chars)
        credit_cents = int(self.total_credit_amount * 100)
        record += f"{credit_cents:012d}"

        # Company Identification (10 chars)
        company_id = company_info.get('company_id', '0000000000')
        record += f"{company_id[:10]:10}"

        # Message Authentication Code (19 chars) - blank unless using MAC
        record += ' ' * 19

        # Reserved (6 chars)
        record += ' ' * 6

        # Originating DFI Identification (8 chars)
        routing = bank_info.get('routing_number', '000000000')
        record += f"{routing[:8]:8}"

        # Batch Number (7 chars)
        record += f"{self.batch_count:07d}"

        return record[:self.RECORD_SIZE]

    def _create_file_control(self) -> str:
        """Create File Control Record (Type 9)"""
        record = '9'  # Record Type Code

        # Batch Count (6 chars)
        record += f"{self.batch_count:06d}"

        # Block Count (6 chars) - total records / 10, rounded up
        total_records = 2 + self.batch_count * 2 + self.entry_count  # File header/control + batch header/control + entries
        block_count = (total_records + 9) // 10  # Round up
        record += f"{block_count:06d}"

        # Entry/Addenda Count (8 chars)
        record += f"{self.entry_count:08d}"

        # Entry Hash (10 chars)
        record += '0000000000'

        # Total Debit Entry Dollar Amount in File (12 chars)
        debit_cents = int(self.total_debit_amount * 100)
        record += f"{debit_cents:012d}"

        # Total Credit Entry Dollar Amount in File (12 chars)
        credit_cents = int(self.total_credit_amount * 100)
        record += f"{credit_cents:012d}"

        # Reserved (39 chars)
        record += ' ' * 39

        return record[:self.RECORD_SIZE]
