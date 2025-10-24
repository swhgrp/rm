"""
API endpoints for Daily Sales Summary (DSS)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.daily_sales_summary import DailySalesSummary, SalesLineItem, SalesPayment
from accounting.models.area import Area
from accounting.models.account import Account
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.schemas.daily_sales_summary import (
    DailySalesSummary as DSSSchema,
    DailySalesSummaryList,
    DailySalesSummaryCreate,
    DailySalesSummaryUpdate,
    DSSVerifyRequest,
    DSSPostRequest,
    DSSImportRequest,
    DSSImportResponse,
    SalesLineItemCreate,
    SalesPaymentCreate
)
from accounting.api.auth import require_auth
from accounting.core.permissions import require_permission

router = APIRouter(prefix="/api/daily-sales", tags=["daily_sales"])


# ============================================================================
# Helper Functions
# ============================================================================

def create_sales_journal_entry(dss: DailySalesSummary, db: Session, post_request: DSSPostRequest) -> JournalEntry:
    """
    Create journal entry for daily sales summary

    Typical entry structure:
    DR: Cash/Credit Card (Asset accounts) - by payment method
    DR: AR - Tips (if tips on credit cards)
    CR: Sales Revenue (by category)
    CR: Sales Tax Payable
    CR: Tips Payable (if cash tips)
    """
    from decimal import Decimal

    # Generate entry number
    today = date.today()
    prefix = f"DSS-{today.strftime('%Y%m%d')}-"
    max_entry = db.query(JournalEntry.entry_number).filter(
        JournalEntry.entry_number.like(f"{prefix}%")
    ).order_by(JournalEntry.entry_number.desc()).first()

    if max_entry and max_entry[0]:
        last_seq = int(max_entry[0].split('-')[-1])
        entry_number = f"{prefix}{last_seq + 1:04d}"
    else:
        entry_number = f"{prefix}0001"

    # Create journal entry
    je = JournalEntry(
        entry_number=entry_number,
        entry_date=dss.business_date,
        description=f"Daily Sales Summary - {dss.business_date} - {dss.area.name}",
        reference_type="SALE",
        reference_id=dss.id,
        created_by=dss.posted_by,
        status=JournalEntryStatus.POSTED
    )
    db.add(je)
    db.flush()

    lines = []
    line_number = 1

    # DEBIT: Payment methods (Cash, Credit Card, etc.) - Asset accounts
    if dss.payments:
        for payment in dss.payments:
            if payment.amount > 0:
                # Get deposit account from mapping or payment record
                account_id = payment.deposit_account_id
                if not account_id and post_request.payment_account_mapping:
                    account_id = post_request.payment_account_mapping.get(payment.payment_type.upper())

                if not account_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No deposit account specified for payment type: {payment.payment_type}"
                    )

                # Tips are excluded from journal entry because they are paid out daily
                # Only the payment amount (not tips) goes to the deposit account
                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=account_id,
                    area_id=dss.area_id,
                    description=f"{payment.payment_type} deposits",
                    debit_amount=payment.amount,  # Exclude tips - they're paid out daily
                    credit_amount=Decimal("0.00")
                ))
                line_number += 1
    elif dss.payment_breakdown:
        # Use JSONB breakdown if no detailed payment records
        for payment_type, amount in dss.payment_breakdown.items():
            if amount > 0:
                account_id = None
                if post_request.payment_account_mapping:
                    account_id = post_request.payment_account_mapping.get(payment_type.upper())

                if not account_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No deposit account specified for payment type: {payment_type}"
                    )

                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=account_id,
                    area_id=dss.area_id,
                    description=f"{payment_type} deposits",
                    debit_amount=Decimal(str(amount)),
                    credit_amount=Decimal("0.00")
                ))
                line_number += 1

    # CREDIT: Revenue by category
    if dss.line_items:
        # Group by category and revenue account
        category_totals = {}
        category_tax_total = Decimal("0.00")

        for item in dss.line_items:
            key = (item.category or "Other", item.revenue_account_id)
            if key not in category_totals:
                category_totals[key] = Decimal("0.00")
            category_totals[key] += item.net_amount
            category_tax_total += (item.tax_amount or Decimal("0.00"))

        for (category, account_id), amount in category_totals.items():
            if amount != 0:  # Include both positive and negative amounts
                # Get account from mapping if not specified
                if not account_id and post_request.category_account_mapping:
                    account_id = post_request.category_account_mapping.get(category.upper())

                if not account_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No revenue account specified for category: {category}"
                    )

                # For negative amounts (like Employee Meals, Comps), debit the revenue account
                # For positive amounts, credit the revenue account
                if amount > 0:
                    debit_amt = Decimal("0.00")
                    credit_amt = amount
                else:
                    debit_amt = abs(amount)
                    credit_amt = Decimal("0.00")

                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=account_id,
                    area_id=dss.area_id,
                    description=f"{category}",
                    debit_amount=debit_amt,
                    credit_amount=credit_amt
                ))
                line_number += 1
    elif dss.category_breakdown:
        # Use JSONB breakdown if no detailed line items
        for category, amount in dss.category_breakdown.items():
            if amount > 0:
                account_id = None
                if post_request.category_account_mapping:
                    account_id = post_request.category_account_mapping.get(category.upper())

                if not account_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No revenue account specified for category: {category}"
                    )

                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=account_id,
                    area_id=dss.area_id,
                    description=f"{category} sales",
                    debit_amount=Decimal("0.00"),
                    credit_amount=Decimal(str(amount))
                ))
                line_number += 1
    else:
        # Fallback: Single revenue line for net sales
        # Need to get a default revenue account
        revenue_account = db.query(Account).filter(
            Account.account_type == "REVENUE",
            Account.is_active == True
        ).first()

        if not revenue_account:
            raise HTTPException(status_code=400, detail="No revenue account found")

        lines.append(JournalEntryLine(
            journal_entry_id=je.id,
            line_number=line_number,
            account_id=revenue_account.id,
            area_id=dss.area_id,
            description="Total sales",
            debit_amount=Decimal("0.00"),
            credit_amount=dss.net_sales
        ))
        line_number += 1

    # CREDIT: Sales Tax Payable
    if dss.tax_collected > 0:
        tax_account = db.query(Account).filter(
            Account.account_type == "LIABILITY",
            Account.account_name.ilike("%tax%payable%")
        ).first()

        if not tax_account:
            raise HTTPException(status_code=400, detail="No sales tax payable account found")

        lines.append(JournalEntryLine(
            journal_entry_id=je.id,
            line_number=line_number,
            account_id=tax_account.id,
            area_id=dss.area_id,
            description="Sales tax collected",
            debit_amount=Decimal("0.00"),
            credit_amount=dss.tax_collected
        ))
        line_number += 1

    # DEBIT: Discounts (contra-revenue or expense accounts)
    if dss.discount_breakdown:
        # Import POSDiscountGLMapping to get mapped accounts
        from accounting.models.pos import POSDiscountGLMapping

        # Get discount mappings for this area
        discount_mappings = db.query(POSDiscountGLMapping).filter(
            POSDiscountGLMapping.area_id == dss.area_id,
            POSDiscountGLMapping.is_active == True
        ).all()

        # Create a lookup dictionary
        discount_map = {m.pos_discount_name: m.discount_account_id for m in discount_mappings}

        for discount_name, amount in dss.discount_breakdown.items():
            discount_amount = abs(Decimal(str(amount)))  # Convert negative to positive
            if discount_amount > 0:
                # Get account from mapping
                account_id = discount_map.get(discount_name)

                if not account_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No discount account mapped for discount: {discount_name}. Please configure in POS Settings."
                    )

                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=account_id,
                    area_id=dss.area_id,
                    description=f"{discount_name}",
                    debit_amount=discount_amount,
                    credit_amount=Decimal("0.00")
                ))
                line_number += 1

    # DEBIT: Refunds (contra-revenue account - Sales Returns & Allowances)
    if dss.refunds and dss.refunds > 0:
        # Find or create Sales Returns & Allowances account (contra-revenue)
        refund_account = db.query(Account).filter(
            Account.account_type == "REVENUE",
            Account.account_name.ilike("%return%")
        ).first()

        if not refund_account:
            # Try to find any contra-revenue account
            refund_account = db.query(Account).filter(
                Account.account_type == "REVENUE",
                Account.account_name.ilike("%allowance%")
            ).first()

        if not refund_account:
            raise HTTPException(
                status_code=400,
                detail="No Sales Returns & Allowances account found. Please create a contra-revenue account."
            )

        lines.append(JournalEntryLine(
            journal_entry_id=je.id,
            line_number=line_number,
            account_id=refund_account.id,
            area_id=dss.area_id,
            description="Sales refunds",
            debit_amount=dss.refunds,
            credit_amount=Decimal("0.00")
        ))
        line_number += 1

    # Add all lines to JE
    je.lines = lines

    # Verify debits = credits
    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)

    variance = total_debits - total_credits

    # If there's a variance and user provided variance adjustment
    if abs(variance) > Decimal("0.01"):
        if post_request.variance_account_id and post_request.variance_amount is not None:
            # Verify the variance amount matches
            if abs(abs(post_request.variance_amount) - abs(variance)) > Decimal("0.01"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Variance amount mismatch: calculated {variance}, provided {post_request.variance_amount}"
                )

            # Add variance adjustment line
            variance_account = db.query(Account).filter(Account.id == post_request.variance_account_id).first()
            if not variance_account:
                raise HTTPException(status_code=400, detail="Variance account not found")

            # If debits > credits, we need to credit the variance account
            # If credits > debits, we need to debit the variance account
            if variance > 0:
                # Debits exceed credits, credit the variance account
                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=variance_account.id,
                    area_id=dss.area_id,
                    description="Rounding/variance adjustment",
                    debit_amount=Decimal("0.00"),
                    credit_amount=abs(variance)
                ))
            else:
                # Credits exceed debits, debit the variance account
                lines.append(JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=line_number,
                    account_id=variance_account.id,
                    area_id=dss.area_id,
                    description="Rounding/variance adjustment",
                    debit_amount=abs(variance),
                    credit_amount=Decimal("0.00")
                ))

            line_number += 1
            je.lines = lines

            # Recalculate totals
            total_debits = sum(line.debit_amount for line in lines)
            total_credits = sum(line.credit_amount for line in lines)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Journal entry doesn't balance: DR={total_debits}, CR={total_credits}. Please specify a variance account."
            )

    # Final balance check
    if abs(total_debits - total_credits) > Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Journal entry doesn't balance: DR={total_debits}, CR={total_credits}"
        )

    return je


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("/", response_model=List[DailySalesSummaryList])
def list_daily_sales_summaries(
    skip: int = 0,
    limit: int = 100,
    area_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List daily sales summaries with filters"""
    require_permission(current_user, 'daily_sales:view')
    query = db.query(DailySalesSummary)

    # Apply filters
    if area_id:
        query = query.filter(DailySalesSummary.area_id == area_id)
    if status:
        query = query.filter(DailySalesSummary.status == status)
    if start_date:
        query = query.filter(DailySalesSummary.business_date >= start_date)
    if end_date:
        query = query.filter(DailySalesSummary.business_date <= end_date)

    # Order by business date desc
    query = query.order_by(DailySalesSummary.business_date.desc())

    summaries = query.offset(skip).limit(limit).all()
    return summaries


