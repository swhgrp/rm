"""
AR GL Integration Service

Automates journal entry creation for:
1. Customer invoices (when sent) - DR: AR, CR: Revenue
2. Customer payments (when recorded) - DR: Cash/Bank, CR: AR
3. Deposits/prepayments - DR: Cash/Bank, CR: Customer Deposits (Liability)
"""
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import date, datetime
from typing import Optional
import logging

from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.customer_invoice import CustomerInvoice, InvoicePayment
from accounting.models.account import Account, AccountType
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus

logger = logging.getLogger(__name__)


class ARGLService:
    """Service to automate GL posting for AR transactions"""

    # Standard AR account codes - these should be configured per business
    AR_ACCOUNT_NUMBER = "1200"  # Accounts Receivable
    CUSTOMER_DEPOSITS_ACCOUNT_NUMBER = "2100"  # Customer Deposits (liability)

    def __init__(self, db: Session):
        self.db = db

    def _get_ar_account(self) -> Account:
        """Get the Accounts Receivable GL account"""
        account = self.db.query(Account).filter(
            Account.account_number == self.AR_ACCOUNT_NUMBER
        ).first()

        if not account:
            # Try to find by account type
            account = self.db.query(Account).filter(
                Account.account_type == AccountType.ACCOUNTS_RECEIVABLE
            ).first()

        if not account:
            raise ValueError(
                f"AR account not found. Please create account {self.AR_ACCOUNT_NUMBER} "
                "or configure an Accounts Receivable account."
            )

        return account

    def _get_customer_deposits_account(self) -> Account:
        """Get the Customer Deposits liability account"""
        account = self.db.query(Account).filter(
            Account.account_number == self.CUSTOMER_DEPOSITS_ACCOUNT_NUMBER
        ).first()

        if not account:
            raise ValueError(
                f"Customer Deposits account not found. Please create account {self.CUSTOMER_DEPOSITS_ACCOUNT_NUMBER} "
                "for tracking prepayments and deposits."
            )

        return account

    def _get_fiscal_period(self, entry_date: date) -> Optional[FiscalPeriod]:
        """Get fiscal period for a given date"""
        return self.db.query(FiscalPeriod).filter(
            FiscalPeriod.start_date <= entry_date,
            FiscalPeriod.end_date >= entry_date,
            FiscalPeriod.status == FiscalPeriodStatus.OPEN
        ).first()

    def _generate_entry_number(self, entry_date: date, prefix: str = "JE") -> str:
        """Generate sequential entry number: PREFIX-YYYYMMDD-NNN"""
        date_str = entry_date.strftime('%Y%m%d')
        entry_prefix = f"{prefix}-{date_str}-"

        # Find the highest number for this date/prefix
        last_entry = self.db.query(JournalEntry).filter(
            JournalEntry.entry_number.like(f"{entry_prefix}%")
        ).order_by(JournalEntry.entry_number.desc()).first()

        if last_entry:
            last_num = int(last_entry.entry_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{entry_prefix}{new_num:03d}"

    def post_invoice_to_gl(
        self,
        invoice: CustomerInvoice,
        user_id: Optional[int] = None,
        auto_post: bool = True
    ) -> JournalEntry:
        """
        Create GL journal entry when invoice is sent to customer

        Journal Entry:
        DR: Accounts Receivable (1200)          $total_amount
            CR: Revenue Account(s)                  $line_item_amounts
            CR: Sales Tax Payable                   $tax_amount (if applicable)

        Args:
            invoice: The customer invoice being sent
            user_id: User creating the entry
            auto_post: If True, automatically post the entry (default: True for automation)

        Returns:
            The created JournalEntry
        """
        if invoice.journal_entry_id:
            raise ValueError(f"Invoice {invoice.invoice_number} already has a journal entry")

        # Validate fiscal period
        fiscal_period = self._get_fiscal_period(invoice.invoice_date)
        if not fiscal_period:
            raise ValueError(
                f"No open fiscal period found for invoice date {invoice.invoice_date}. "
                "Please create an open fiscal period before posting invoices."
            )

        # Get AR account
        ar_account = self._get_ar_account()

        # Generate entry number
        entry_number = self._generate_entry_number(invoice.invoice_date, prefix="AR-INV")

        # Create journal entry
        journal_entry = JournalEntry(
            entry_number=entry_number,
            entry_date=invoice.invoice_date,
            description=f"Customer Invoice {invoice.invoice_number} - {invoice.customer.name if invoice.customer else 'Unknown'}",
            reference_type="CUSTOMER_INVOICE",
            reference_id=invoice.id,
            location_id=invoice.area_id,
            created_by=user_id,
            status=JournalEntryStatus.POSTED if auto_post else JournalEntryStatus.DRAFT
        )

        if auto_post:
            journal_entry.posted_at = datetime.utcnow()
            journal_entry.approved_by = user_id

        self.db.add(journal_entry)
        self.db.flush()  # Get journal entry ID

        # Debit: Accounts Receivable (Total invoice amount)
        ar_line = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=ar_account.id,
            area_id=invoice.area_id,
            debit_amount=invoice.total_amount,
            credit_amount=Decimal('0.00'),
            description=f"Invoice {invoice.invoice_number}"
        )
        self.db.add(ar_line)

        # Credit: Revenue accounts (per line item)
        for line_item in invoice.line_items:
            # Amount is net of discounts (after line discount but before tax)
            net_amount = line_item.amount - line_item.discount_amount

            revenue_line = JournalEntryLine(
                journal_entry_id=journal_entry.id,
                account_id=line_item.account_id,  # Revenue account from line item
                area_id=line_item.area_id or invoice.area_id,
                debit_amount=Decimal('0.00'),
                credit_amount=net_amount,
                description=line_item.description or f"Invoice {invoice.invoice_number}"
            )
            self.db.add(revenue_line)

        # Credit: Sales Tax Payable (if applicable)
        if invoice.tax_amount > 0:
            # Find Sales Tax Payable account
            tax_account = self.db.query(Account).filter(
                Account.account_number == "2150"  # Standard sales tax payable account
            ).first()

            if not tax_account:
                # Try to find by account type or name
                tax_account = self.db.query(Account).filter(
                    Account.account_name.ilike("%tax%payable%")
                ).first()

            if tax_account:
                tax_line = JournalEntryLine(
                    journal_entry_id=journal_entry.id,
                    account_id=tax_account.id,
                    area_id=invoice.area_id,
                    debit_amount=Decimal('0.00'),
                    credit_amount=invoice.tax_amount,
                    description=f"Sales Tax - Invoice {invoice.invoice_number}"
                )
                self.db.add(tax_line)
            else:
                logger.warning(
                    f"Sales Tax Payable account not found. Invoice {invoice.invoice_number} "
                    "has tax amount but no tax account configured."
                )

        # Link invoice to journal entry
        invoice.journal_entry_id = journal_entry.id

        self.db.commit()
        self.db.refresh(journal_entry)

        logger.info(
            f"Created journal entry {entry_number} for invoice {invoice.invoice_number} "
            f"(Total: ${invoice.total_amount})"
        )

        return journal_entry

    def post_payment_to_gl(
        self,
        payment: InvoicePayment,
        invoice: CustomerInvoice,
        user_id: Optional[int] = None,
        auto_post: bool = True
    ) -> JournalEntry:
        """
        Create GL journal entry when payment is received

        For regular payments:
        DR: Cash/Bank Account                   $amount
            CR: Accounts Receivable                 $amount

        For deposits/prepayments:
        DR: Cash/Bank Account                   $amount
            CR: Customer Deposits (Liability)       $amount

        Args:
            payment: The invoice payment being recorded
            invoice: The associated invoice
            user_id: User creating the entry
            auto_post: If True, automatically post the entry (default: True for automation)

        Returns:
            The created JournalEntry
        """
        if payment.journal_entry_id:
            raise ValueError(f"Payment {payment.id} already has a journal entry")

        # Validate fiscal period
        fiscal_period = self._get_fiscal_period(payment.payment_date)
        if not fiscal_period:
            raise ValueError(
                f"No open fiscal period found for payment date {payment.payment_date}. "
                "Please create an open fiscal period before posting payments."
            )

        # Get accounts
        bank_account = payment.bank_account
        if not bank_account:
            raise ValueError(f"Payment {payment.id} has no bank account specified")

        # Determine credit account (AR or Customer Deposits)
        if payment.is_deposit:
            # Prepayment/deposit goes to liability account
            credit_account = self._get_customer_deposits_account()
            description_suffix = "Deposit/Prepayment"
        else:
            # Regular payment reduces AR
            credit_account = self._get_ar_account()
            description_suffix = "Payment"

        # Generate entry number
        entry_number = self._generate_entry_number(payment.payment_date, prefix="AR-PMT")

        # Create journal entry
        journal_entry = JournalEntry(
            entry_number=entry_number,
            entry_date=payment.payment_date,
            description=f"Customer Payment - Invoice {invoice.invoice_number} - {description_suffix} ({payment.payment_method})",
            reference_type="INVOICE_PAYMENT",
            reference_id=payment.id,
            location_id=invoice.area_id,
            created_by=user_id,
            status=JournalEntryStatus.POSTED if auto_post else JournalEntryStatus.DRAFT
        )

        if auto_post:
            journal_entry.posted_at = datetime.utcnow()
            journal_entry.approved_by = user_id

        self.db.add(journal_entry)
        self.db.flush()  # Get journal entry ID

        # Debit: Cash/Bank Account
        bank_line = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=bank_account.id,
            area_id=invoice.area_id,
            debit_amount=payment.amount,
            credit_amount=Decimal('0.00'),
            description=f"Payment {payment.reference_number or ''} - {payment.payment_method}"
        )
        self.db.add(bank_line)

        # Credit: AR or Customer Deposits
        credit_line = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=credit_account.id,
            area_id=invoice.area_id,
            debit_amount=Decimal('0.00'),
            credit_amount=payment.amount,
            description=f"Invoice {invoice.invoice_number} - {description_suffix}"
        )
        self.db.add(credit_line)

        # Link payment to journal entry
        payment.journal_entry_id = journal_entry.id

        self.db.commit()
        self.db.refresh(journal_entry)

        logger.info(
            f"Created journal entry {entry_number} for payment on invoice {invoice.invoice_number} "
            f"(Amount: ${payment.amount}, Method: {payment.payment_method})"
        )

        return journal_entry

    def reverse_invoice_entry(
        self,
        invoice: CustomerInvoice,
        reversal_date: date,
        user_id: Optional[int] = None,
        reason: str = "Invoice voided"
    ) -> JournalEntry:
        """
        Reverse the GL entry for a voided invoice

        Creates a reversing entry that debits revenue and credits AR

        Args:
            invoice: The invoice being voided
            reversal_date: Date for the reversal entry
            user_id: User creating the reversal
            reason: Reason for reversal

        Returns:
            The reversal JournalEntry
        """
        if not invoice.journal_entry_id:
            raise ValueError(f"Invoice {invoice.invoice_number} has no journal entry to reverse")

        original_entry = self.db.query(JournalEntry).filter(
            JournalEntry.id == invoice.journal_entry_id
        ).first()

        if not original_entry:
            raise ValueError(f"Original journal entry {invoice.journal_entry_id} not found")

        if original_entry.status == JournalEntryStatus.REVERSED:
            raise ValueError(f"Journal entry {original_entry.entry_number} is already reversed")

        # Validate fiscal period
        fiscal_period = self._get_fiscal_period(reversal_date)
        if not fiscal_period:
            raise ValueError(
                f"No open fiscal period found for reversal date {reversal_date}"
            )

        # Generate entry number
        entry_number = self._generate_entry_number(reversal_date, prefix="AR-REV")

        # Create reversal entry
        reversal_entry = JournalEntry(
            entry_number=entry_number,
            entry_date=reversal_date,
            description=f"REVERSAL of {original_entry.entry_number}: {reason}",
            reference_type="REVERSAL",
            reference_id=original_entry.id,
            location_id=original_entry.location_id,
            created_by=user_id,
            status=JournalEntryStatus.POSTED,
            posted_at=datetime.utcnow(),
            approved_by=user_id
        )

        self.db.add(reversal_entry)
        self.db.flush()

        # Create reversal lines (swap debits and credits)
        for line in original_entry.lines:
            reversal_line = JournalEntryLine(
                journal_entry_id=reversal_entry.id,
                account_id=line.account_id,
                area_id=line.area_id,
                debit_amount=line.credit_amount,  # Swap
                credit_amount=line.debit_amount,  # Swap
                description=f"Reversal: {reason}"
            )
            self.db.add(reversal_line)

        # Mark original as reversed
        original_entry.status = JournalEntryStatus.REVERSED

        self.db.commit()
        self.db.refresh(reversal_entry)

        logger.info(
            f"Created reversal entry {entry_number} for invoice {invoice.invoice_number} "
            f"(Original: {original_entry.entry_number})"
        )

        return reversal_entry
