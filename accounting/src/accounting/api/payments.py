"""
Payment API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from accounting.db.database import get_db
from accounting.models.payment import Payment, CheckBatch, ACHBatch, PaymentStatus
from accounting.schemas.payment import (
    PaymentCreate, PaymentResponse, PaymentUpdate,
    BatchPaymentRequest, BatchPaymentResponse,
    CheckBatchResponse, CheckPrintRequest, CheckPrintResponse,
    ACHBatchResponse, ACHFileGenerateRequest, ACHFileGenerateResponse,
    PaymentVoidRequest, PaymentHistoryFilter, PaymentSummary
)
from accounting.services.payment_service import PaymentService

router = APIRouter()


# ============================================================================
# Payment CRUD
# ============================================================================

@router.post("/", response_model=PaymentResponse)
def create_payment(
    payment: PaymentCreate,
    db: Session = Depends(get_db)
):
    """Create a new payment"""
    # TODO: Get user_id from session
    user_id = 1

    service = PaymentService(db)
    result = service.create_payment(payment, user_id)
    return result


@router.get("/", response_model=List[PaymentResponse])
def list_payments(
    vendor_id: Optional[int] = None,
    area_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List payments with filters"""
    query = db.query(Payment)

    if vendor_id:
        query = query.filter(Payment.vendor_id == vendor_id)
    if area_id:
        query = query.filter(Payment.area_id == area_id)
    if status:
        query = query.filter(Payment.status == status)
    if start_date:
        query = query.filter(Payment.payment_date >= start_date)
    if end_date:
        query = query.filter(Payment.payment_date <= end_date)

    payments = query.order_by(Payment.payment_date.desc()).offset(skip).limit(limit).all()
    return payments


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    """Get payment by ID"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.put("/{payment_id}", response_model=PaymentResponse)
def update_payment(
    payment_id: int,
    payment_update: PaymentUpdate,
    db: Session = Depends(get_db)
):
    """Update payment"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    for field, value in payment_update.dict(exclude_unset=True).items():
        setattr(payment, field, value)

    db.commit()
    db.refresh(payment)
    return payment


@router.post("/{payment_id}/void", response_model=PaymentResponse)
def void_payment(
    payment_id: int,
    void_request: PaymentVoidRequest,
    db: Session = Depends(get_db)
):
    """Void a payment"""
    user_id = 1  # TODO: Get from session

    service = PaymentService(db)
    payment = service.void_payment(payment_id, void_request.void_reason, user_id)
    return payment


# ============================================================================
# Batch Payments
# ============================================================================

@router.post("/batch", response_model=BatchPaymentResponse)
def create_batch_payment(
    batch_request: BatchPaymentRequest,
    db: Session = Depends(get_db)
):
    """Create batch payment for multiple bills"""
    user_id = 1  # TODO: Get from session

    service = PaymentService(db)
    result = service.create_batch_payment(batch_request, user_id)

    return BatchPaymentResponse(
        batch_id=result['batch_id'],
        batch_number=f"BATCH-{result['batch_id']}",
        payment_count=result['payment_count'],
        total_amount=result['total_amount'],
        payment_ids=result['payment_ids']
    )


# ============================================================================
# Check Printing
# ============================================================================

