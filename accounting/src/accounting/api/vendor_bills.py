"""
API endpoints for Vendor Bills (Accounts Payable)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.vendor_bill import VendorBill, VendorBillLine, BillPayment, BillStatus, PaymentMethod
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account
from accounting.models.area import Area
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus
from accounting.schemas.vendor_bill import (
    VendorBillCreate,
    VendorBillUpdate,
    VendorBillResponse,
    VendorBillListResponse,
    BillApprovalRequest,
    BillPaymentCreate,
    BillPaymentResponse,
    APAgingReportResponse,
    AgingBucket,
    VendorAgingDetail,
)
from accounting.api.auth import require_auth, require_admin
from accounting.services.vendor_service import VendorService

router = APIRouter(prefix="/api/vendor-bills", tags=["vendor_bills"])

# Accounts Payable account ID (2100 - Account Payable)
AP_ACCOUNT_ID = 17


def validate_fiscal_period(db: Session, entry_date: date, action: str = "create bill"):
    """Validate that a fiscal period exists and is open for the given date"""
    period = db.query(FiscalPeriod).filter(
        FiscalPeriod.start_date <= entry_date,
        FiscalPeriod.end_date >= entry_date
    ).first()

    if not period:
        raise HTTPException(
            status_code=400,
            detail=f"No fiscal period found for date {entry_date}. Please create fiscal periods before attempting to {action}."
        )

    if period.status == FiscalPeriodStatus.CLOSED:
        raise HTTPException(
            status_code=400,
            detail=f"Fiscal period {period.period_name} is closed. Cannot {action}."
        )

    if period.status == FiscalPeriodStatus.LOCKED:
        raise HTTPException(
            status_code=400,
            detail=f"Fiscal period {period.period_name} is locked. Cannot {action}."
        )

    return period


def create_bill_journal_entry(bill: VendorBill, db: Session) -> JournalEntry:
    """
    Create journal entry when bill is approved
    DR: Expense accounts (from line items)
    CR: Accounts Payable
    """
    # Generate unique entry number
    today = date.today()
    prefix = f"AP-{today.strftime('%Y%m%d')}-"

    # Find the highest sequence number for today
    max_entry = db.query(JournalEntry.entry_number).filter(
        JournalEntry.entry_number.like(f"{prefix}%")
    ).order_by(JournalEntry.entry_number.desc()).first()

    if max_entry and max_entry[0]:
        # Extract sequence number from last entry
        last_seq = int(max_entry[0].split('-')[-1])
        entry_number = f"{prefix}{last_seq + 1:04d}"
    else:
        entry_number = f"{prefix}0001"

    # Create journal entry
    je = JournalEntry(
        entry_date=bill.bill_date,
        entry_number=entry_number,
        description=f"AP Bill: {bill.vendor_name} - {bill.bill_number}",
        reference_type="VENDOR_BILL",
        reference_id=bill.id,
        location_id=bill.area_id,
        created_by=bill.approved_by or bill.created_by,
        status=JournalEntryStatus.POSTED,
        posted_at=datetime.now()
    )
    db.add(je)
    db.flush()  # Get JE ID

    # Add debit lines for each bill line item (Expenses)
    # Note: Credit line items (negative amounts) are recorded as credits, not negative debits
    line_number = 1
    for bill_line in bill.line_items:
        line_amount = bill_line.amount + bill_line.tax_amount

        # Handle credit items (negative amounts) - record as credit instead of negative debit
        if line_amount >= 0:
            debit_amt = line_amount
            credit_amt = Decimal('0.00')
        else:
            debit_amt = Decimal('0.00')
            credit_amt = abs(line_amount)

        je_line = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=bill_line.account_id,
            area_id=bill_line.area_id or bill.area_id,
            debit_amount=debit_amt,
            credit_amount=credit_amt,
            description=bill_line.description or f"{bill.vendor_name} - {bill.bill_number}",
            line_number=line_number
        )
        db.add(je_line)
        line_number += 1

    # Add credit line for Accounts Payable
    je_line = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=AP_ACCOUNT_ID,  # 2100 - Account Payable
        area_id=bill.area_id,
        debit_amount=Decimal('0.00'),
        credit_amount=bill.total_amount,
        description=f"AP: {bill.vendor_name} - {bill.bill_number}",
        line_number=line_number
    )
    db.add(je_line)

    return je


def create_payment_journal_entry(payment: BillPayment, bill: VendorBill, db: Session) -> JournalEntry:
    """
    Create journal entry when payment is recorded
    DR: Accounts Payable
    CR: Bank/Cash account
    """
    # Generate unique entry number
    today = date.today()
    prefix = f"PMT-{today.strftime('%Y%m%d')}-"

    # Find the highest sequence number for today
    max_entry = db.query(JournalEntry.entry_number).filter(
        JournalEntry.entry_number.like(f"{prefix}%")
    ).order_by(JournalEntry.entry_number.desc()).first()

    if max_entry and max_entry[0]:
        # Extract sequence number from last entry
        last_seq = int(max_entry[0].split('-')[-1])
        entry_number = f"{prefix}{last_seq + 1:04d}"
    else:
        entry_number = f"{prefix}0001"

    # Create journal entry
    je = JournalEntry(
        entry_date=payment.payment_date,
        entry_number=entry_number,
        description=f"Payment: {bill.vendor_name} - {bill.bill_number}",
        reference_type="BILL_PAYMENT",
        reference_id=payment.id,
        location_id=bill.area_id,
        created_by=payment.created_by,
        status=JournalEntryStatus.POSTED,
        posted_at=datetime.now()
    )
    db.add(je)
    db.flush()  # Get JE ID

    # DR: Accounts Payable (reduce liability)
    je_line = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=AP_ACCOUNT_ID,  # 2100 - Account Payable
        area_id=bill.area_id,
        debit_amount=payment.amount,
        credit_amount=Decimal('0.00'),
        description=f"Payment: {bill.vendor_name} - {bill.bill_number}",
        line_number=1
    )
    db.add(je_line)

    # CR: Bank/Cash account (reduce asset)
    je_line = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=payment.bank_account_id,
        area_id=bill.area_id,
        debit_amount=Decimal('0.00'),
        credit_amount=payment.amount,
        description=f"Payment to {bill.vendor_name} - {payment.payment_method}",
        line_number=2
    )
    db.add(je_line)

    return je


@router.post("/", response_model=VendorBillResponse, status_code=201)
def create_vendor_bill(
    bill_data: VendorBillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Create a new vendor bill
    - Creates bill header and line items
    - Status defaults to DRAFT
    - Validates line items sum to total
    """

    # Validate area exists if provided
    if bill_data.area_id:
        area = db.query(Area).filter(Area.id == bill_data.area_id).first()
        if not area:
            raise HTTPException(status_code=404, detail=f"Area {bill_data.area_id} not found")

    # Note: Fiscal period validation is done when approving, not when creating drafts
    # This allows users to enter bills before fiscal periods are set up

    # Check for duplicate bill number for this vendor
    existing_bill = db.query(VendorBill).filter(
        VendorBill.bill_number == bill_data.bill_number,
        VendorBill.vendor_id == bill_data.vendor_id,
        VendorBill.status != BillStatus.VOID  # Allow re-entering voided bills
    ).first()
    if existing_bill:
        raise HTTPException(
            status_code=400,
            detail=f"Bill number '{bill_data.bill_number}' already exists for this vendor (Bill ID: {existing_bill.id})"
        )

    # Validate line items if provided
    if bill_data.line_items:
        for line in bill_data.line_items:
            # Validate account exists
            account = db.query(Account).filter(Account.id == line.account_id).first()
            if not account:
                raise HTTPException(status_code=404, detail=f"Account {line.account_id} not found")

            # Validate area if provided
            if line.area_id:
                area = db.query(Area).filter(Area.id == line.area_id).first()
                if not area:
                    raise HTTPException(status_code=404, detail=f"Area {line.area_id} not found")

        # Validate line items sum to totals
        lines_subtotal = sum(line.amount for line in bill_data.line_items)
        lines_tax = sum(line.tax_amount for line in bill_data.line_items)

        # Allow small rounding differences (< 1 cent)
        if abs(lines_subtotal - bill_data.subtotal) > Decimal('0.01'):
            raise HTTPException(
                status_code=400,
                detail=f"Line items subtotal ({lines_subtotal}) does not match bill subtotal ({bill_data.subtotal})"
            )
        if abs(lines_tax - bill_data.tax_amount) > Decimal('0.01'):
            raise HTTPException(
                status_code=400,
                detail=f"Line items tax ({lines_tax}) does not match bill tax ({bill_data.tax_amount})"
            )

    # Create bill
    bill = VendorBill(
        vendor_name=bill_data.vendor_name,
        vendor_id=bill_data.vendor_id,
        bill_number=bill_data.bill_number,
        bill_date=bill_data.bill_date,
        due_date=bill_data.due_date,
        received_date=bill_data.received_date,
        subtotal=bill_data.subtotal,
        tax_amount=bill_data.tax_amount,
        total_amount=bill_data.total_amount,
        area_id=bill_data.area_id,
        is_1099_eligible=bill_data.is_1099_eligible,
        reference_number=bill_data.reference_number,
        description=bill_data.description,
        notes=bill_data.notes,
        status=BillStatus.DRAFT,
        created_by=current_user.id,
    )

    db.add(bill)
    db.flush()  # Get bill ID

    # Create line items
    for idx, line_data in enumerate(bill_data.line_items, start=1):
        line = VendorBillLine(
            bill_id=bill.id,
            account_id=line_data.account_id,
            area_id=line_data.area_id,
            description=line_data.description,
            quantity=line_data.quantity,
            unit_price=line_data.unit_price,
            amount=line_data.amount,
            is_taxable=line_data.is_taxable,
            tax_amount=line_data.tax_amount,
            line_number=line_data.line_number or idx,
        )
        db.add(line)

    db.commit()
    db.refresh(bill)

    return bill


