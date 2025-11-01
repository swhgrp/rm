"""
Customer management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.customer import Customer
from accounting.models.customer_invoice import CustomerInvoice, InvoiceStatus
from accounting.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from accounting.api.auth import require_auth

router = APIRouter(prefix="/api/customers", tags=["customers"])


# Credit Status Schema
class CustomerCreditStatus(BaseModel):
    customer_id: int
    customer_name: str
    credit_limit: Optional[Decimal]
    outstanding_balance: Decimal
    available_credit: Optional[Decimal]
    credit_utilization_percent: Optional[float]
    is_over_limit: bool
    warning_threshold_reached: bool  # True if >= 90% of limit

    class Config:
        from_attributes = True


@router.get("/", response_model=List[CustomerResponse])
def list_customers(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    search: Optional[str] = Query(None, description="Search by customer name or code"),
    customer_type: Optional[str] = Query(None, description="Filter by customer type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all customers - available to all authenticated users"""
    query = db.query(Customer)

    if not include_inactive:
        query = query.filter(Customer.is_active == True)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Customer.customer_name.ilike(search_pattern)) |
            (Customer.customer_code.ilike(search_pattern))
        )

    if customer_type:
        query = query.filter(Customer.customer_type == customer_type)

    customers = query.order_by(Customer.customer_name).offset(skip).limit(limit).all()
    return customers


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific customer by ID"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    return customer


@router.post("/", response_model=CustomerResponse)
def create_customer(
    customer_data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new customer"""
    # Check if customer name already exists
    existing_name = db.query(Customer).filter(Customer.customer_name == customer_data.customer_name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer name already exists"
        )

    # Check if customer code already exists (if provided)
    if customer_data.customer_code:
        existing_code = db.query(Customer).filter(Customer.customer_code == customer_data.customer_code).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer code already exists"
            )

    # Create new customer
    new_customer = Customer(
        customer_name=customer_data.customer_name,
        customer_code=customer_data.customer_code,
        customer_type=customer_data.customer_type,
        contact_name=customer_data.contact_name,
        email=customer_data.email,
        phone=customer_data.phone,
        mobile=customer_data.mobile,
        fax=customer_data.fax,
        website=customer_data.website,
        address_line1=customer_data.address_line1,
        address_line2=customer_data.address_line2,
        city=customer_data.city,
        state=customer_data.state,
        zip_code=customer_data.zip_code,
        country=customer_data.country,
        billing_email=customer_data.billing_email,
        billing_contact=customer_data.billing_contact,
        tax_exempt=customer_data.tax_exempt,
        tax_exempt_id=customer_data.tax_exempt_id,
        tax_rate=customer_data.tax_rate,
        payment_terms=customer_data.payment_terms,
        credit_limit=customer_data.credit_limit,
        discount_percentage=customer_data.discount_percentage,
        notes=customer_data.notes
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return new_customer


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # Update fields if provided
    if customer_data.customer_name is not None:
        existing_name = db.query(Customer).filter(
            Customer.customer_name == customer_data.customer_name,
            Customer.id != customer_id
        ).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer name already exists"
            )
        customer.customer_name = customer_data.customer_name

    if customer_data.customer_code is not None:
        existing_code = db.query(Customer).filter(
            Customer.customer_code == customer_data.customer_code,
            Customer.id != customer_id
        ).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer code already exists"
            )
        customer.customer_code = customer_data.customer_code

    # Update all other fields
    if customer_data.customer_type is not None:
        customer.customer_type = customer_data.customer_type
    if customer_data.contact_name is not None:
        customer.contact_name = customer_data.contact_name
    if customer_data.email is not None:
        customer.email = customer_data.email
    if customer_data.phone is not None:
        customer.phone = customer_data.phone
    if customer_data.mobile is not None:
        customer.mobile = customer_data.mobile
    if customer_data.fax is not None:
        customer.fax = customer_data.fax
    if customer_data.website is not None:
        customer.website = customer_data.website
    if customer_data.address_line1 is not None:
        customer.address_line1 = customer_data.address_line1
    if customer_data.address_line2 is not None:
        customer.address_line2 = customer_data.address_line2
    if customer_data.city is not None:
        customer.city = customer_data.city
    if customer_data.state is not None:
        customer.state = customer_data.state
    if customer_data.zip_code is not None:
        customer.zip_code = customer_data.zip_code
    if customer_data.country is not None:
        customer.country = customer_data.country
    if customer_data.billing_email is not None:
        customer.billing_email = customer_data.billing_email
    if customer_data.billing_contact is not None:
        customer.billing_contact = customer_data.billing_contact
    if customer_data.tax_exempt is not None:
        customer.tax_exempt = customer_data.tax_exempt
    if customer_data.tax_exempt_id is not None:
        customer.tax_exempt_id = customer_data.tax_exempt_id
    if customer_data.tax_rate is not None:
        customer.tax_rate = customer_data.tax_rate
    if customer_data.payment_terms is not None:
        customer.payment_terms = customer_data.payment_terms
    if customer_data.credit_limit is not None:
        customer.credit_limit = customer_data.credit_limit
    if customer_data.discount_percentage is not None:
        customer.discount_percentage = customer_data.discount_percentage
    if customer_data.notes is not None:
        customer.notes = customer_data.notes
    if customer_data.is_active is not None:
        customer.is_active = customer_data.is_active

    db.commit()
    db.refresh(customer)

    return customer


@router.get("/{customer_id}/credit-status", response_model=CustomerCreditStatus)
def get_customer_credit_status(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Get customer's credit status including outstanding balance and available credit

    Returns credit limit, current outstanding balance, available credit,
    and warnings about credit utilization.
    """
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # Calculate current outstanding balance (unpaid invoices)
    outstanding_balance = db.query(
        func.sum(CustomerInvoice.total_amount - CustomerInvoice.deposit_amount - CustomerInvoice.paid_amount)
    ).filter(
        CustomerInvoice.customer_id == customer_id,
        CustomerInvoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE])
    ).scalar() or Decimal("0")

    # Calculate available credit and utilization
    available_credit = None
    credit_utilization = None
    is_over_limit = False
    warning_threshold = False

    if customer.credit_limit and customer.credit_limit > 0:
        available_credit = customer.credit_limit - outstanding_balance
        credit_utilization = float((outstanding_balance / customer.credit_limit) * 100)
        is_over_limit = outstanding_balance > customer.credit_limit
        warning_threshold = credit_utilization >= 90.0

    return CustomerCreditStatus(
        customer_id=customer.id,
        customer_name=customer.customer_name,
        credit_limit=customer.credit_limit,
        outstanding_balance=outstanding_balance,
        available_credit=available_credit,
        credit_utilization_percent=credit_utilization,
        is_over_limit=is_over_limit,
        warning_threshold_reached=warning_threshold
    )


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a customer"""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # TODO: Check if customer has any invoices before deleting

    db.delete(customer)
    db.commit()

    return {"message": "Customer deleted successfully"}
