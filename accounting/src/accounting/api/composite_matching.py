"""
Composite Matching API Endpoints (Phase 1B)
Handles matching one bank transaction to multiple journal entry lines
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.bank_account import BankTransaction, BankTransactionCompositeMatch
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.account import Account
from accounting.models.area import Area
from accounting.schemas.composite_match import (
    CompositeMatchRequest,
    CompositeMatchResponse,
    CompositeMatchLineResponse,
    CompositeMatchSummary,
    UndepositedFundsLine,
    UndepositedFundsRequest,
    UndepositedFundsResponse,
    UnmatchCompositeRequest,
    UnmatchCompositeResponse,
)
from accounting.api.auth import get_current_user
from accounting.models.user import User

router = APIRouter()


# ============================================================================
# Helper Functions
# ============================================================================

def create_clearing_journal_entry(
    db: Session,
    bank_transaction: BankTransaction,
    matched_lines: List[JournalEntryLine],
    user_id: int,
    area_id: Optional[int] = None
) -> JournalEntry:
    """
    Create clearing journal entry for composite match

    Example:
    Bank deposit: $1,550
    Matched to 3 DSS entries totaling $1,550 to GL 1090

    Clearing JE:
    DR 1021 Checking             $1,550
    CR 1090 Undeposited CC                $1,550
    """
    # Get bank account's GL account
    bank_gl_account_id = bank_transaction.bank_account.gl_account_id
    if not bank_gl_account_id:
        raise HTTPException(status_code=400, detail="Bank account does not have a GL account assigned")

    # Calculate total matched amount
    total_matched = sum(
        line.debit_amount or Decimal(0) for line in matched_lines
    )

    # Determine the GL account being cleared (should be same for all lines)
    undeposited_account_id = matched_lines[0].account_id if matched_lines else None
    if not undeposited_account_id:
        raise HTTPException(status_code=400, detail="Cannot determine undeposited account")

    # Verify all lines are from the same GL account
    for line in matched_lines:
        if line.account_id != undeposited_account_id:
            raise HTTPException(
                status_code=400,
                detail="All matched lines must be from the same GL account"
            )

    # Get next entry number
    max_number = db.query(func.max(JournalEntry.entry_number)).scalar() or "JE-0000"
    next_num = int(max_number.split('-')[1]) + 1
    entry_number = f"JE-{next_num:04d}"

    # Create journal entry
    je = JournalEntry(
        entry_number=entry_number,
        entry_date=bank_transaction.transaction_date,
        description=f"Bank deposit clearing - {bank_transaction.description}",
        status=JournalEntryStatus.POSTED,
        source="bank_composite_match",
        area_id=area_id,
        created_by=user_id,
    )
    db.add(je)
    db.flush()

    # Create debit line (increase bank account)
    debit_line = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=bank_gl_account_id,
        debit_amount=abs(bank_transaction.amount),
        credit_amount=Decimal(0),
        description=f"Deposit from {bank_transaction.description}",
        area_id=area_id,
    )
    db.add(debit_line)

    # Create credit line (clear undeposited funds)
    credit_line = JournalEntryLine(
        journal_entry_id=je.id,
        account_id=undeposited_account_id,
        debit_amount=Decimal(0),
        credit_amount=total_matched,
        description=f"Clear undeposited funds - {len(matched_lines)} transactions",
        area_id=area_id,
    )
    db.add(credit_line)

    db.flush()
    return je


# ============================================================================
# Composite Matching Endpoints
# ============================================================================

@router.post("/{bank_transaction_id}/match-composite", response_model=CompositeMatchResponse)
def create_composite_match(
    bank_transaction_id: int,
    request: CompositeMatchRequest,
    user_id: int = Query(..., description="User ID performing the match"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a composite match - link one bank transaction to multiple JE lines

    Use case: Match a bank deposit to multiple DSS entries
    Example: $1,550 deposit → Day 1 ($500) + Day 2 ($600) + Day 3 ($450)
    """
    # Get bank transaction
    bank_txn = db.query(BankTransaction).filter(BankTransaction.id == bank_transaction_id).first()
    if not bank_txn:
        raise HTTPException(status_code=404, detail="Bank transaction not found")

    # Check if already matched
    if bank_txn.is_composite_match:
        raise HTTPException(status_code=400, detail="Bank transaction is already composite matched. Unmatch first.")

    # Get journal entry lines
    je_lines = db.query(JournalEntryLine).filter(
        JournalEntryLine.id.in_(request.journal_entry_line_ids)
    ).all()

    if len(je_lines) != len(request.journal_entry_line_ids):
        raise HTTPException(status_code=404, detail="One or more journal entry lines not found")

    # Verify lines are from posted entries
    for line in je_lines:
        if line.journal_entry.status != JournalEntryStatus.POSTED:
            raise HTTPException(
                status_code=400,
                detail=f"Journal entry {line.journal_entry.entry_number} is not posted"
            )

    # Calculate total matched amount (use debit amounts for undeposited funds)
    total_matched = sum(line.debit_amount or Decimal(0) for line in je_lines)
    bank_amount = abs(bank_txn.amount)
    difference = bank_amount - total_matched

    # Create clearing journal entry if requested
    clearing_je = None
    if request.create_clearing_entry:
        area_id = je_lines[0].area_id if je_lines else None
        clearing_je = create_clearing_journal_entry(
            db=db,
            bank_transaction=bank_txn,
            matched_lines=je_lines,
            user_id=user_id,
            area_id=area_id
        )

    # Create composite match records
    matches = []
    for line in je_lines:
        match = BankTransactionCompositeMatch(
            bank_transaction_id=bank_txn.id,
            journal_entry_line_id=line.id,
            amount=line.debit_amount or Decimal(0),
            match_type="composite",
            notes=request.notes,
            created_by=user_id,
        )
        db.add(match)
        matches.append(match)

    # Update bank transaction
    bank_txn.is_composite_match = True
    bank_txn.status = "reconciled"
    bank_txn.reconciled_date = date.today()

    # Commit transaction
    db.commit()
    db.refresh(bank_txn)

    # Build response
    match_responses = []
    for match in matches:
        db.refresh(match)
        je_line = next(line for line in je_lines if line.id == match.journal_entry_line_id)
        match_responses.append(CompositeMatchLineResponse(
            id=match.id,
            bank_transaction_id=match.bank_transaction_id,
            journal_entry_line_id=match.journal_entry_line_id,
            amount=match.amount,
            match_type=match.match_type,
            notes=match.notes,
            created_at=match.created_at,
            created_by=match.created_by,
            je_number=je_line.journal_entry.entry_number,
            je_date=je_line.journal_entry.entry_date,
            je_description=je_line.journal_entry.description,
            account_code=je_line.account.code,
            account_name=je_line.account.name,
        ))

    return CompositeMatchResponse(
        success=True,
        bank_transaction_id=bank_txn.id,
        matched_lines_count=len(matches),
        total_matched_amount=total_matched,
        bank_amount=bank_amount,
        difference=difference,
        clearing_journal_entry_id=clearing_je.id if clearing_je else None,
        clearing_entry_number=clearing_je.entry_number if clearing_je else None,
        matches=match_responses,
        message=f"Successfully matched {len(matches)} journal entry lines to bank transaction"
    )