@router.get("/", response_model=List[VendorBillListResponse])
def list_vendor_bills(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    vendor_name: Optional[str] = Query(None, description="Filter by vendor name (partial match)"),
    area_id: Optional[int] = Query(None, description="Filter by location/area"),
    status: Optional[BillStatus] = Query(None, description="Filter by bill status"),
    start_date: Optional[date] = Query(None, description="Filter bills on or after this date"),
    end_date: Optional[date] = Query(None, description="Filter bills on or before this date"),
    overdue_only: bool = Query(False, description="Show only overdue bills"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List vendor bills with filtering and pagination
    """
    query = db.query(VendorBill).options(
        joinedload(VendorBill.area),
        joinedload(VendorBill.creator)
    )

    # Apply filters
    if vendor_name:
        query = query.filter(VendorBill.vendor_name.ilike(f"%{vendor_name}%"))

    if area_id is not None:
        query = query.filter(VendorBill.area_id == area_id)

    if status is not None:
        query = query.filter(VendorBill.status == status)

    if start_date:
        query = query.filter(VendorBill.bill_date >= start_date)

    if end_date:
        query = query.filter(VendorBill.bill_date <= end_date)

    if overdue_only:
        today = date.today()
        query = query.filter(
            VendorBill.due_date < today,
            VendorBill.status.in_([BillStatus.APPROVED, BillStatus.PENDING_APPROVAL, BillStatus.PARTIALLY_PAID]),
            VendorBill.paid_amount < VendorBill.total_amount
        )

    # Order by bill date (newest first)
    query = query.order_by(VendorBill.bill_date.desc())

    bills = query.offset(skip).limit(limit).all()
    return bills


@router.get("/aging-report", response_model=APAgingReportResponse)
def get_ap_aging_report(
    as_of_date: Optional[str] = Query(None),
    area_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get AP Aging Report showing outstanding bills grouped by age
    - Buckets: 0-30, 31-60, 61-90, 90+ days
    - Grouped by vendor
    - Optionally filtered by area/location
    - As of specific date (defaults to today)
    """
    # Parse date string
    if as_of_date is None:
        report_date = date.today()
    else:
        try:
            report_date = date.fromisoformat(as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {as_of_date}. Use YYYY-MM-DD")

    # Build query for outstanding bills (APPROVED, PARTIALLY_PAID)
    # Filter for bills with outstanding balance (total_amount - paid_amount > 0)
    query = db.query(VendorBill).filter(
        VendorBill.status.in_([BillStatus.APPROVED, BillStatus.PARTIALLY_PAID]),
        VendorBill.total_amount > VendorBill.paid_amount
    )

    # Filter by area if specified
    area_name = None
    if area_id:
        area = db.query(Area).filter(Area.id == area_id).first()
        if area:
            area_name = area.name
        query = query.filter(VendorBill.area_id == area_id)

    # Get all outstanding bills
    bills = query.all()

    # Group by vendor and calculate aging buckets
    vendor_data = {}

    for bill in bills:
        vendor_key = bill.vendor_name
        if vendor_key not in vendor_data:
            vendor_data[vendor_key] = {
                'vendor_name': bill.vendor_name,
                'vendor_id': bill.vendor_id,
                'current': Decimal('0.00'),
                'days_31_60': Decimal('0.00'),
                'days_61_90': Decimal('0.00'),
                'over_90_days': Decimal('0.00'),
                'total': Decimal('0.00')
            }

        # Calculate days overdue (from due date)
        days_old = (report_date - bill.due_date).days
        balance = bill.balance_due

        # Assign to aging bucket
        if days_old <= 30:
            vendor_data[vendor_key]['current'] += balance
        elif days_old <= 60:
            vendor_data[vendor_key]['days_31_60'] += balance
        elif days_old <= 90:
            vendor_data[vendor_key]['days_61_90'] += balance
        else:
            vendor_data[vendor_key]['over_90_days'] += balance

        vendor_data[vendor_key]['total'] += balance

    # Convert to list and sort by vendor name
    vendors = [VendorAgingDetail(**data) for data in vendor_data.values()]
    vendors.sort(key=lambda v: v.vendor_name)

    # Calculate totals across all vendors
    totals = AgingBucket(
        current=sum(v.current for v in vendors),
        days_31_60=sum(v.days_31_60 for v in vendors),
        days_61_90=sum(v.days_61_90 for v in vendors),
        over_90_days=sum(v.over_90_days for v in vendors),
        total=sum(v.total for v in vendors)
    )

    return APAgingReportResponse(
        as_of_date=report_date,
        area_id=area_id,
        area_name=area_name,
        vendors=vendors,
        totals=totals
    )


@router.get("/{bill_id}", response_model=VendorBillResponse)
def get_vendor_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific vendor bill with all details including line items"""
    bill = db.query(VendorBill).options(
        joinedload(VendorBill.area),
        joinedload(VendorBill.line_items).joinedload(VendorBillLine.account),
        joinedload(VendorBill.line_items).joinedload(VendorBillLine.area),
        joinedload(VendorBill.creator),
        joinedload(VendorBill.approver),
        joinedload(VendorBill.payments)
    ).filter(VendorBill.id == bill_id).first()

    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    return bill


@router.put("/{bill_id}", response_model=VendorBillResponse)
def update_vendor_bill(
    bill_id: int,
    bill_data: VendorBillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Update a vendor bill
    - Only DRAFT bills can be fully edited
    - Approved/Paid bills have limited editable fields
    """
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    # Restrict editing of non-draft bills
    if bill.status not in [BillStatus.DRAFT, BillStatus.PENDING_APPROVAL]:
        # Only allow updating notes and reference_number for approved/paid bills
        allowed_fields = {'notes', 'reference_number'}
        provided_fields = {k for k, v in bill_data.model_dump(exclude_unset=True).items() if v is not None}
        if not provided_fields.issubset(allowed_fields):
            raise HTTPException(
                status_code=400,
                detail=f"Bill in {bill.status} status can only update: {', '.join(allowed_fields)}"
            )

    # Update fields
    for field, value in bill_data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(bill, field, value)

    db.commit()
    db.refresh(bill)

    return bill


@router.delete("/{bill_id}", status_code=204)
def delete_vendor_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Delete a vendor bill
    - Only DRAFT bills can be deleted
    - Other bills must be voided instead
    """
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    if bill.status != BillStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete bill in {bill.status} status. Use VOID instead."
        )

    db.delete(bill)
    db.commit()

    return None


@router.post("/{bill_id}/submit", response_model=VendorBillResponse)
def submit_bill_for_approval(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Submit a DRAFT bill for approval
    Changes status from DRAFT to PENDING_APPROVAL
    """
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    if bill.status != BillStatus.DRAFT:
        raise HTTPException(status_code=400, detail=f"Bill must be in DRAFT status to submit")

    # Validate bill has line items
    line_count = db.query(func.count(VendorBillLine.id)).filter(
        VendorBillLine.bill_id == bill_id
    ).scalar()

    if line_count == 0:
        raise HTTPException(status_code=400, detail="Bill must have at least one line item")

    bill.status = BillStatus.PENDING_APPROVAL
    db.commit()
    db.refresh(bill)

    return bill


@router.post("/{bill_id}/approve", response_model=VendorBillResponse)
def approve_bill(
    bill_id: int,
    approval_data: BillApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Approve or reject a bill
    - Creates journal entry if approved
    - Returns to DRAFT if rejected
    """
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    if bill.status != BillStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail=f"Bill must be PENDING_APPROVAL to approve/reject")

    if approval_data.approve:
        # Validate fiscal period is open for the bill date before creating journal entry
        validate_fiscal_period(db, bill.bill_date, "approve bill")

        # Approve bill
        bill.status = BillStatus.APPROVED
        bill.approved_by = current_user.id
        bill.approved_date = datetime.now()
        bill.approval_notes = approval_data.notes

        # Create journal entry for the bill
        # DR: Expense accounts (from line items)
        # CR: Accounts Payable
        try:
            # Load line items for JE creation
            bill = db.query(VendorBill).options(
                joinedload(VendorBill.line_items)
            ).filter(VendorBill.id == bill_id).first()

            # Set status again to ensure it's correct
            bill.status = BillStatus.APPROVED
            bill.approved_by = current_user.id
            bill.approved_date = datetime.now()

            journal_entry = create_bill_journal_entry(bill, db)

            # Add note about JE creation
            if bill.approval_notes:
                bill.approval_notes += f"\nJournal Entry Created: {journal_entry.entry_number}"
            else:
                bill.approval_notes = f"Journal Entry Created: {journal_entry.entry_number}"

            # Single commit for everything
            db.commit()
            db.refresh(bill)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating journal entry: {str(e)}")

    else:
        # Reject bill - return to DRAFT
        bill.status = BillStatus.DRAFT
        bill.approval_notes = f"Rejected: {approval_data.notes}" if approval_data.notes else "Rejected"
        db.commit()
        db.refresh(bill)

    return bill


@router.post("/{bill_id}/void", response_model=VendorBillResponse)
def void_bill(
    bill_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Void a bill
    - Can void bills in any status except already VOID
    - Cannot void bills with payments (must delete payments first)
    - Reverses the associated journal entry if one exists
    """
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    if bill.status == BillStatus.VOID:
        raise HTTPException(status_code=400, detail="Bill is already void")

    # Check for payments
    payment_count = db.query(func.count(BillPayment.id)).filter(
        BillPayment.bill_id == bill_id
    ).scalar()

    if payment_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot void bill with {payment_count} payment(s). Delete payments first."
        )

    # Mark the journal entry as REVERSED if one exists
    # Note: We just mark as REVERSED rather than creating a reversing entry.
    # REVERSED status excludes the entry from dashboard/report calculations.
    # Creating a reversing entry would offset ALL entries for those accounts
    # in the period, not just this specific entry.
    if bill.journal_entry_id:
        journal_entry = db.query(JournalEntry).filter(JournalEntry.id == bill.journal_entry_id).first()
        if journal_entry and journal_entry.status == JournalEntryStatus.POSTED:
            journal_entry.status = JournalEntryStatus.REVERSED

    bill.status = BillStatus.VOID
    void_note = f"\nVoided by {current_user.email} on {date.today()}"
    if notes:
        void_note += f": {notes}"
    bill.notes = (bill.notes or "") + void_note

    db.commit()
    db.refresh(bill)

    return bill


# Payment endpoints
@router.post("/{bill_id}/payments", response_model=BillPaymentResponse, status_code=201)
def create_bill_payment(
    bill_id: int,
    payment_data: BillPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Record a payment against a bill
    - Updates bill paid_amount and status
    - Creates journal entry for payment
    """
    # Verify bill_id matches
    if payment_data.bill_id != bill_id:
        raise HTTPException(status_code=400, detail="Bill ID mismatch")

    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    if bill.status not in [BillStatus.APPROVED, BillStatus.PARTIALLY_PAID]:
        raise HTTPException(
            status_code=400,
            detail=f"Bill must be APPROVED or PARTIALLY_PAID to record payments (current: {bill.status})"
        )

    # Validate payment amount doesn't exceed balance
    balance_due = bill.total_amount - bill.paid_amount
    if payment_data.amount > balance_due:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount ({payment_data.amount}) exceeds balance due ({balance_due})"
        )

    # Validate bank account exists
    bank_account = db.query(Account).filter(Account.id == payment_data.bank_account_id).first()
    if not bank_account:
        raise HTTPException(status_code=404, detail=f"Bank account {payment_data.bank_account_id} not found")

    # Validate fiscal period is open for the payment date
    validate_fiscal_period(db, payment_data.payment_date, "record payment")

    # Create payment record
    payment = BillPayment(
        bill_id=bill_id,
        payment_date=payment_data.payment_date,
        amount=payment_data.amount,
        payment_method=payment_data.payment_method,
        reference_number=payment_data.reference_number,
        bank_account_id=payment_data.bank_account_id,
        notes=payment_data.notes,
        created_by=current_user.id,
    )

    db.add(payment)

    # Update bill paid_amount and status
    bill.paid_amount += payment_data.amount
    new_balance = bill.total_amount - bill.paid_amount

    if abs(new_balance) < Decimal('0.01'):  # Fully paid (accounting for rounding)
        bill.status = BillStatus.PAID
        bill.paid_amount = bill.total_amount  # Ensure exact match
    else:
        bill.status = BillStatus.PARTIALLY_PAID

    # Create journal entry for the payment
    # DR: Accounts Payable (reduce liability)
    # CR: Bank/Cash account (reduce asset)
    try:
        journal_entry = create_payment_journal_entry(payment, bill, db)
        db.commit()
        db.refresh(payment)

        # Add note about JE creation to payment
        if payment.notes:
            payment.notes += f"\nJournal Entry Created: {journal_entry.entry_number}"
        else:
            payment.notes = f"Journal Entry Created: {journal_entry.entry_number}"

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating journal entry: {str(e)}")

    return payment


@router.get("/{bill_id}/payments", response_model=List[BillPaymentResponse])
def list_bill_payments(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all payments for a specific bill"""
    # Verify bill exists
    bill = db.query(VendorBill).filter(VendorBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found")

    payments = db.query(BillPayment).options(
        joinedload(BillPayment.bank_account),
        joinedload(BillPayment.creator)
    ).filter(
        BillPayment.bill_id == bill_id
    ).order_by(BillPayment.payment_date.desc()).all()

    return payments


@router.post("/from-hub")
def receive_vendor_bill_from_hub(
    bill_data: dict,
    db: Session = Depends(get_db)
):
    """
    Receive and create a vendor bill from the Integration Hub

    Expected payload:
    {
        "vendor_name": "Gold Coast Linen Service",
        "bill_number": "1103/1009",
        "bill_date": "2025-11-03",
        "due_date": "2025-11-18",
        "total_amount": 111.74,
        "tax_amount": 0.00,
        "hub_invoice_id": 10,
        "location_id": 2,  # Hub location ID
        "location_name": "SW Grill",
        "lines": [
            {
                "account_id": 123,  # Accounting database ID
                "amount": 111.74,
                "description": "Linen Service"
            }
        ]
    }
    """
    try:
        # Look up location by name or create mapping
        area = None
        if bill_data.get("location_name"):
            area = db.query(Area).filter(
                Area.name.ilike(f"%{bill_data['location_name']}%")
            ).first()

        # Resolve vendor name using VendorService (handles aliases)
        vendor_service = VendorService(db)
        vendor, was_created, was_alias = vendor_service.get_or_create_vendor(
            vendor_name=bill_data["vendor_name"],
            create_if_not_found=True,
            default_payment_terms="Net 30"
        )

        # Use canonical vendor name if resolved via alias
        canonical_vendor_name = vendor.vendor_name if vendor else bill_data["vendor_name"]

        # Create vendor bill
        bill_date = datetime.strptime(bill_data["bill_date"], "%Y-%m-%d").date()
        # Default due date to vendor's payment terms, or 30 days if not set
        if bill_data.get("due_date"):
            due_date = datetime.strptime(bill_data["due_date"], "%Y-%m-%d").date()
        else:
            from datetime import timedelta
            # Use vendor payment terms if available
            payment_days = 30
            if vendor and vendor.payment_terms:
                # Parse "Net X" to get days
                terms = vendor.payment_terms.lower()
                if "net" in terms:
                    try:
                        payment_days = int(''.join(filter(str.isdigit, terms)))
                    except ValueError:
                        payment_days = 30
                elif "due on receipt" in terms:
                    payment_days = 0
            due_date = bill_date + timedelta(days=payment_days)

        bill = VendorBill(
            vendor_name=canonical_vendor_name,  # Use canonical name
            vendor_id=vendor.id if vendor else None,
            bill_number=bill_data["bill_number"],
            bill_date=bill_date,
            due_date=due_date,
            subtotal=Decimal(str(bill_data["total_amount"])) - Decimal(str(bill_data.get("tax_amount", 0))),
            tax_amount=Decimal(str(bill_data.get("tax_amount", 0))),
            total_amount=Decimal(str(bill_data["total_amount"])),
            area_id=area.id if area else None,
            reference_number=f"HUB-{bill_data.get('hub_invoice_id')}",
            description=f"From Integration Hub - Invoice #{bill_data['bill_number']}",
            status=BillStatus.APPROVED,  # Auto-approve bills from Hub
            created_by=1,  # System user (Integration Hub)
            approved_by=None,  # No manual approval - auto-approved by system
            approved_date=None  # No manual approval date
        )

        db.add(bill)
        db.flush()  # Get bill ID

        # Create line items
        for idx, line_data in enumerate(bill_data["lines"], start=1):
            line = VendorBillLine(
                bill_id=bill.id,
                account_id=line_data["account_id"],
                area_id=area.id if area else None,
                description=line_data.get("description"),
                amount=Decimal(str(line_data["amount"])),
                is_taxable=False,
                tax_amount=Decimal('0.00'),
                line_number=idx
            )
            db.add(line)

        db.flush()

        # Create journal entry (Dr. Expense, Cr. AP)
        je = create_bill_journal_entry(bill, db)

        # Link bill to journal entry
        bill.journal_entry_id = je.id

        db.commit()
        db.refresh(bill)

        return {
            "success": True,
            "bill_id": bill.id,
            "journal_entry_id": je.id,
            "journal_entry_number": je.entry_number,
            "message": f"Vendor bill {bill.bill_number} created successfully"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating vendor bill: {str(e)}"
        )
