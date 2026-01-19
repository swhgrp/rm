"""
Recurring Invoice API Endpoints

CRUD operations for managing recurring invoice templates
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.api.auth import require_auth
from accounting.models.recurring_invoice import (
    RecurringInvoice,
    RecurringInvoiceLineItem,
    RecurringFrequency,
    RecurringInvoiceStatus
)
from accounting.models.customer import Customer
from accounting.services.recurring_invoice_service import RecurringInvoiceService

router = APIRouter()


# Pydantic Schemas
class RecurringInvoiceLineItemCreate(BaseModel):
    line_number: int = 1
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")
    account_id: Optional[int] = None


class RecurringInvoiceLineItemResponse(BaseModel):
    id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    account_id: Optional[int]

    class Config:
        from_attributes = True


class RecurringInvoiceCreate(BaseModel):
    customer_id: int
    template_name: str
    description: Optional[str] = None
    frequency: RecurringFrequency
    start_date: date
    end_date: Optional[date] = None
    next_invoice_date: date
    terms_days: int = 30
    invoice_description: Optional[str] = None
    notes: Optional[str] = None
    discount_percent: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal("0.00")
    auto_send_email: bool = True
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    line_items: List[RecurringInvoiceLineItemCreate]


class RecurringInvoiceUpdate(BaseModel):
    template_name: Optional[str] = None
    description: Optional[str] = None
    frequency: Optional[RecurringFrequency] = None
    end_date: Optional[date] = None
    next_invoice_date: Optional[date] = None
    terms_days: Optional[int] = None
    invoice_description: Optional[str] = None
    notes: Optional[str] = None
    discount_percent: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    auto_send_email: Optional[bool] = None
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    status: Optional[RecurringInvoiceStatus] = None
    line_items: Optional[List[RecurringInvoiceLineItemCreate]] = None


class RecurringInvoiceResponse(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    template_name: str
    description: Optional[str]
    frequency: RecurringFrequency
    start_date: date
    end_date: Optional[date]
    next_invoice_date: date
    terms_days: int
    invoice_description: Optional[str]
    notes: Optional[str]
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    auto_send_email: bool
    email_to: Optional[str]
    email_cc: Optional[str]
    status: RecurringInvoiceStatus
    invoices_generated: int
    last_generated_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    line_items: List[RecurringInvoiceLineItemResponse]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[RecurringInvoiceResponse])
def list_recurring_invoices(
    status: Optional[RecurringInvoiceStatus] = None,
    customer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all recurring invoice templates"""
    query = db.query(RecurringInvoice)

    if status:
        query = query.filter(RecurringInvoice.status == status)

    if customer_id:
        query = query.filter(RecurringInvoice.customer_id == customer_id)

    templates = query.order_by(RecurringInvoice.next_invoice_date).all()

    # Convert to response format
    result = []
    for template in templates:
        result.append({
            **template.__dict__,
            'customer_name': template.customer.customer_name
        })

    return result