@router.get("/{dss_id}", response_model=DSSSchema)
def get_daily_sales_summary(
    dss_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific daily sales summary with all details"""
    require_permission(current_user, 'daily_sales:view')

    dss = db.query(DailySalesSummary).options(
        joinedload(DailySalesSummary.line_items),
        joinedload(DailySalesSummary.payments),
        joinedload(DailySalesSummary.area)
    ).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    return dss


@router.post("/", response_model=DSSSchema)
def create_daily_sales_summary(
    dss_create: DailySalesSummaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new daily sales summary"""
    require_permission(current_user, 'daily_sales:create')

    # Check if DSS already exists for this date and area
    existing = db.query(DailySalesSummary).filter(
        DailySalesSummary.business_date == dss_create.business_date,
        DailySalesSummary.area_id == dss_create.area_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Daily sales summary already exists for {dss_create.business_date} in this location"
        )

    # Verify location exists
    area = db.query(Area).filter(Area.id == dss_create.area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Location not found")

    # Create DSS
    dss = DailySalesSummary(
        **dss_create.model_dump(exclude={"line_items", "payments"}),
        created_by=current_user.id,
        status="draft"
    )
    db.add(dss)
    db.flush()

    # Add line items
    if dss_create.line_items:
        for item_data in dss_create.line_items:
            item = SalesLineItem(**item_data.model_dump(), dss_id=dss.id)
            db.add(item)

    # Add payments
    if dss_create.payments:
        for payment_data in dss_create.payments:
            payment = SalesPayment(**payment_data.model_dump(), dss_id=dss.id)
            db.add(payment)

    db.commit()
    db.refresh(dss)

    # Load relationships
    dss = db.query(DailySalesSummary).options(
        joinedload(DailySalesSummary.line_items),
        joinedload(DailySalesSummary.payments)
    ).filter(DailySalesSummary.id == dss.id).first()

    return dss


@router.put("/{dss_id}", response_model=DSSSchema)
def update_daily_sales_summary(
    dss_id: int,
    dss_update: DailySalesSummaryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a daily sales summary (only if status is draft)"""
    require_permission(current_user, 'daily_sales:edit')
    dss = db.query(DailySalesSummary).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    if dss.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update DSS in status: {dss.status}. Only draft DSS can be updated."
        )

    # Update fields
    update_data = dss_update.model_dump(exclude_unset=True, exclude={"line_items", "payments"})
    for field, value in update_data.items():
        setattr(dss, field, value)

    # Update line items if provided
    if dss_update.line_items is not None:
        # Delete existing line items
        db.query(SalesLineItem).filter(SalesLineItem.dss_id == dss_id).delete()
        # Add new line items
        for item_data in dss_update.line_items:
            item = SalesLineItem(**item_data.model_dump(), dss_id=dss.id)
            db.add(item)

    # Update payments if provided
    if dss_update.payments is not None:
        # Delete existing payments
        db.query(SalesPayment).filter(SalesPayment.dss_id == dss_id).delete()
        # Add new payments
        for payment_data in dss_update.payments:
            payment = SalesPayment(**payment_data.model_dump(), dss_id=dss.id)
            db.add(payment)

    dss.updated_at = datetime.now()
    db.commit()
    db.refresh(dss)

    # Load relationships
    dss = db.query(DailySalesSummary).options(
        joinedload(DailySalesSummary.line_items),
        joinedload(DailySalesSummary.payments)
    ).filter(DailySalesSummary.id == dss.id).first()

    return dss


@router.delete("/{dss_id}")
def delete_daily_sales_summary(
    dss_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a daily sales summary

    - Draft entries: can be deleted by anyone with daily_sales:delete permission
    - Verified/Posted entries: can only be deleted by users with daily_sales:reopen permission (admins)
    """
    require_permission(current_user, 'daily_sales:delete')

    dss = db.query(DailySalesSummary).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    # Only draft entries can be deleted by regular users
    # Verified/Posted entries require admin permission
    if dss.status != "draft":
        # Check if user has reopen permission (admin-level)
        try:
            require_permission(current_user, 'daily_sales:reopen')
        except HTTPException:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete DSS in status: {dss.status}. Only draft DSS can be deleted, or you need admin permission to delete verified/posted entries."
            )

    db.delete(dss)
    db.commit()

    return {"message": "Daily sales summary deleted successfully"}


# ============================================================================
# Workflow Endpoints
# ============================================================================

@router.post("/{dss_id}/verify", response_model=DSSSchema)
def verify_daily_sales_summary(
    dss_id: int,
    verify_request: DSSVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Verify a daily sales summary (draft -> verified)"""
    require_permission(current_user, 'daily_sales:verify')
    dss = db.query(DailySalesSummary).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    if dss.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot verify DSS in status: {dss.status}. Only draft DSS can be verified."
        )

    # Note: Cash variance is now handled separately through the Cash Reconciliation system
    # Managers reconcile actual cash deposits, and any variance creates a cash over/short JE

    # Update status
    dss.status = "verified"
    dss.verified_by = current_user.id
    dss.verified_at = datetime.now()

    if verify_request.notes:
        if dss.notes:
            dss.notes += f"\n\nVerification Notes: {verify_request.notes}"
        else:
            dss.notes = f"Verification Notes: {verify_request.notes}"

    db.commit()
    db.refresh(dss)

    return dss


@router.post("/{dss_id}/post", response_model=DSSSchema)
def post_daily_sales_summary(
    dss_id: int,
    post_request: DSSPostRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Post a daily sales summary (verified -> posted) and create journal entry"""
    require_permission(current_user, 'daily_sales:post')
    dss = db.query(DailySalesSummary).options(
        joinedload(DailySalesSummary.line_items),
        joinedload(DailySalesSummary.payments),
        joinedload(DailySalesSummary.area)
    ).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    if dss.status != "verified":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot post DSS in status: {dss.status}. Only verified DSS can be posted."
        )

    try:
        # Create journal entry
        dss.posted_by = current_user.id
        je = create_sales_journal_entry(dss, db, post_request)

        # Update DSS status
        dss.status = "posted"
        dss.posted_at = datetime.now()
        dss.journal_entry_id = je.id

        if post_request.notes:
            if dss.notes:
                dss.notes += f"\n\nPosting Notes: {post_request.notes}"
            else:
                dss.notes = f"Posting Notes: {post_request.notes}"

        # Add note about JE
        if dss.notes:
            dss.notes += f"\nJournal Entry Created: {je.entry_number}"
        else:
            dss.notes = f"Journal Entry Created: {je.entry_number}"

        db.commit()
        db.refresh(dss)

        return dss

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error posting DSS: {str(e)}")


@router.post("/{dss_id}/reconcile-cash", response_model=DSSSchema)
def reconcile_cash(
    dss_id: int,
    reconcile_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Reconcile actual cash deposit for a DSS entry (manager function)"""
    # Managers need daily_sales:edit or cash_reconciliation permission
    try:
        require_permission(current_user, 'cash_reconciliation')
    except HTTPException:
        # Fallback to daily_sales:edit if cash_reconciliation permission doesn't exist
        require_permission(current_user, 'daily_sales:edit')

    dss = db.query(DailySalesSummary).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    # Get actual cash deposit from request
    actual_cash = Decimal(str(reconcile_data.get('actual_cash_deposit', 0)))
    notes = reconcile_data.get('notes', '')

    # Update cash reconciliation fields
    expected_cash = dss.expected_cash_deposit or Decimal('0')
    dss.actual_cash_deposit = actual_cash
    dss.cash_variance = actual_cash - expected_cash
    dss.cash_reconciled_by = current_user.id
    dss.cash_reconciled_at = datetime.now()

    # Add notes if provided
    if notes:
        if dss.notes:
            dss.notes += f"\n\nCash Reconciliation Notes: {notes}"
        else:
            dss.notes = f"Cash Reconciliation Notes: {notes}"

    # Create journal entry for cash variance if variance exists
    if abs(dss.cash_variance) > Decimal('0.01'):
        # Get cash over/short account from settings
        from accounting.models.system_setting import SystemSetting
        cash_over_short_setting = db.query(SystemSetting).filter(
            SystemSetting.setting_key == 'cash_over_short_account_id'
        ).first()

        if not cash_over_short_setting:
            raise HTTPException(status_code=500, detail="Cash Over/Short account not configured in system settings")

        cash_over_short_account_id = int(cash_over_short_setting.setting_value)

        # Get the cash account from the CASH payment line
        cash_payment = next((p for p in dss.payments if p.payment_type == 'CASH'), None)
        if not cash_payment or not cash_payment.deposit_account_id:
            raise HTTPException(status_code=400, detail="No cash deposit account found for this DSS")

        cash_account_id = cash_payment.deposit_account_id

        # Generate entry number
        from accounting.api.journal_entries import generate_entry_number
        entry_number = generate_entry_number(db, dss.business_date)

        # Create journal entry for the variance
        je = JournalEntry(
            entry_date=dss.business_date,
            entry_number=entry_number,
            description=f"Cash Over/Short - {dss.business_date}",
            reference_type="CASH_RECONCILIATION",
            reference_id=dss.id,
            status=JournalEntryStatus.POSTED,
            created_by=current_user.id,
            posted_at=datetime.now()
        )
        db.add(je)
        db.flush()

        # Determine if cash is over or short
        if dss.cash_variance < 0:
            # CASH SHORT: actual < expected
            # DR: Cash Over/Short (Expense)
            # CR: Cash
            lines = [
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=1,
                    account_id=cash_over_short_account_id,
                    area_id=dss.area_id,
                    description=f"Cash short - expected ${expected_cash}, actual ${actual_cash}",
                    debit_amount=abs(dss.cash_variance),
                    credit_amount=Decimal('0.00')
                ),
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=2,
                    account_id=cash_account_id,
                    area_id=dss.area_id,
                    description=f"Cash short adjustment",
                    debit_amount=Decimal('0.00'),
                    credit_amount=abs(dss.cash_variance)
                )
            ]
        else:
            # CASH OVER: actual > expected
            # DR: Cash
            # CR: Cash Over/Short (Income)
            lines = [
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=1,
                    account_id=cash_account_id,
                    area_id=dss.area_id,
                    description=f"Cash over adjustment",
                    debit_amount=dss.cash_variance,
                    credit_amount=Decimal('0.00')
                ),
                JournalEntryLine(
                    journal_entry_id=je.id,
                    line_number=2,
                    account_id=cash_over_short_account_id,
                    area_id=dss.area_id,
                    description=f"Cash over - expected ${expected_cash}, actual ${actual_cash}",
                    debit_amount=Decimal('0.00'),
                    credit_amount=dss.cash_variance
                )
            ]

        je.lines = lines
        db.add_all(lines)

    db.commit()
    db.refresh(dss)

    return dss


@router.post("/{dss_id}/reopen", response_model=DSSSchema)
def reopen_daily_sales_summary(
    dss_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Reopen a posted daily sales summary (requires daily_sales:reopen permission)"""
    require_permission(current_user, 'daily_sales:reopen')

    dss = db.query(DailySalesSummary).options(
        joinedload(DailySalesSummary.journal_entry)
    ).filter(DailySalesSummary.id == dss_id).first()

    if not dss:
        raise HTTPException(status_code=404, detail="Daily sales summary not found")

    if dss.status != "posted":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reopen DSS in status: {dss.status}. Only posted DSS can be reopened."
        )

    try:
        # If there's a linked journal entry, reverse its status
        if dss.journal_entry_id:
            je = dss.journal_entry
            if je:
                # Mark journal entry as reversed
                je.status = JournalEntryStatus.REVERSED

                # Add note to journal entry description
                if je.description:
                    je.description += f"\n\n[REVERSED by {current_user.username} on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"
                else:
                    je.description = f"[REVERSED by {current_user.username} on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"

        # Reset DSS status to draft
        dss.status = "draft"
        dss.verified_by = None
        dss.verified_at = None
        dss.posted_by = None
        dss.posted_at = None

        # Add note about reopening
        if dss.notes:
            dss.notes += f"\n\nReopened by {current_user.username} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        else:
            dss.notes = f"Reopened by {current_user.username} on {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        db.commit()
        db.refresh(dss)

        return dss

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error reopening DSS: {str(e)}")


# ============================================================================
# Import Endpoints
# ============================================================================

@router.post("/import", response_model=DSSImportResponse)
def import_sales_data(
    import_request: DSSImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Import sales data from external POS system
    This endpoint accepts flexible JSON structure and creates a DSS
    """
    # Check if DSS already exists
    existing = db.query(DailySalesSummary).filter(
        DailySalesSummary.business_date == import_request.business_date,
        DailySalesSummary.area_id == import_request.area_id
    ).first()

    if existing:
        return DSSImportResponse(
            success=False,
            message=f"Daily sales summary already exists for {import_request.business_date}",
            dss_id=existing.id,
            business_date=existing.business_date,
            net_sales=existing.net_sales
        )

    # TODO: Parse sales_data based on source_system
    # For now, expect specific structure

    # This is a placeholder - actual implementation would parse POS-specific formats
    sales_data = import_request.sales_data

    # Create DSS from parsed data
    # This structure is illustrative - actual parsing logic would be more complex
    dss_create = DailySalesSummaryCreate(
        business_date=import_request.business_date,
        area_id=import_request.area_id,
        pos_system=import_request.source_system,
        gross_sales=sales_data.get("gross_sales", 0),
        discounts=sales_data.get("discounts", 0),
        refunds=sales_data.get("refunds", 0),
        net_sales=sales_data.get("net_sales", 0),
        tax_collected=sales_data.get("tax_collected", 0),
        tips=sales_data.get("tips", 0),
        total_collected=sales_data.get("total_collected", 0),
        payment_breakdown=sales_data.get("payment_breakdown"),
        category_breakdown=sales_data.get("category_breakdown"),
        imported_from=import_request.source_system
    )

    # Create the DSS
    dss = DailySalesSummary(
        **dss_create.model_dump(),
        created_by=current_user.id,
        imported_at=datetime.now(),
        status="draft"
    )
    db.add(dss)
    db.commit()
    db.refresh(dss)

    return DSSImportResponse(
        success=True,
        message="Sales data imported successfully",
        dss_id=dss.id,
        business_date=dss.business_date,
        net_sales=dss.net_sales
    )
