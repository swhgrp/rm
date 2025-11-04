"""
Journal Entry API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account
from accounting.models.fiscal_period import FiscalPeriod, FiscalPeriodStatus
from accounting.models.user import User
from accounting.api.auth import require_auth, require_admin
from accounting.core.permissions import require_permission
from pydantic import BaseModel, Field, field_validator


# Pydantic schemas
class JournalEntryLineCreate(BaseModel):
    account_id: int
    debit_amount: Decimal = Field(default=Decimal('0.00'), ge=0)
    credit_amount: Decimal = Field(default=Decimal('0.00'), ge=0)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator('debit_amount', 'credit_amount')
    @classmethod
    def validate_amounts(cls, v):
        if v < 0:
            raise ValueError('Amount cannot be negative')
        return v


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str = Field(..., max_length=500)
    reference_type: Optional[str] = Field(None, max_length=50)
    reference_id: Optional[int] = None
    location_id: Optional[int] = None
    lines: List[JournalEntryLineCreate] = Field(..., min_length=2)

    @field_validator('lines')
    @classmethod
    def validate_lines(cls, lines):
        if len(lines) < 2:
            raise ValueError('Journal entry must have at least 2 lines')

        # Calculate totals
        total_debits = sum(line.debit_amount for line in lines)
        total_credits = sum(line.credit_amount for line in lines)

        # Check each line has either debit or credit, not both
        for i, line in enumerate(lines):
            if line.debit_amount > 0 and line.credit_amount > 0:
                raise ValueError(f'Line {i+1}: Cannot have both debit and credit amounts')
            if line.debit_amount == 0 and line.credit_amount == 0:
                raise ValueError(f'Line {i+1}: Must have either debit or credit amount')

        # Validate debits equal credits
        if total_debits != total_credits:
            raise ValueError(
                f'Debits ({total_debits}) must equal credits ({total_credits}). '
                f'Difference: {abs(total_debits - total_credits)}'
            )

        return lines


class JournalEntryLineResponse(BaseModel):
    id: int
    account_id: int
    account_number: str
    account_name: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: Optional[str]

    class Config:
        from_attributes = True


class JournalEntryResponse(BaseModel):
    id: int
    entry_number: str
    entry_date: date
    description: str
    reference_type: Optional[str]
    reference_id: Optional[int]
    location_id: Optional[int]
    status: JournalEntryStatus
    created_at: datetime
    posted_at: Optional[datetime]
    created_by: Optional[int]
    approved_by: Optional[int]
    lines: List[JournalEntryLineResponse]

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/journal-entries", tags=["Journal Entries"])


def validate_fiscal_period(db: Session, entry_date: date, allow_closed: bool = False):
    """Validate that a fiscal period exists and is open for the entry date"""
    period = db.query(FiscalPeriod).filter(
        FiscalPeriod.start_date <= entry_date,
        FiscalPeriod.end_date >= entry_date
    ).first()

    if not period:
        raise HTTPException(
            status_code=400,
            detail=f"No fiscal period found for date {entry_date}"
        )

    if not allow_closed:
        if period.status == FiscalPeriodStatus.CLOSED:
            raise HTTPException(
                status_code=400,
                detail=f"Fiscal period {period.period_name} is closed. Cannot create or modify entries."
            )

        if period.status == FiscalPeriodStatus.LOCKED:
            raise HTTPException(
                status_code=400,
                detail=f"Fiscal period {period.period_name} is locked. Cannot create or modify entries."
            )

    return period


def generate_entry_number(db: Session, entry_date: date) -> str:
    """Generate sequential entry number for the date: JE-YYYYMMDD-NNN"""
    date_str = entry_date.strftime('%Y%m%d')
    prefix = f"JE-{date_str}-"

    # Find the highest number for this date
    last_entry = db.query(JournalEntry).filter(
        JournalEntry.entry_number.like(f"{prefix}%")
    ).order_by(JournalEntry.entry_number.desc()).first()

    if last_entry:
        last_num = int(last_entry.entry_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{prefix}{new_num:03d}"


@router.get("/", response_model=List[JournalEntryResponse])
def list_journal_entries(
    status: Optional[JournalEntryStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    location_id: Optional[int] = None,
    reference_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    List journal entries with optional filters
    """
    require_permission(user, 'journal_entries:view')

    query = db.query(JournalEntry)

    if status:
        query = query.filter(JournalEntry.status == status)

    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)

    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    if location_id:
        query = query.filter(JournalEntry.location_id == location_id)

    if reference_type:
        query = query.filter(JournalEntry.reference_type == reference_type.upper())

    entries = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.entry_number.desc()).offset(skip).limit(limit).all()

    # Enrich with account details
    result = []
    for entry in entries:
        entry_dict = {
            "id": entry.id,
            "entry_number": entry.entry_number,
            "entry_date": entry.entry_date,
            "description": entry.description,
            "reference_type": entry.reference_type,
            "reference_id": entry.reference_id,
            "location_id": entry.location_id,
            "status": entry.status,
            "created_at": entry.created_at,
            "posted_at": entry.posted_at,
            "created_by": entry.created_by,
            "approved_by": entry.approved_by,
            "lines": []
        }

        for line in entry.lines:
            account = db.query(Account).filter(Account.id == line.account_id).first()
            entry_dict["lines"].append({
                "id": line.id,
                "account_id": line.account_id,
                "account_number": account.account_number if account else "UNKNOWN",
                "account_name": account.account_name if account else "UNKNOWN",
                "debit_amount": line.debit_amount,
                "credit_amount": line.credit_amount,
                "description": line.description
            })

        result.append(entry_dict)

    return result