@router.get("/{template_id}", response_model=RecurringInvoiceResponse)
def get_recurring_invoice(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific recurring invoice template"""
    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    return {
        **template.__dict__,
        'customer_name': template.customer.customer_name
    }


@router.post("/", response_model=RecurringInvoiceResponse)
def create_recurring_invoice(
    data: RecurringInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new recurring invoice template"""

    # Verify customer exists
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Create recurring invoice
    template = RecurringInvoice(
        customer_id=data.customer_id,
        template_name=data.template_name,
        description=data.description,
        frequency=data.frequency,
        start_date=datetime.combine(data.start_date, datetime.min.time()),
        end_date=datetime.combine(data.end_date, datetime.min.time()) if data.end_date else None,
        next_invoice_date=datetime.combine(data.next_invoice_date, datetime.min.time()),
        terms_days=data.terms_days,
        invoice_description=data.invoice_description,
        notes=data.notes,
        discount_percent=data.discount_percent,
        tax_rate=data.tax_rate,
        auto_send_email=data.auto_send_email,
        email_to=data.email_to,
        email_cc=data.email_cc,
        status=RecurringInvoiceStatus.ACTIVE,
        created_by=current_user.id,
        updated_by=current_user.id
    )

    db.add(template)
    db.flush()

    # Add line items
    for item_data in data.line_items:
        line_item = RecurringInvoiceLineItem(
            recurring_invoice_id=template.id,
            line_number=item_data.line_number,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            amount=item_data.quantity * item_data.unit_price,
            account_id=item_data.account_id
        )
        db.add(line_item)

    db.flush()

    # Calculate totals
    service = RecurringInvoiceService(db)
    template = service.calculate_totals(template)

    db.commit()
    db.refresh(template)

    return {
        **template.__dict__,
        'customer_name': customer.customer_name
    }


@router.put("/{template_id}", response_model=RecurringInvoiceResponse)
def update_recurring_invoice(
    template_id: int,
    data: RecurringInvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a recurring invoice template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    # Update fields
    if data.template_name is not None:
        template.template_name = data.template_name
    if data.description is not None:
        template.description = data.description
    if data.frequency is not None:
        template.frequency = data.frequency
    if data.end_date is not None:
        template.end_date = datetime.combine(data.end_date, datetime.min.time())
    if data.next_invoice_date is not None:
        template.next_invoice_date = datetime.combine(data.next_invoice_date, datetime.min.time())
    if data.terms_days is not None:
        template.terms_days = data.terms_days
    if data.invoice_description is not None:
        template.invoice_description = data.invoice_description
    if data.notes is not None:
        template.notes = data.notes
    if data.discount_percent is not None:
        template.discount_percent = data.discount_percent
    if data.tax_rate is not None:
        template.tax_rate = data.tax_rate
    if data.auto_send_email is not None:
        template.auto_send_email = data.auto_send_email
    if data.email_to is not None:
        template.email_to = data.email_to
    if data.email_cc is not None:
        template.email_cc = data.email_cc
    if data.status is not None:
        template.status = data.status

    # Update line items if provided
    if data.line_items is not None:
        # Delete existing line items
        db.query(RecurringInvoiceLineItem).filter(
            RecurringInvoiceLineItem.recurring_invoice_id == template_id
        ).delete()

        # Add new line items
        for item_data in data.line_items:
            line_item = RecurringInvoiceLineItem(
                recurring_invoice_id=template.id,
                line_number=item_data.line_number,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                amount=item_data.quantity * item_data.unit_price,
                account_id=item_data.account_id
            )
            db.add(line_item)

        db.flush()

        # Recalculate totals
        service = RecurringInvoiceService(db)
        template = service.calculate_totals(template)

    template.updated_by = current_user.id
    template.updated_at = get_now()

    db.commit()
    db.refresh(template)

    return {
        **template.__dict__,
        'customer_name': template.customer.customer_name
    }


@router.delete("/{template_id}")
def delete_recurring_invoice(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a recurring invoice template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    db.delete(template)
    db.commit()

    return {"message": "Recurring invoice template deleted successfully"}


@router.post("/{template_id}/generate")
def generate_invoice_now(
    template_id: int,
    override_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Manually generate an invoice from template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    service = RecurringInvoiceService(db)
    invoice = service.generate_invoice_from_template(template, override_date)

    return {
        "message": "Invoice generated successfully",
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number
    }


@router.post("/{template_id}/pause")
def pause_recurring_invoice(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Pause a recurring invoice template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    template.status = RecurringInvoiceStatus.PAUSED
    template.updated_by = current_user.id
    template.updated_at = get_now()

    db.commit()

    return {"message": "Recurring invoice paused successfully"}


@router.post("/{template_id}/resume")
def resume_recurring_invoice(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Resume a paused recurring invoice template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    if template.status != RecurringInvoiceStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Only paused templates can be resumed")

    template.status = RecurringInvoiceStatus.ACTIVE
    template.updated_by = current_user.id
    template.updated_at = get_now()

    db.commit()

    return {"message": "Recurring invoice resumed successfully"}


@router.post("/{template_id}/cancel")
def cancel_recurring_invoice(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Cancel a recurring invoice template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    template.status = RecurringInvoiceStatus.CANCELLED
    template.updated_by = current_user.id
    template.updated_at = get_now()

    db.commit()

    return {"message": "Recurring invoice cancelled successfully"}


@router.get("/{template_id}/history")
def get_recurring_invoice_history(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get invoices generated from this template"""

    template = db.query(RecurringInvoice).filter(RecurringInvoice.id == template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Recurring invoice template not found")

    from accounting.models.customer_invoice import CustomerInvoice

    invoices = db.query(CustomerInvoice).filter(
        CustomerInvoice.recurring_invoice_id == template_id
    ).order_by(CustomerInvoice.invoice_date.desc()).all()

    return {
        "template_id": template_id,
        "template_name": template.template_name,
        "invoices_generated": len(invoices),
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat(),
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "total_amount": float(inv.total_amount),
                "status": inv.status.value,
                "paid_amount": float(inv.paid_amount)
            }
            for inv in invoices
        ]
    }
