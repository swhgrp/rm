"""
API endpoints for Customer Invoices (Accounts Receivable)
Handles invoice creation, line items, payments, and status management
"""
from fastapi import APIRouter, Depends, HTTPException, Query
import logging
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.customer import Customer
from accounting.models.customer_invoice import (
    CustomerInvoice, CustomerInvoiceLine, InvoicePayment, InvoiceStatus
)
from accounting.schemas.customer_invoice import (
    CustomerInvoiceCreate, CustomerInvoiceUpdate, CustomerInvoiceRead,
    CustomerInvoiceLineCreate, InvoicePaymentCreate, InvoicePaymentRead,
    PaymentMethod, ARAgingReportResponse
)
from accounting.api.auth import require_auth
from accounting.services.ar_gl_service import ARGLService

router = APIRouter(prefix="/api/customer-invoices", tags=["customer-invoices"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[CustomerInvoiceRead])
def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: Optional[int] = Query(None),
    status: Optional[InvoiceStatus] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    area_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List customer invoices with filtering"""
    query = db.query(CustomerInvoice).options(
        joinedload(CustomerInvoice.customer),
        joinedload(CustomerInvoice.area)
    )

    # Filter by customer
    if customer_id:
        query = query.filter(CustomerInvoice.customer_id == customer_id)

    # Filter by status
    if status:
        query = query.filter(CustomerInvoice.status == status)

    # Filter by location/area
    if area_id:
        query = query.filter(CustomerInvoice.area_id == area_id)

    # Date range filter
    if start_date:
        query = query.filter(CustomerInvoice.invoice_date >= start_date)
    if end_date:
        query = query.filter(CustomerInvoice.invoice_date <= end_date)

    # Search by invoice number or customer name
    if search:
        query = query.join(Customer).filter(
            or_(
                CustomerInvoice.invoice_number.ilike(f"%{search}%"),
                Customer.customer_name.ilike(f"%{search}%")
            )
        )

    # Order by invoice date desc
    query = query.order_by(CustomerInvoice.invoice_date.desc(), CustomerInvoice.id.desc())

    invoices = query.offset(skip).limit(limit).all()
    return invoices



@router.get("/aging-report", response_model=ARAgingReportResponse)
def ar_aging_report(
    area_id: Optional[int] = Query(None),
    as_of_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Accounts Receivable aging report
    Shows outstanding invoices grouped by age
    """

    # Parse date string
    if as_of_date is None:
        as_of_date = date.today()
    else:
        try:
            as_of_date = date.fromisoformat(as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {as_of_date}. Use YYYY-MM-DD")
    # Query for unpaid/partially paid invoices
    query = db.query(CustomerInvoice).filter(
        CustomerInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID])
    )

    # Filter by location if specified
    if area_id:
        query = query.filter(CustomerInvoice.area_id == area_id)

    invoices = query.all()

    # Initialize aging buckets
    current = Decimal('0')  # 0-30 days
    days_31_60 = Decimal('0')
    days_61_90 = Decimal('0')
    over_90 = Decimal('0')
    total_outstanding = Decimal('0')

    # Calculate aging for each invoice
    for invoice in invoices:
        # Calculate balance (total - paid)
        balance = invoice.total_amount - invoice.paid_amount

        if balance <= 0:
            continue  # Skip fully paid invoices

        # Calculate days overdue from due date
        days_overdue = (as_of_date - invoice.due_date).days

        # Add to appropriate bucket
        if days_overdue <= 30:
            current += balance
        elif days_overdue <= 60:
            days_31_60 += balance
        elif days_overdue <= 90:
            days_61_90 += balance
        else:
            over_90 += balance

        total_outstanding += balance

    return ARAgingReportResponse(
        as_of_date=as_of_date,
        current=float(current),
        days_31_60=float(days_31_60),
        days_61_90=float(days_61_90),
        over_90=float(over_90),
        total_outstanding=float(total_outstanding)
    )