@router.get("/{entry_id}", response_model=JournalEntryResponse)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get a specific journal entry by ID
    """
    require_permission(user, 'journal_entries:view')

    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    # Enrich with account details
    entry_dict = {
        "id": entry.id,
        "entry_number": entry.entry_number,
        "entry_date": entry.entry_date,
        "description": entry.description,
        "reference_type": entry.reference_type,
        "reference_id": entry.reference_id,
        "location_id": entry.location_id,
        "status": entry.status,
        "created_at": entry.created_at,
        "posted_at": entry.posted_at,
        "created_by": entry.created_by,
        "approved_by": entry.approved_by,
        "lines": []
    }

    for line in entry.lines:
        account = db.query(Account).filter(Account.id == line.account_id).first()
        entry_dict["lines"].append({
            "id": line.id,
            "account_id": line.account_id,
            "account_number": account.account_number if account else "UNKNOWN",
            "account_name": account.account_name if account else "UNKNOWN",
            "debit_amount": line.debit_amount,
            "credit_amount": line.credit_amount,
            "description": line.description
        })

    return entry_dict


@router.post("/", response_model=JournalEntryResponse, status_code=201)
def create_journal_entry(
    entry: JournalEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Create a new journal entry (in DRAFT status)
    """
    require_permission(user, 'journal_entries:create')

    # Validate fiscal period is open
    validate_fiscal_period(db, entry.entry_date)

    # Validate all accounts exist
    for line in entry.lines:
        account = db.query(Account).filter(Account.id == line.account_id).first()
        if not account:
            raise HTTPException(status_code=400, detail=f"Account {line.account_id} not found")
        if not account.is_active:
            raise HTTPException(status_code=400, detail=f"Account {account.account_number} is inactive")

    # Generate entry number
    entry_number = generate_entry_number(db, entry.entry_date)

    # Create journal entry
    new_entry = JournalEntry(
        entry_number=entry_number,
        entry_date=entry.entry_date,
        description=entry.description,
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        location_id=entry.location_id,
        created_by=user.id,
        status=JournalEntryStatus.DRAFT
    )
    db.add(new_entry)
    db.flush()  # Get the ID

    # Create journal entry lines
    for line_data in entry.lines:
        line = JournalEntryLine(
            journal_entry_id=new_entry.id,
            account_id=line_data.account_id,
            debit_amount=line_data.debit_amount,
            credit_amount=line_data.credit_amount,
            description=line_data.description
        )
        db.add(line)

    db.commit()
    db.refresh(new_entry)

    # Return with account details
    return get_journal_entry(new_entry.id, db)


