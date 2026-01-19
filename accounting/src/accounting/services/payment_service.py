"""
Payment service layer - orchestrates payment creation, processing, and management
"""
import os
import logging
from decimal import Decimal
from datetime import date, datetime
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from accounting.models.payment import (
    Payment, PaymentApplication, CheckBatch, ACHBatch,
    CheckNumberRegistry, PaymentDiscount, PaymentSchedule,
    PaymentMethod, PaymentStatus
)
from accounting.models.vendor_bill import VendorBill
from accounting.models.vendor import Vendor
from accounting.models.bank_account import BankAccount
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.models.account import Account
from accounting.schemas.payment import PaymentCreate, BatchPaymentRequest
from accounting.services.check_printer import CheckPrinter
from accounting.services.ach_generator import ACHGenerator

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for payment operations"""

    def __init__(self, db: Session):
        self.db = db

    def create_payment(
        self,
        payment_data: PaymentCreate,
        user_id: int
    ) -> Payment:
        """
        Create a new payment

        Args:
            payment_data: Payment creation data
            user_id: User creating the payment

        Returns:
            Created Payment object
        """
        # Calculate net amount
        net_amount = payment_data.amount - payment_data.discount_amount

        # Generate payment number
        payment_number = self._generate_payment_number(payment_data.payment_method)

        # Assign check number if needed
        check_number = None
        if payment_data.payment_method == PaymentMethod.CHECK:
            if payment_data.check_number:
                check_number = payment_data.check_number
            else:
                check_number = self._get_next_check_number(payment_data.bank_account_id)

        # Create payment record
        payment = Payment(
            payment_number=payment_number,
            payment_method=payment_data.payment_method,
            payment_date=payment_data.payment_date,
            vendor_id=payment_data.vendor_id,
            area_id=payment_data.area_id,
            bank_account_id=payment_data.bank_account_id,
            amount=payment_data.amount,
            discount_amount=payment_data.discount_amount,
            net_amount=net_amount,
            status=PaymentStatus.DRAFT,
            check_number=check_number,
            scheduled_date=payment_data.scheduled_date,
            memo=payment_data.memo,
            notes=payment_data.notes,
            created_by=user_id
        )

        self.db.add(payment)
        self.db.flush()

        # Create payment applications (link to bills)
        for app_data in payment_data.applications:
            app = PaymentApplication(
                payment_id=payment.id,
                vendor_bill_id=app_data.vendor_bill_id,
                amount_applied=app_data.amount_applied,
                discount_applied=app_data.discount_applied
            )
            self.db.add(app)

            # Update bill paid amount with pessimistic locking to prevent race conditions
            # when multiple concurrent payments are applied to the same bill
            bill = self.db.query(VendorBill).filter(
                VendorBill.id == app_data.vendor_bill_id
            ).with_for_update().first()
            if bill:
                bill.paid_amount = (bill.paid_amount or Decimal('0')) + app_data.amount_applied
                if bill.paid_amount >= bill.total_amount:
                    bill.status = 'PAID'
                elif bill.paid_amount > 0:
                    bill.status = 'PARTIALLY_PAID'

        # Register check number if applicable
        if check_number:
            self._register_check_number(payment_data.bank_account_id, check_number, payment.id)

        # Create journal entry
        journal_entry = self._create_payment_journal_entry(payment, user_id)
        if journal_entry:
            payment.journal_entry_id = journal_entry.id

        self.db.commit()
        self.db.refresh(payment)

        logger.info(f"Created payment {payment.payment_number} for vendor {payment.vendor_id}")
        return payment

    def create_batch_payment(
        self,
        batch_request: BatchPaymentRequest,
        user_id: int
    ) -> Dict:
        """
        Create batch payment for multiple bills

        Args:
            batch_request: Batch payment request data
            user_id: User creating the batch

        Returns:
            Dictionary with batch information and created payments
        """
        # Get bills
        bills = self.db.query(VendorBill).filter(
            VendorBill.id.in_(batch_request.bill_ids)
        ).all()

        if not bills:
            raise ValueError("No bills found for batch payment")

        # Group bills by vendor
        bills_by_vendor = {}
        for bill in bills:
            if bill.vendor_id not in bills_by_vendor:
                bills_by_vendor[bill.vendor_id] = []
            bills_by_vendor[bill.vendor_id].append(bill)

        # Create payments (one per vendor)
        payments = []
        total_amount = Decimal('0')

        for vendor_id, vendor_bills in bills_by_vendor.items():
            # Calculate total for this vendor
            vendor_total = sum(
                (bill.total_amount - (bill.paid_amount or Decimal('0')))
                for bill in vendor_bills
            )

            # Create payment applications
            applications = []
            for bill in vendor_bills:
                outstanding = bill.total_amount - (bill.paid_amount or Decimal('0'))
                applications.append({
                    'vendor_bill_id': bill.id,
                    'amount_applied': outstanding,
                    'discount_applied': Decimal('0')
                })

            # Create payment data
            payment_create = PaymentCreate(
                payment_method=batch_request.payment_method,
                payment_date=batch_request.payment_date,
                vendor_id=vendor_id,
                area_id=batch_request.area_id,
                bank_account_id=batch_request.bank_account_id,
                amount=vendor_total,
                discount_amount=Decimal('0'),
                applications=applications,
                memo=batch_request.memo_template
            )

            payment = self.create_payment(payment_create, user_id)
            payments.append(payment)
            total_amount += vendor_total

        # Create batch record if check or ACH
        batch_id = None
        if batch_request.payment_method == PaymentMethod.CHECK:
            batch = self._create_check_batch(payments, batch_request, user_id)
            batch_id = batch.id
        elif batch_request.payment_method == PaymentMethod.ACH:
            batch = self._create_ach_batch(payments, batch_request, user_id)
            batch_id = batch.id

        return {
            'payment_count': len(payments),
            'total_amount': total_amount,
            'payment_ids': [p.id for p in payments],
            'batch_id': batch_id
        }

    def print_checks(
        self,
        check_batch_id: int,
        user_id: int,
        output_dir: str = "/tmp"
    ) -> str:
        """
        Generate PDF for check batch

        Args:
            check_batch_id: ID of check batch to print
            user_id: User printing checks
            output_dir: Directory for PDF output

        Returns:
            Path to generated PDF
        """
        # Get batch and payments
        batch = self.db.query(CheckBatch).filter(CheckBatch.id == check_batch_id).first()
        if not batch:
            raise ValueError(f"Check batch {check_batch_id} not found")

        payments = self.db.query(Payment).filter(
            Payment.check_batch_id == check_batch_id
        ).order_by(Payment.check_number).all()

        # Get company and bank info
        bank_account = self.db.query(BankAccount).filter(
            BankAccount.id == batch.bank_account_id
        ).first()

        company_info = {
            'legal_name': bank_account.area.legal_name if bank_account.area else 'Company Name',
            'address_line1': bank_account.area.address_line1 if bank_account.area else '',
            'city': bank_account.area.city if bank_account.area else '',
            'state': bank_account.area.state if bank_account.area else '',
            'zip_code': bank_account.area.zip_code if bank_account.area else ''
        }

        bank_info = {
            'bank_name': bank_account.institution_name,
            'bank_address': '',
            'routing_number': bank_account.routing_number,
            'account_number': bank_account.account_number
        }

        # Prepare check data
        checks_data = []
        for payment in payments:
            # Get vendor
            vendor = self.db.query(Vendor).filter(Vendor.id == payment.vendor_id).first()

            # Get invoice details
            invoices = []
            for app in payment.applications:
                bill = self.db.query(VendorBill).filter(VendorBill.id == app.vendor_bill_id).first()
                if bill:
                    invoices.append({
                        'invoice_number': bill.bill_number,
                        'invoice_date': bill.bill_date,
                        'amount': app.amount_applied,
                        'discount': app.discount_applied
                    })

            # Build payee address
            payee_address = {}
            if vendor:
                payee_address = {
                    'address_line1': vendor.address_line1 or '',
                    'address_line2': vendor.address_line2 or '',
                    'city': vendor.city or '',
                    'state': vendor.state or '',
                    'zip_code': vendor.zip_code or '',
                    'country': vendor.country or ''
                }

            check_data = {
                'check_number': payment.check_number,
                'payment_date': payment.payment_date,
                'payee_name': vendor.name if vendor else '',
                'payee_address': payee_address,
                'amount': payment.net_amount,
                'memo': payment.memo or ', '.join([inv['invoice_number'] for inv in invoices[:3]]),
                'bank_account_name': bank_account.account_name,
                'invoices': invoices
            }
            checks_data.append(check_data)

        # Generate PDF
        pdf_filename = f"checks_{batch.batch_number}.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)

        printer = CheckPrinter(pdf_path)
        printer.generate_checks(checks_data, company_info, bank_info)

        # Update batch
        batch.pdf_file_path = pdf_path
        batch.status = 'PRINTED'
        batch.printed_at = datetime.now()
        batch.printed_by = user_id

        # Update payment statuses
        for payment in payments:
            payment.status = PaymentStatus.PRINTED

        self.db.commit()

        logger.info(f"Printed {len(checks_data)} checks for batch {batch.batch_number}")
        return pdf_path

    def generate_ach_file(
        self,
        ach_batch_id: int,
        user_id: int,
        output_dir: str = "/tmp"
    ) -> str:
        """
        Generate NACHA ACH file for batch

        Args:
            ach_batch_id: ID of ACH batch
            user_id: User generating file
            output_dir: Directory for file output

        Returns:
            Path to generated ACH file
        """
        # Get batch and payments
        batch = self.db.query(ACHBatch).filter(ACHBatch.id == ach_batch_id).first()
        if not batch:
            raise ValueError(f"ACH batch {ach_batch_id} not found")

        payments = self.db.query(Payment).filter(
            Payment.ach_batch_id == ach_batch_id
        ).all()

        # Get bank account
        bank_account = self.db.query(BankAccount).filter(
            BankAccount.id == batch.bank_account_id
        ).first()

        # Prepare company info
        company_info = {
            'legal_name': bank_account.area.legal_name if bank_account.area else 'Company',
            'company_id': bank_account.area.ein if bank_account.area else '0000000000'
        }

        bank_info = {
            'bank_name': bank_account.institution_name,
            'routing_number': bank_account.routing_number
        }

        batch_info = {
            'batch_date': batch.batch_date,
            'effective_date': batch.effective_date
        }

        # Prepare payment data
        payments_data = []
        for i, payment in enumerate(payments, 1):
            vendor = self.db.query(Vendor).filter(Vendor.id == payment.vendor_id).first()

            payment_data = {
                'vendor_name': vendor.name if vendor else '',
                'vendor_routing': vendor.bank_routing_number if vendor and vendor.bank_routing_number else '000000000',
                'vendor_account': vendor.bank_account_number if vendor and vendor.bank_account_number else '',
                'amount': payment.net_amount,
                'payment_number': payment.payment_number,
                'reference': payment.memo or payment.payment_number,
                'company_routing': bank_account.routing_number,
                'trace_sequence': i
            }
            payments_data.append(payment_data)

        # Generate ACH file
        ach_filename = f"ach_{batch.batch_number}.txt"
        ach_path = os.path.join(output_dir, ach_filename)

        generator = ACHGenerator(ach_path)
        generator.generate_ach_file(payments_data, company_info, bank_info, batch_info)

        # Update batch
        batch.nacha_file_path = ach_path
        batch.status = 'GENERATED'
        batch.generated_at = datetime.now()
        batch.generated_by = user_id

        # Update payment statuses
        for payment in payments:
            payment.status = PaymentStatus.SUBMITTED

        self.db.commit()

        logger.info(f"Generated ACH file for batch {batch.batch_number}")
        return ach_path

    def void_payment(
        self,
        payment_id: int,
        void_reason: str,
        user_id: int
    ) -> Payment:
        """Void a payment"""
        payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status == PaymentStatus.VOIDED:
            raise ValueError("Payment is already voided")

        # Reverse bill payments with pessimistic locking to prevent race conditions
        for app in payment.applications:
            bill = self.db.query(VendorBill).filter(
                VendorBill.id == app.vendor_bill_id
            ).with_for_update().first()
            if bill:
                bill.paid_amount = (bill.paid_amount or Decimal('0')) - app.amount_applied
                if bill.paid_amount == 0:
                    bill.status = 'APPROVED'
                elif bill.paid_amount < bill.total_amount:
                    bill.status = 'PARTIALLY_PAID'

        # Update payment
        payment.status = PaymentStatus.VOIDED
        payment.void_reason = void_reason
        payment.voided_date = date.today()
        payment.voided_by = user_id

        # Update check registry if check payment
        if payment.check_number:
            registry = self.db.query(CheckNumberRegistry).filter(
                and_(
                    CheckNumberRegistry.bank_account_id == payment.bank_account_id,
                    CheckNumberRegistry.check_number == payment.check_number
                )
            ).first()
            if registry:
                registry.status = 'VOIDED'

        # Reverse journal entry (create reversing entry)
        if payment.journal_entry_id:
            self._reverse_journal_entry(payment.journal_entry_id, user_id)

        self.db.commit()
        self.db.refresh(payment)

        logger.info(f"Voided payment {payment.payment_number}")
        return payment

    # Helper methods

    def _generate_payment_number(self, payment_method: PaymentMethod) -> str:
        """Generate unique payment number"""
        prefix = {
            PaymentMethod.CHECK: 'CHK',
            PaymentMethod.ACH: 'ACH',
            PaymentMethod.WIRE: 'WIRE',
            PaymentMethod.CREDIT_CARD: 'CC',
        }.get(payment_method, 'PAY')

        # Get next sequence number
        last_payment = self.db.query(Payment).filter(
            Payment.payment_number.like(f"{prefix}%")
        ).order_by(Payment.id.desc()).first()

        if last_payment:
            last_num = int(last_payment.payment_number[3:])
            next_num = last_num + 1
        else:
            next_num = 1

        return f"{prefix}{next_num:07d}"

    def _get_next_check_number(self, bank_account_id: int) -> int:
        """Get next available check number for bank account"""
        last_check = self.db.query(CheckNumberRegistry).filter(
            CheckNumberRegistry.bank_account_id == bank_account_id
        ).order_by(CheckNumberRegistry.check_number.desc()).first()

        if last_check:
            return last_check.check_number + 1
        else:
            # Get starting check number from bank account settings (if field exists)
            bank_account = self.db.query(BankAccount).filter(BankAccount.id == bank_account_id).first()
            starting_num = getattr(bank_account, 'starting_check_number', None) if bank_account else None
            return starting_num if starting_num else 1001

    def _register_check_number(self, bank_account_id: int, check_number: int, payment_id: int):
        """Register check number in registry"""
        registry = CheckNumberRegistry(
            bank_account_id=bank_account_id,
            check_number=check_number,
            status='USED',
            payment_id=payment_id,
            used_date=date.today()
        )
        self.db.add(registry)

    def _create_payment_journal_entry(self, payment: Payment, user_id: int) -> Optional[JournalEntry]:
        """Create journal entry for payment"""
        # DR: Accounts Payable, CR: Cash
        cash_account = self.db.query(Account).filter(
            Account.account_type == 'ASSET',
            Account.account_name.ilike('%cash%')
        ).first()

        ap_account = self.db.query(Account).filter(
            Account.account_type == 'LIABILITY',
            Account.account_name.ilike('%accounts payable%')
        ).first()

        if not cash_account or not ap_account:
            logger.warning("Could not find cash or AP accounts for journal entry")
            return None

        je = JournalEntry(
            entry_date=payment.payment_date,
            description=f"Payment {payment.payment_number} to vendor",
            status='POSTED',
            created_by=user_id
        )
        self.db.add(je)
        self.db.flush()

        # Debit AP
        debit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=1,
            account_id=ap_account.id,
            area_id=payment.area_id,
            description=f"Payment {payment.payment_number}",
            debit_amount=payment.net_amount,
            credit_amount=Decimal('0')
        )
        self.db.add(debit_line)

        # Credit Cash
        credit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=2,
            account_id=cash_account.id,
            area_id=payment.area_id,
            description=f"Payment {payment.payment_number}",
            debit_amount=Decimal('0'),
            credit_amount=payment.net_amount
        )
        self.db.add(credit_line)

        return je

    def _create_check_batch(self, payments: List[Payment], batch_request: BatchPaymentRequest, user_id: int) -> CheckBatch:
        """Create check batch record"""
        batch_number = f"CHK-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        check_numbers = [p.check_number for p in payments if p.check_number]

        batch = CheckBatch(
            batch_number=batch_number,
            batch_date=batch_request.payment_date,
            bank_account_id=batch_request.bank_account_id,
            starting_check_number=min(check_numbers) if check_numbers else 0,
            ending_check_number=max(check_numbers) if check_numbers else 0,
            check_count=len(payments),
            total_amount=sum(p.net_amount for p in payments),
            status='DRAFT'
        )
        self.db.add(batch)
        self.db.flush()

        # Link payments to batch
        for payment in payments:
            payment.check_batch_id = batch.id

        return batch

    def _create_ach_batch(self, payments: List[Payment], batch_request: BatchPaymentRequest, user_id: int) -> ACHBatch:
        """Create ACH batch record"""
        batch_number = f"ACH-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        batch = ACHBatch(
            batch_number=batch_number,
            batch_date=batch_request.payment_date,
            bank_account_id=batch_request.bank_account_id,
            effective_date=batch_request.effective_date or batch_request.payment_date,
            payment_count=len(payments),
            total_amount=sum(p.net_amount for p in payments),
            status='DRAFT'
        )
        self.db.add(batch)
        self.db.flush()

        # Link payments to batch
        for payment in payments:
            payment.ach_batch_id = batch.id

        return batch

    def _reverse_journal_entry(self, je_id: int, user_id: int):
        """Create reversing journal entry"""
        original = self.db.query(JournalEntry).filter(JournalEntry.id == je_id).first()
        if not original:
            return

        reversing = JournalEntry(
            entry_date=date.today(),
            description=f"REVERSAL: {original.description}",
            status='POSTED',
            created_by=user_id
        )
        self.db.add(reversing)
        self.db.flush()

        # Reverse all lines
        for line in original.lines:
            reversed_line = JournalEntryLine(
                journal_entry_id=reversing.id,
                line_number=line.line_number,
                account_id=line.account_id,
                area_id=line.area_id,
                description=f"REVERSAL: {line.description}",
                debit_amount=line.credit_amount,  # Swap debit/credit
                credit_amount=line.debit_amount
            )
            self.db.add(reversed_line)