@router.get("/check-batches/", response_model=List[CheckBatchResponse])
def list_check_batches(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List check batches"""
    query = db.query(CheckBatch)

    if status:
        query = query.filter(CheckBatch.status == status)

    batches = query.order_by(CheckBatch.batch_date.desc()).offset(skip).limit(limit).all()
    return batches


@router.get("/check-batches/{batch_id}", response_model=CheckBatchResponse)
def get_check_batch(batch_id: int, db: Session = Depends(get_db)):
    """Get check batch by ID"""
    batch = db.query(CheckBatch).filter(CheckBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Check batch not found")
    return batch


@router.post("/check-batches/{batch_id}/print")
def print_checks(
    batch_id: int,
    db: Session = Depends(get_db)
):
    """Generate and return PDF for check batch"""
    user_id = 1  # TODO: Get from session

    service = PaymentService(db)

    try:
        pdf_path = service.print_checks(batch_id, user_id)
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"checks_{batch_id}.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check-batches/{batch_id}/preview")
def preview_checks(batch_id: int, db: Session = Depends(get_db)):
    """Get check data for preview"""
    batch = db.query(CheckBatch).filter(CheckBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Check batch not found")

    payments = db.query(Payment).filter(
        Payment.check_batch_id == batch_id
    ).order_by(Payment.check_number).all()

    checks = []
    for payment in payments:
        checks.append({
            'check_number': payment.check_number,
            'payment_date': payment.payment_date,
            'payee_name': payment.vendor.name if payment.vendor else '',
            'amount': float(payment.net_amount),
            'memo': payment.memo
        })

    return {
        'batch_id': batch.id,
        'batch_number': batch.batch_number,
        'check_count': len(checks),
        'total_amount': float(batch.total_amount),
        'checks': checks
    }


# ============================================================================
# ACH Processing
# ============================================================================

@router.get("/ach-batches/", response_model=List[ACHBatchResponse])
def list_ach_batches(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List ACH batches"""
    query = db.query(ACHBatch)

    if status:
        query = query.filter(ACHBatch.status == status)

    batches = query.order_by(ACHBatch.batch_date.desc()).offset(skip).limit(limit).all()
    return batches


@router.post("/ach-batches/{batch_id}/generate")
def generate_ach_file(
    batch_id: int,
    db: Session = Depends(get_db)
):
    """Generate NACHA ACH file for batch"""
    user_id = 1  # TODO: Get from session

    service = PaymentService(db)

    try:
        ach_path = service.generate_ach_file(batch_id, user_id)
        return FileResponse(
            ach_path,
            media_type="text/plain",
            filename=f"ach_{batch_id}.txt"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Payment Reports
# ============================================================================

@router.get("/reports/history")
def payment_history_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    vendor_id: Optional[int] = None,
    area_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get payment history report"""
    query = db.query(Payment)

    if start_date:
        query = query.filter(Payment.payment_date >= start_date)
    if end_date:
        query = query.filter(Payment.payment_date <= end_date)
    if vendor_id:
        query = query.filter(Payment.vendor_id == vendor_id)
    if area_id:
        query = query.filter(Payment.area_id == area_id)

    payments = query.order_by(Payment.payment_date.desc()).all()

    return {
        'payments': [
            {
                'payment_number': p.payment_number,
                'payment_date': p.payment_date,
                'vendor_name': p.vendor.name if p.vendor else '',
                'amount': float(p.net_amount),
                'payment_method': p.payment_method,
                'status': p.status,
                'check_number': p.check_number
            }
            for p in payments
        ],
        'total_amount': sum(p.net_amount for p in payments),
        'payment_count': len(payments)
    }


@router.get("/reports/outstanding-checks")
def outstanding_checks_report(db: Session = Depends(get_db)):
    """Get outstanding checks report"""
    payments = db.query(Payment).filter(
        Payment.payment_method == 'CHECK',
        Payment.status.in_(['PRINTED', 'PENDING']),
        Payment.cleared_date.is_(None)
    ).order_by(Payment.check_number).all()

    checks = []
    for payment in payments:
        days_outstanding = (date.today() - payment.payment_date).days
        checks.append({
            'check_number': payment.check_number,
            'payment_date': payment.payment_date,
            'vendor_name': payment.vendor.name if payment.vendor else '',
            'amount': float(payment.net_amount),
            'days_outstanding': days_outstanding,
            'status': payment.status
        })

    return {
        'checks': checks,
        'total_amount': sum(c['amount'] for c in checks),
        'check_count': len(checks)
    }