@router.post("/{entry_id}/post")
def post_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Post a journal entry (make it immutable)
    """
    require_permission(user, 'journal_entries:approve')

    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status == JournalEntryStatus.POSTED:
        raise HTTPException(status_code=400, detail="Journal entry is already posted")

    if entry.status == JournalEntryStatus.REVERSED:
        raise HTTPException(status_code=400, detail="Cannot post a reversed entry")

    # Validate fiscal period is open
    validate_fiscal_period(db, entry.entry_date)

    # Validate debits equal credits (should already be validated, but double-check)
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)

    if total_debits != total_credits:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot post: debits ({total_debits}) don't equal credits ({total_credits})"
        )

    # Post the entry
    entry.status = JournalEntryStatus.POSTED
    entry.posted_at = func.now()
    entry.approved_by = user.id

    db.commit()

    return {"message": "Journal entry posted successfully", "entry_number": entry.entry_number}


@router.post("/{entry_id}/reverse")
def reverse_journal_entry(
    entry_id: int,
    reversal_date: date = Query(..., description="Date for the reversal entry"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Reverse a posted journal entry by creating an opposite entry
    """
    require_permission(user, 'journal_entries:reverse')

    # Validate fiscal period is open for reversal date
    validate_fiscal_period(db, reversal_date)
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status != JournalEntryStatus.POSTED:
        raise HTTPException(status_code=400, detail="Can only reverse posted entries")

    # Generate reversal entry number
    reversal_number = generate_entry_number(db, reversal_date)

    # Create reversal entry
    reversal_entry = JournalEntry(
        entry_number=reversal_number,
        entry_date=reversal_date,
        description=f"REVERSAL of {entry.entry_number}: {entry.description}",
        reference_type="REVERSAL",
        reference_id=entry.id,
        location_id=entry.location_id,
        status=JournalEntryStatus.DRAFT
    )
    db.add(reversal_entry)
    db.flush()

    # Create reversal lines (swap debits and credits)
    for line in entry.lines:
        reversal_line = JournalEntryLine(
            journal_entry_id=reversal_entry.id,
            account_id=line.account_id,
            debit_amount=line.credit_amount,  # Swap
            credit_amount=line.debit_amount,  # Swap
            description=f"Reversal of {entry.entry_number}"
        )
        db.add(reversal_line)

    # Mark original as reversed
    entry.status = JournalEntryStatus.REVERSED

    db.commit()
    db.refresh(reversal_entry)

    return {
        "message": "Journal entry reversed successfully",
        "original_entry": entry.entry_number,
        "reversal_entry": reversal_entry.entry_number,
        "reversal_id": reversal_entry.id
    }