@router.get("/undeposited-lines", response_model=UndepositedFundsResponse)
def get_undeposited_funds_lines(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs (e.g., '1090,1091,1095')"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    area_id: Optional[int] = None,
    only_unmatched: bool = Query(True, description="Only show unmatched lines"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get journal entry lines from Undeposited Funds accounts
    Used to find DSS entries that need to be matched to bank deposits

    Default accounts:
    - 1090: Undeposited Credit Card
    - 1091: Undeposited Cash
    - 1095: Undeposited Third Party Delivery
    """
    # Parse account IDs
    filter_account_ids = None
    if account_ids:
        try:
            filter_account_ids = [int(id.strip()) for id in account_ids.split(',')]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid account_ids format")
    else:
        # Default to standard undeposited accounts
        default_codes = ['1090', '1091', '1095']
        accounts = db.query(Account).filter(Account.code.in_(default_codes)).all()
        filter_account_ids = [acc.id for acc in accounts]

    # Build query
    query = db.query(JournalEntryLine).join(JournalEntry).join(Account)

    # Filter by accounts
    if filter_account_ids:
        query = query.filter(JournalEntryLine.account_id.in_(filter_account_ids))

    # Filter by date range
    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    # Filter by area
    if area_id:
        query = query.filter(JournalEntryLine.area_id == area_id)

    # Only posted entries
    query = query.filter(JournalEntry.status == JournalEntryStatus.POSTED)

    # Only debit entries (deposits to undeposited accounts)
    query = query.filter(JournalEntryLine.debit_amount > 0)

    # Only unmatched if requested
    if only_unmatched:
        # Lines not in composite matches
        matched_line_ids = db.query(BankTransactionCompositeMatch.journal_entry_line_id).distinct()
        query = query.filter(~JournalEntryLine.id.in_(matched_line_ids))

    # Order by date
    query = query.order_by(desc(JournalEntry.entry_date))

    lines = query.all()

    # Build response
    response_lines = []
    for line in lines:
        area = db.query(Area).filter(Area.id == line.area_id).first() if line.area_id else None
        response_lines.append(UndepositedFundsLine(
            id=line.id,
            journal_entry_id=line.journal_entry_id,
            journal_entry_number=line.journal_entry.entry_number,
            journal_entry_date=line.journal_entry.entry_date,
            description=line.journal_entry.description or "",
            account_id=line.account_id,
            account_code=line.account.code,
            account_name=line.account.name,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            amount=line.debit_amount or Decimal(0),
            area_id=line.area_id,
            area_name=area.name if area else None,
        ))

    # Calculate totals
    total_amount = sum(line.amount for line in response_lines)

    # Build accounts summary
    accounts_summary = {}
    for line in response_lines:
        if line.account_id not in accounts_summary:
            accounts_summary[line.account_id] = {
                "account_code": line.account_code,
                "account_name": line.account_name,
                "total_amount": Decimal(0),
                "count": 0
            }
        accounts_summary[line.account_id]["total_amount"] += line.amount
        accounts_summary[line.account_id]["count"] += 1

    return UndepositedFundsResponse(
        lines=response_lines,
        total_amount=total_amount,
        total_count=len(response_lines),
        accounts_summary=accounts_summary
    )


@router.delete("/{bank_transaction_id}/unmatch-composite", response_model=UnmatchCompositeResponse)
def unmatch_composite(
    bank_transaction_id: int,
    request: UnmatchCompositeRequest,
    user_id: int = Query(..., description="User ID performing the unmatch"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Unmatch a composite match - remove all composite match records
    Optionally reverse the clearing journal entry
    """
    # Get bank transaction
    bank_txn = db.query(BankTransaction).filter(BankTransaction.id == bank_transaction_id).first()
    if not bank_txn:
        raise HTTPException(status_code=404, detail="Bank transaction not found")

    # Check if it's a composite match
    if not bank_txn.is_composite_match:
        raise HTTPException(status_code=400, detail="Bank transaction is not a composite match")

    # Get all composite matches
    matches = db.query(BankTransactionCompositeMatch).filter(
        BankTransactionCompositeMatch.bank_transaction_id == bank_transaction_id
    ).all()

    if not matches:
        raise HTTPException(status_code=404, detail="No composite matches found")

    # TODO: Reverse clearing journal entry if requested
    # This would require finding the clearing JE and creating a reversal
    reversal_je_id = None
    reversal_entry_number = None

    # Delete all composite matches
    for match in matches:
        db.delete(match)

    # Update bank transaction
    bank_txn.is_composite_match = False
    bank_txn.status = "unreconciled"
    bank_txn.reconciled_date = None

    db.commit()

    return UnmatchCompositeResponse(
        success=True,
        bank_transaction_id=bank_transaction_id,
        unmatched_lines_count=len(matches),
        reversal_entry_id=reversal_je_id,
        reversal_entry_number=reversal_entry_number,
        message=f"Successfully unmatched {len(matches)} journal entry lines"
    )


@router.get("/{bank_transaction_id}/composite-summary", response_model=CompositeMatchSummary)
def get_composite_match_summary(
    bank_transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary of a composite match
    Shows total matched amount, count of lines, difference
    """
    # Get bank transaction
    bank_txn = db.query(BankTransaction).filter(BankTransaction.id == bank_transaction_id).first()
    if not bank_txn:
        raise HTTPException(status_code=404, detail="Bank transaction not found")

    # Get composite matches
    matches = db.query(BankTransactionCompositeMatch).filter(
        BankTransactionCompositeMatch.bank_transaction_id == bank_transaction_id
    ).all()

    total_matched = sum(match.amount for match in matches)
    bank_amount = abs(bank_txn.amount)
    difference = bank_amount - total_matched

    return CompositeMatchSummary(
        bank_transaction_id=bank_transaction_id,
        transaction_date=bank_txn.transaction_date,
        description=bank_txn.description or "",
        bank_amount=bank_amount,
        matched_lines_count=len(matches),
        total_matched_amount=total_matched,
        difference=difference,
        is_balanced=(difference == 0)
    )