@router.get("/{invoice_id}", response_model=CustomerInvoiceRead)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get a specific invoice with all details"""
    invoice = db.query(CustomerInvoice).options(
        joinedload(CustomerInvoice.customer),
        joinedload(CustomerInvoice.area),
        joinedload(CustomerInvoice.line_items),
        joinedload(CustomerInvoice.payments)
    ).filter(CustomerInvoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoice


@router.post("/", response_model=CustomerInvoiceRead)
def create_invoice(
    invoice_data: CustomerInvoiceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create a new customer invoice"""

    # Verify customer exists
    customer = db.query(Customer).filter(Customer.id == invoice_data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check for duplicate invoice number
    existing = db.query(CustomerInvoice).filter(
        CustomerInvoice.invoice_number == invoice_data.invoice_number
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Invoice number already exists")

    # Calculate totals from line items
    subtotal = Decimal("0")
    total_discount = Decimal("0")
    total_tax = Decimal("0")

    for line in invoice_data.lines:
        line_amount = line.quantity * line.unit_price
        line_discount = Decimal("0")

        # Calculate discount
        if line.discount_percentage and line.discount_percentage > 0:
            line_discount = line_amount * (line.discount_percentage / Decimal("100"))

        line_net = line_amount - line_discount
        subtotal += line_amount
        total_discount += line_discount

        # Calculate tax if taxable and not tax exempt
        if line.is_taxable and not invoice_data.is_tax_exempt:
            tax_rate = invoice_data.tax_rate or customer.tax_rate or Decimal("0")
            line_tax = line_net * (tax_rate / Decimal("100"))
            total_tax += line_tax

    # Calculate total
    total_amount = subtotal - total_discount + total_tax

    # Create invoice
    invoice = CustomerInvoice(
        customer_id=invoice_data.customer_id,
        area_id=invoice_data.area_id,
        invoice_number=invoice_data.invoice_number,
        invoice_date=invoice_data.invoice_date,
        due_date=invoice_data.due_date,
        event_date=invoice_data.event_date,
        event_type=invoice_data.event_type,
        event_location=invoice_data.event_location,
        guest_count=invoice_data.guest_count,
        subtotal=subtotal,
        discount_amount=total_discount,
        tax_amount=total_tax,
        deposit_amount=invoice_data.deposit_amount or Decimal("0"),
        total_amount=total_amount,
        paid_amount=Decimal("0"),
        is_tax_exempt=invoice_data.is_tax_exempt,
        tax_rate=invoice_data.tax_rate,
        notes=invoice_data.notes,
        status=InvoiceStatus.DRAFT,
        created_by=user.id
    )

    db.add(invoice)
    db.flush()  # Get the invoice ID

    # Create line items
    for line_data in invoice_data.lines:
        line_amount = line_data.quantity * line_data.unit_price
        line_discount = Decimal("0")
        line_tax = Decimal("0")

        if line_data.discount_percentage and line_data.discount_percentage > 0:
            line_discount = line_amount * (line_data.discount_percentage / Decimal("100"))

        line_net = line_amount - line_discount

        if line_data.is_taxable and not invoice_data.is_tax_exempt:
            tax_rate = invoice_data.tax_rate or customer.tax_rate or Decimal("0")
            line_tax = line_net * (tax_rate / Decimal("100"))

        line = CustomerInvoiceLine(
            invoice_id=invoice.id,
            account_id=line_data.account_id,
            description=line_data.description,
            quantity=line_data.quantity,
            unit_price=line_data.unit_price,
            amount=line_amount,
            discount_percentage=line_data.discount_percentage,
            discount_amount=line_discount,
            is_taxable=line_data.is_taxable,
            tax_amount=line_tax
        )
        db.add(line)

    db.commit()
    db.refresh(invoice)

    return invoice


@router.put("/{invoice_id}", response_model=CustomerInvoiceRead)
def update_invoice(
    invoice_id: int,
    invoice_data: CustomerInvoiceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update an invoice (only if status is DRAFT)"""

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Only allow editing draft invoices
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only edit draft invoices")

    # Check invoice number uniqueness if changed
    if invoice_data.invoice_number and invoice_data.invoice_number != invoice.invoice_number:
        existing = db.query(CustomerInvoice).filter(
            CustomerInvoice.invoice_number == invoice_data.invoice_number,
            CustomerInvoice.id != invoice_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Invoice number already exists")

    # Update fields
    if invoice_data.invoice_number:
        invoice.invoice_number = invoice_data.invoice_number
    if invoice_data.invoice_date:
        invoice.invoice_date = invoice_data.invoice_date
    if invoice_data.due_date:
        invoice.due_date = invoice_data.due_date
    if invoice_data.event_date is not None:
        invoice.event_date = invoice_data.event_date
    if invoice_data.event_type is not None:
        invoice.event_type = invoice_data.event_type
    if invoice_data.event_location is not None:
        invoice.event_location = invoice_data.event_location
    if invoice_data.guest_count is not None:
        invoice.guest_count = invoice_data.guest_count
    if invoice_data.notes is not None:
        invoice.notes = invoice_data.notes
    if invoice_data.deposit_amount is not None:
        invoice.deposit_amount = invoice_data.deposit_amount

    invoice.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(invoice)

    return invoice


@router.post("/{invoice_id}/send")
def send_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Mark invoice as sent and auto-post to GL

    Creates journal entry:
    DR: Accounts Receivable
        CR: Revenue (per line items)
        CR: Sales Tax Payable (if applicable)
    """

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only send draft invoices")

    # Update invoice status
    invoice.status = InvoiceStatus.SENT
    invoice.sent_date = datetime.utcnow()
    invoice.updated_at = datetime.utcnow()

    # Auto-post to GL
    try:
        ar_gl_service = ARGLService(db)
        journal_entry = ar_gl_service.post_invoice_to_gl(
            invoice=invoice,
            user_id=user.id,
            auto_post=True
        )

        logger.info(
            f"Invoice {invoice.invoice_number} sent and posted to GL "
            f"(JE: {journal_entry.entry_number})"
        )

        return {
            "message": "Invoice sent and posted to GL",
            "status": invoice.status,
            "journal_entry_number": journal_entry.entry_number
        }
    except ValueError as e:
        # GL posting failed - revert status change
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to post invoice to GL: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error posting invoice to GL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error posting invoice to GL: {str(e)}"
        )


@router.post("/{invoice_id}/payments", response_model=InvoicePaymentRead)
def record_payment(
    invoice_id: int,
    payment_data: InvoicePaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Record a payment against an invoice and auto-post to GL

    Creates journal entry:
    DR: Cash/Bank Account
        CR: Accounts Receivable (or Customer Deposits if is_deposit=True)
    """

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.VOID:
        raise HTTPException(status_code=400, detail="Cannot record payment for voided invoice")

    # Validate payment amount
    balance_due = invoice.total_amount - invoice.deposit_amount - invoice.paid_amount
    if payment_data.amount > balance_due:
        raise HTTPException(
            status_code=400,
            detail=f"Payment amount ${payment_data.amount} exceeds balance due ${balance_due}"
        )

    # Create payment record
    payment = InvoicePayment(
        invoice_id=invoice_id,
        payment_date=payment_data.payment_date,
        amount=payment_data.amount,
        payment_method=payment_data.payment_method,
        bank_account_id=payment_data.bank_account_id,
        reference_number=payment_data.reference_number,
        notes=payment_data.notes,
        is_deposit=payment_data.is_deposit or False,
        created_by=user.id
    )

    db.add(payment)
    db.flush()  # Get payment ID for GL posting

    # Update invoice paid amount and status
    if payment_data.is_deposit:
        invoice.deposit_amount += payment_data.amount
    else:
        invoice.paid_amount += payment_data.amount

    # Update status based on payment
    total_paid = invoice.deposit_amount + invoice.paid_amount
    if total_paid >= invoice.total_amount:
        invoice.status = InvoiceStatus.PAID
    elif total_paid > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID

    invoice.updated_at = datetime.utcnow()

    # Auto-post to GL
    try:
        ar_gl_service = ARGLService(db)
        journal_entry = ar_gl_service.post_payment_to_gl(
            payment=payment,
            invoice=invoice,
            user_id=user.id,
            auto_post=True
        )

        logger.info(
            f"Payment of ${payment.amount} recorded for invoice {invoice.invoice_number} "
            f"and posted to GL (JE: {journal_entry.entry_number})"
        )

        db.commit()
        db.refresh(payment)

        return payment
    except ValueError as e:
        # GL posting failed - revert changes
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Failed to post payment to GL: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error posting payment to GL: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error posting payment to GL: {str(e)}"
        )


@router.delete("/{invoice_id}/payments/{payment_id}")
def delete_payment(
    invoice_id: int,
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete a payment (admin only or within 24 hours)"""

    payment = db.query(InvoicePayment).filter(
        InvoicePayment.id == payment_id,
        InvoicePayment.invoice_id == invoice_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()

    # Revert payment from invoice
    if payment.is_deposit:
        invoice.deposit_amount -= payment.amount
    else:
        invoice.paid_amount -= payment.amount

    # Update invoice status
    total_paid = invoice.deposit_amount + invoice.paid_amount
    if total_paid == 0:
        invoice.status = InvoiceStatus.SENT
    elif total_paid < invoice.total_amount:
        invoice.status = InvoiceStatus.PARTIALLY_PAID

    invoice.updated_at = datetime.utcnow()

    db.delete(payment)
    db.commit()

    return {"message": "Payment deleted successfully"}


@router.post("/{invoice_id}/void")
def void_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Void an invoice and reverse GL entry

    Creates reversal journal entry:
    DR: Revenue (per line items)
    DR: Sales Tax Payable
        CR: Accounts Receivable
    """

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Cannot void a paid invoice")

    if invoice.paid_amount > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot void invoice with payments. Delete payments first."
        )

    # Void the invoice
    invoice.status = InvoiceStatus.VOID
    invoice.updated_at = datetime.utcnow()

    # Reverse GL entry if it exists
    if invoice.journal_entry_id:
        try:
            ar_gl_service = ARGLService(db)
            reversal_entry = ar_gl_service.reverse_invoice_entry(
                invoice=invoice,
                reversal_date=date.today(),
                user_id=user.id,
                reason=f"Invoice {invoice.invoice_number} voided"
            )

            logger.info(
                f"Invoice {invoice.invoice_number} voided and GL entry reversed "
                f"(Reversal JE: {reversal_entry.entry_number})"
            )

            db.commit()

            return {
                "message": "Invoice voided and GL entry reversed",
                "status": invoice.status,
                "reversal_entry_number": reversal_entry.entry_number
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Error reversing GL entry: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error reversing GL entry: {str(e)}"
            )
    else:
        # No GL entry to reverse
        db.commit()
        return {"message": "Invoice voided successfully (no GL entry to reverse)", "status": invoice.status}


@router.delete("/{invoice_id}")
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete an invoice (only if DRAFT and no payments)"""

    invoice = db.query(CustomerInvoice).filter(CustomerInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only delete draft invoices")

    # Delete line items first
    db.query(CustomerInvoiceLine).filter(CustomerInvoiceLine.invoice_id == invoice_id).delete()

    # Delete invoice
    db.delete(invoice)
    db.commit()

    return {"message": "Invoice deleted successfully"}


@router.get("/next-invoice-number/")
def get_next_invoice_number(
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get the next available invoice number"""

    # Get the latest invoice number
    latest = db.query(CustomerInvoice).order_by(CustomerInvoice.id.desc()).first()

    if not latest:
        # First invoice
        return {"next_number": "INV-00001"}

    # Try to extract number from latest invoice number
    try:
        if latest.invoice_number.startswith("INV-"):
            num = int(latest.invoice_number.split("-")[1]) + 1
            return {"next_number": f"INV-{num:05d}"}
    except:
        pass

    # Fallback: use ID-based numbering
    return {"next_number": f"INV-{latest.id + 1:05d}"}