@router.delete("/{entry_id}")
def delete_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Delete a journal entry (only allowed for DRAFT entries)
    """
    require_permission(user, 'journal_entries:delete')

    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    if entry.status != JournalEntryStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Can only delete DRAFT entries. Use reverse for posted entries."
        )

    # Delete lines first (cascade should handle this, but explicit is better)
    db.query(JournalEntryLine).filter(JournalEntryLine.journal_entry_id == entry_id).delete()

    # Delete entry
    db.delete(entry)
    db.commit()

    return {"message": "Journal entry deleted successfully"}


@router.post("/from-hub")
def receive_journal_entry_from_hub(
    je_data: dict,
    db: Session = Depends(get_db)
):
    """
    Receive journal entry from Integration Hub

    This endpoint is called by the Integration Hub when an invoice is fully mapped
    and ready to create a journal entry in the accounting system.

    Expected payload:
    {
        "entry_date": "2025-10-19",
        "description": "Invoice INV-12345 from US Foods",
        "reference_number": "INV-12345",
        "source": "hub",
        "hub_invoice_id": 123,
        "lines": [
            {
                "account_id": 1418,
                "debit": 87.50,
                "credit": 0.00,
                "description": "Chicken Breast"
            },
            {
                "account_id": 2010,
                "debit": 0.00,
                "credit": 87.50,
                "description": "AP - US Foods"
            }
        ]
    }
    """
    try:
        # Extract data
        entry_date_str = je_data.get("entry_date")
        description = je_data.get("description")
        reference_number = je_data.get("reference_number")
        hub_invoice_id = je_data.get("hub_invoice_id")
        lines_data = je_data.get("lines", [])

        # Parse date
        entry_date = datetime.fromisoformat(entry_date_str).date() if entry_date_str else date.today()

        # Validate we have lines
        if not lines_data or len(lines_data) < 2:
            raise ValueError("Journal entry must have at least 2 lines")

        # Calculate totals and validate
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')

        for line_data in lines_data:
            debit = Decimal(str(line_data.get("debit", 0)))
            credit = Decimal(str(line_data.get("credit", 0)))

            if debit > 0 and credit > 0:
                raise ValueError("Line cannot have both debit and credit amounts")
            if debit == 0 and credit == 0:
                raise ValueError("Line must have either debit or credit amount")

            total_debits += debit
            total_credits += credit

        # Validate balanced
        if abs(total_debits - total_credits) > Decimal('0.01'):
            raise ValueError(
                f"Debits ({total_debits}) must equal credits ({total_credits}). "
                f"Difference: {abs(total_debits - total_credits)}"
            )

        # Find open fiscal period
        fiscal_period = db.query(FiscalPeriod).filter(
            FiscalPeriod.start_date <= entry_date,
            FiscalPeriod.end_date >= entry_date,
            FiscalPeriod.status == FiscalPeriodStatus.OPEN
        ).first()

        if not fiscal_period:
            raise ValueError(f"No open fiscal period found for date {entry_date}")

        # Generate entry number
        # Only look for JE- entries that match the format "JE-NNNNNN"
        # Filter out entries like "JE-BANK-000001" or "DSS-..."
        max_entry_number = db.query(func.max(JournalEntry.entry_number)).filter(
            JournalEntry.entry_number.like('JE-%')
        ).scalar()

        if max_entry_number:
            # Split and get the last part (handle cases like "JE-000001" correctly)
            parts = max_entry_number.split('-')
            if len(parts) == 2 and parts[1].isdigit():
                last_num = int(parts[1])
                new_entry_number = f"JE-{last_num + 1:06d}"
            else:
                # If entry number doesn't match expected format, start fresh
                new_entry_number = "JE-000001"
        else:
            new_entry_number = "JE-000001"

        # Create journal entry
        # Note: fiscal_period validation done above, but not stored in model
        entry = JournalEntry(
            entry_number=new_entry_number,
            entry_date=entry_date,
            description=description,
            reference_type="hub_invoice",
            reference_id=hub_invoice_id,
            status=JournalEntryStatus.POSTED,  # Auto-post from hub
            created_by=1,  # System user - TODO: create dedicated system user
            approved_by=1,  # System user
            posted_at=datetime.utcnow()
        )

        db.add(entry)
        db.flush()  # Get entry ID

        # Create journal entry lines
        for line_data in lines_data:
            account_id = line_data.get("account_id")
            debit = Decimal(str(line_data.get("debit", 0)))
            credit = Decimal(str(line_data.get("credit", 0)))
            line_description = line_data.get("description", "")

            # Verify account exists
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                raise ValueError(f"Account ID {account_id} not found")

            # Create line
            line = JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=account_id,
                debit_amount=debit,
                credit_amount=credit,
                description=line_description
            )

            db.add(line)

            # Note: Account balances are calculated from journal entries, not stored
            # No need to update current_balance field (doesn't exist in model)

        db.commit()

        return {
            "success": True,
            "journal_entry_id": entry.id,
            "entry_number": new_entry_number,
            "message": f"Journal entry {new_entry_number} created successfully",
            "total_debits": float(total_debits),
            "total_credits": float(total_credits)
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating journal entry from hub: {str(e)}"
        )
