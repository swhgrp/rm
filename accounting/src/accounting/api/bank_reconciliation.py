"""
Bank Reconciliation API
Endpoints for managing bank reconciliations
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Optional
from datetime import date
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.bank_account import (
    BankAccount,
    BankTransaction,
    BankReconciliation,
    BankReconciliationItem
)
from accounting.models.journal_entry import JournalEntryLine
from accounting.schemas.bank_account import (
    BankReconciliationCreate,
    BankReconciliationUpdate,
    BankReconciliationResponse,
    BankReconciliationItemCreate,
    BankReconciliationItemResponse
)
from accounting.api.auth import get_current_user
from accounting.models.user import User

router = APIRouter()


# ============================================================================
# Bank Reconciliation Management
# ============================================================================

@router.get("/", response_model=List[BankReconciliationResponse])
def list_reconciliations(
    bank_account_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of bank reconciliations"""
    query = db.query(BankReconciliation)

    if bank_account_id:
        query = query.filter(BankReconciliation.bank_account_id == bank_account_id)

    if status:
        query = query.filter(BankReconciliation.status == status)

    reconciliations = query.order_by(
        BankReconciliation.reconciliation_date.desc()
    ).limit(limit).all()

    # Add calculated fields
    for recon in reconciliations:
        recon.cleared_count = len(recon.items)

        # Calculate outstanding checks and deposits in transit
        recon.outstanding_checks = Decimal("0.00")
        recon.deposits_in_transit = Decimal("0.00")

        for item in recon.items:
            if item.bank_transaction and not item.bank_transaction.matched_journal_line_id:
                if item.amount < 0:
                    recon.outstanding_checks += abs(item.amount)
                else:
                    recon.deposits_in_transit += item.amount

    return reconciliations


@router.post("/", response_model=BankReconciliationResponse)
def create_reconciliation(
    reconciliation: BankReconciliationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start a new bank reconciliation"""
    # Verify bank account exists
    bank_account = db.query(BankAccount).filter(
        BankAccount.id == reconciliation.bank_account_id
    ).first()

    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Check if there's already an in-progress reconciliation
    existing = db.query(BankReconciliation).filter(
        and_(
            BankReconciliation.bank_account_id == reconciliation.bank_account_id,
            BankReconciliation.status == "in_progress"
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Reconciliation #{existing.id} is already in progress for this account"
        )

    # Create reconciliation
    db_reconciliation = BankReconciliation(
        **reconciliation.dict(),
        reconciled_by=current_user.id
    )

    db.add(db_reconciliation)
    db.commit()
    db.refresh(db_reconciliation)

    # Initialize calculated fields
    db_reconciliation.cleared_count = 0
    db_reconciliation.outstanding_checks = Decimal("0.00")
    db_reconciliation.deposits_in_transit = Decimal("0.00")

    return db_reconciliation


@router.get("/{reconciliation_id}", response_model=BankReconciliationResponse)
def get_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get reconciliation by ID"""
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Add calculated fields
    reconciliation.cleared_count = len(reconciliation.items)

    # Calculate outstanding items
    reconciliation.outstanding_checks = Decimal("0.00")
    reconciliation.deposits_in_transit = Decimal("0.00")

    for item in reconciliation.items:
        if item.bank_transaction and not item.bank_transaction.matched_journal_line_id:
            if item.amount < 0:
                reconciliation.outstanding_checks += abs(item.amount)
            else:
                reconciliation.deposits_in_transit += item.amount

    return reconciliation


@router.put("/{reconciliation_id}", response_model=BankReconciliationResponse)
def update_reconciliation(
    reconciliation_id: int,
    reconciliation_update: BankReconciliationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update reconciliation"""
    db_reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not db_reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Don't allow updating locked reconciliations
    if db_reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot update locked reconciliation"
        )

    # Update fields
    update_data = reconciliation_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_reconciliation, field, value)

    db.commit()
    db.refresh(db_reconciliation)

    # Add calculated fields
    db_reconciliation.cleared_count = len(db_reconciliation.items)
    db_reconciliation.outstanding_checks = Decimal("0.00")
    db_reconciliation.deposits_in_transit = Decimal("0.00")

    return db_reconciliation


@router.post("/{reconciliation_id}/balance", response_model=dict)
def calculate_balance(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate reconciliation balance and difference"""
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Calculate cleared balance (sum of cleared items from bank)
    cleared_balance = Decimal("0.00")
    for item in reconciliation.items:
        if item.bank_transaction:
            cleared_balance += item.amount

    # Get book balance from GL account
    bank_account = reconciliation.bank_account
    if bank_account and bank_account.gl_account_id:
        # TODO: Calculate actual GL balance as of reconciliation date
        book_balance = bank_account.current_balance or Decimal("0.00")
    else:
        book_balance = Decimal("0.00")

    # Calculate difference
    # Difference = Statement Ending Balance - Cleared Balance
    # When all items are cleared, this should be $0
    difference = reconciliation.ending_balance - cleared_balance

    # Update reconciliation
    reconciliation.cleared_balance = cleared_balance
    reconciliation.book_balance = book_balance
    reconciliation.difference = difference

    # Check if balanced
    if abs(difference) < Decimal("0.01"):  # Within 1 cent
        reconciliation.status = "balanced"

    db.commit()

    return {
        "beginning_balance": reconciliation.beginning_balance,
        "ending_balance": reconciliation.ending_balance,
        "cleared_balance": cleared_balance,
        "book_balance": book_balance,
        "difference": difference,
        "is_balanced": abs(difference) < Decimal("0.01")
    }


@router.post("/{reconciliation_id}/lock", response_model=BankReconciliationResponse)
def lock_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lock a reconciliation (finalize it)"""
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Check if balanced
    if reconciliation.status != "balanced":
        raise HTTPException(
            status_code=400,
            detail="Can only lock a balanced reconciliation"
        )

    # Lock reconciliation
    from datetime import datetime
    reconciliation.status = "locked"
    reconciliation.locked_by = current_user.id
    reconciliation.locked_at = datetime.now()

    # Mark all cleared transactions as reconciled
    for item in reconciliation.items:
        if item.bank_transaction:
            item.bank_transaction.status = "reconciled"
            item.bank_transaction.reconciled_date = reconciliation.reconciliation_date

    db.commit()
    db.refresh(reconciliation)

    reconciliation.cleared_count = len(reconciliation.items)
    reconciliation.outstanding_checks = Decimal("0.00")
    reconciliation.deposits_in_transit = Decimal("0.00")

    return reconciliation


@router.delete("/{reconciliation_id}")
def delete_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete reconciliation (only if not locked)"""
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Don't allow deleting locked reconciliations
    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete locked reconciliation"
        )

    db.delete(reconciliation)
    db.commit()

    return {"message": "Reconciliation deleted successfully"}


# ============================================================================
# Reconciliation Items (Cleared Transactions)
# ============================================================================

@router.get("/{reconciliation_id}/items", response_model=List[BankReconciliationItemResponse])
def list_reconciliation_items(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get cleared items for a reconciliation"""
    items = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.reconciliation_id == reconciliation_id
    ).all()

    return items


@router.post("/{reconciliation_id}/items", response_model=BankReconciliationItemResponse)
def add_reconciliation_item(
    reconciliation_id: int,
    item: BankReconciliationItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add an item to reconciliation (mark as cleared)"""
    # Verify reconciliation exists and is not locked
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot add items to locked reconciliation"
        )

    # Create item
    db_item = BankReconciliationItem(
        reconciliation_id=reconciliation_id,
        **item.dict(exclude={"reconciliation_id"})
    )

    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    return db_item


@router.delete("/{reconciliation_id}/items/{item_id}")
def remove_reconciliation_item(
    reconciliation_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove an item from reconciliation (unmark as cleared)"""
    # Verify reconciliation is not locked
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot remove items from locked reconciliation"
        )

    # Delete item
    item = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.id == item_id,
        BankReconciliationItem.reconciliation_id == reconciliation_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()

    return {"message": "Item removed from reconciliation"}


@router.post("/{reconciliation_id}/clear-transaction/{transaction_id}")
def clear_transaction(
    reconciliation_id: int,
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a bank transaction as cleared in this reconciliation"""
    # Verify reconciliation
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify locked reconciliation"
        )

    # Verify transaction
    transaction = db.query(BankTransaction).filter(
        BankTransaction.id == transaction_id,
        BankTransaction.bank_account_id == reconciliation.bank_account_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Check if already cleared
    existing = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.reconciliation_id == reconciliation_id,
        BankReconciliationItem.bank_transaction_id == transaction_id
    ).first()

    if existing:
        return {"message": "Transaction already cleared"}

    # Create reconciliation item
    item = BankReconciliationItem(
        reconciliation_id=reconciliation_id,
        bank_transaction_id=transaction_id,
        amount=transaction.amount,
        item_type="bank_transaction",
        cleared_date=reconciliation.statement_date
    )

    db.add(item)
    db.commit()

    return {"message": "Transaction marked as cleared"}


@router.delete("/{reconciliation_id}/clear-transaction/{transaction_id}")
def unclear_transaction(
    reconciliation_id: int,
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unmark a bank transaction as cleared"""
    # Verify reconciliation is not locked
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify locked reconciliation"
        )

    # Find and delete item
    item = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.reconciliation_id == reconciliation_id,
        BankReconciliationItem.bank_transaction_id == transaction_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Transaction not cleared in this reconciliation")

    db.delete(item)
    db.commit()

    return {"message": "Transaction unmarked as cleared"}


@router.post("/{reconciliation_id}/clear-gl-entry/{line_id}")
def clear_gl_entry(
    reconciliation_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a GL entry as cleared in this reconciliation"""
    # Verify reconciliation
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify locked reconciliation"
        )

    # Verify GL entry line exists
    gl_line = db.query(JournalEntryLine).filter(
        JournalEntryLine.id == line_id
    ).first()

    if not gl_line:
        raise HTTPException(status_code=404, detail="GL entry not found")

    # Check if already cleared
    existing = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.reconciliation_id == reconciliation_id,
        BankReconciliationItem.journal_entry_line_id == line_id
    ).first()

    if existing:
        return {"message": "GL entry already cleared"}

    # Calculate amount (debit - credit)
    amount = (gl_line.debit_amount or 0) - (gl_line.credit_amount or 0)

    # Create reconciliation item
    item = BankReconciliationItem(
        reconciliation_id=reconciliation_id,
        journal_entry_line_id=line_id,
        amount=amount,
        item_type="gl_entry",
        cleared_date=reconciliation.statement_date
    )

    db.add(item)
    db.commit()

    return {"message": "GL entry marked as cleared"}


@router.delete("/{reconciliation_id}/clear-gl-entry/{line_id}")
def unclear_gl_entry(
    reconciliation_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unmark a GL entry as cleared"""
    # Verify reconciliation is not locked
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify locked reconciliation"
        )

    # Find and delete item
    item = db.query(BankReconciliationItem).filter(
        BankReconciliationItem.reconciliation_id == reconciliation_id,
        BankReconciliationItem.journal_entry_line_id == line_id
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="GL entry not cleared in this reconciliation")

    db.delete(item)
    db.commit()

    return {"message": "GL entry unmarked as cleared"}


# ============================================================================
# Reconciliation Workspace Data
# ============================================================================

@router.get("/{reconciliation_id}/workspace", response_model=dict)
def get_reconciliation_workspace(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all data needed for reconciliation workspace UI
    Returns reconciliation, unreconciled transactions, and GL entries
    """
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Get unreconciled bank transactions
    bank_transactions = db.query(BankTransaction).filter(
        and_(
            BankTransaction.bank_account_id == reconciliation.bank_account_id,
            BankTransaction.transaction_date <= reconciliation.statement_date,
            BankTransaction.status == "unreconciled"
        )
    ).order_by(BankTransaction.transaction_date).all()

    # Get cleared transaction IDs
    cleared_ids = [
        item.bank_transaction_id
        for item in reconciliation.items
        if item.bank_transaction_id
    ]

    # Get unmatched GL entries for the account
    gl_entries = []
    if reconciliation.bank_account.gl_account_id:
        gl_entries = db.query(JournalEntryLine).filter(
            and_(
                JournalEntryLine.account_id == reconciliation.bank_account.gl_account_id,
                JournalEntryLine.id.notin_(
                    db.query(BankTransaction.matched_journal_line_id).filter(
                        BankTransaction.matched_journal_line_id.isnot(None)
                    )
                )
            )
        ).limit(100).all()

    # Calculate balances
    cleared_balance = sum(item.amount for item in reconciliation.items)

    # Convert SQLAlchemy objects to dictionaries
    def serialize_reconciliation(recon):
        return {
            "id": recon.id,
            "bank_account_id": recon.bank_account_id,
            "reconciliation_date": recon.reconciliation_date.isoformat() if recon.reconciliation_date else None,
            "statement_date": recon.statement_date.isoformat() if recon.statement_date else None,
            "beginning_balance": float(recon.beginning_balance) if recon.beginning_balance else 0.0,
            "ending_balance": float(recon.ending_balance) if recon.ending_balance else 0.0,
            "status": recon.status,
            "created_at": recon.created_at.isoformat() if recon.created_at else None,
            "cleared_count": len(recon.items)
        }

    def serialize_bank_transaction(txn):
        return {
            "id": txn.id,
            "bank_account_id": txn.bank_account_id,
            "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
            "description": txn.description,
            "amount": float(txn.amount) if txn.amount else 0.0,
            "check_number": txn.check_number,
            "status": txn.status,
            "matched_journal_line_id": txn.matched_journal_line_id,
            "is_composite_match": txn.is_composite_match if hasattr(txn, 'is_composite_match') else False
        }

    def serialize_gl_entry(entry):
        return {
            "id": entry.id,
            "journal_entry_id": entry.journal_entry_id,
            "account_id": entry.account_id,
            "debit_amount": float(entry.debit_amount) if entry.debit_amount else 0.0,
            "credit_amount": float(entry.credit_amount) if entry.credit_amount else 0.0,
            "description": entry.description,
            "journal_entry": {
                "id": entry.journal_entry.id,
                "entry_date": entry.journal_entry.entry_date.isoformat() if entry.journal_entry.entry_date else None,
                "description": entry.journal_entry.description,
                "status": entry.journal_entry.status
            } if entry.journal_entry else None,
            "amount": float(entry.debit_amount or 0) - float(entry.credit_amount or 0)
        }

    return {
        "reconciliation": serialize_reconciliation(reconciliation),
        "bank_account": {
            "id": reconciliation.bank_account.id,
            "account_name": reconciliation.bank_account.account_name,
            "account_number": reconciliation.bank_account.account_number,
            "institution_name": reconciliation.bank_account.institution_name,
            "current_balance": float(reconciliation.bank_account.current_balance) if reconciliation.bank_account.current_balance else 0.0
        },
        "unreconciled_transactions": [serialize_bank_transaction(txn) for txn in bank_transactions],
        "unreconciled_gl_entries": [serialize_gl_entry(entry) for entry in gl_entries],
        "cleared_items": [
            {
                "bank_transaction_id": item.bank_transaction_id,
                "journal_entry_line_id": item.journal_entry_line_id
            }
            for item in reconciliation.items
        ],
        "cleared_balance": float(cleared_balance),
        "outstanding_count": len(bank_transactions) - len(cleared_ids)
    }


@router.get("/{reconciliation_id}/outstanding-items", response_model=dict)
def get_outstanding_items(
    reconciliation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get outstanding checks and deposits in transit"""
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    # Get all transactions before statement date that aren't cleared
    cleared_ids = [
        item.bank_transaction_id
        for item in reconciliation.items
        if item.bank_transaction_id
    ]

    outstanding = db.query(BankTransaction).filter(
        and_(
            BankTransaction.bank_account_id == reconciliation.bank_account_id,
            BankTransaction.transaction_date <= reconciliation.statement_date,
            BankTransaction.id.notin_(cleared_ids) if cleared_ids else True
        )
    ).all()

    outstanding_checks = [txn for txn in outstanding if txn.amount < 0]
    deposits_in_transit = [txn for txn in outstanding if txn.amount >= 0]

    return {
        "outstanding_checks": outstanding_checks,
        "outstanding_checks_total": sum(abs(txn.amount) for txn in outstanding_checks),
        "deposits_in_transit": deposits_in_transit,
        "deposits_in_transit_total": sum(txn.amount for txn in deposits_in_transit)
    }


@router.post("/{reconciliation_id}/create-adjustment")
def create_bank_adjustment(
    reconciliation_id: int,
    bank_transaction_id: int,
    gl_account_id: int,
    description: str,
    transaction_date: date,
    amount: Decimal,
    adjustment_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a bank adjustment journal entry for unmatched transactions
    (fees, interest, NSF charges, etc.)
    """
    from accounting.models.journal_entry import JournalEntry
    from accounting.models.account import Account

    # Verify reconciliation exists and is not locked
    reconciliation = db.query(BankReconciliation).filter(
        BankReconciliation.id == reconciliation_id
    ).first()

    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")

    if reconciliation.status == "locked":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify locked reconciliation"
        )

    # Get bank transaction
    bank_txn = db.query(BankTransaction).filter(
        BankTransaction.id == bank_transaction_id
    ).first()

    if not bank_txn:
        raise HTTPException(status_code=404, detail="Bank transaction not found")

    # Get bank account to find checking GL account
    bank_account = db.query(BankAccount).filter(
        BankAccount.id == reconciliation.bank_account_id
    ).first()

    if not bank_account or not bank_account.gl_account_id:
        raise HTTPException(
            status_code=400,
            detail="Bank account does not have a linked GL account"
        )

    # Get the GL accounts
    checking_account = db.query(Account).filter(
        Account.id == bank_account.gl_account_id
    ).first()

    adjustment_account = db.query(Account).filter(
        Account.id == gl_account_id
    ).first()

    if not adjustment_account:
        raise HTTPException(status_code=404, detail="GL account not found")

    # Determine if this is an expense (negative) or income (positive)
    is_expense = bank_txn.amount < 0

    # Create journal entry
    entry_number = f"BAJ-{reconciliation_id}-{bank_transaction_id}"

    journal_entry = JournalEntry(
        entry_number=entry_number,
        entry_date=transaction_date,
        description=description,
        reference_type="bank_adjustment",
        reference_id=bank_transaction_id,
        location_id=reconciliation.bank_account.location_id if hasattr(reconciliation.bank_account, 'location_id') else None,
        created_by=current_user.id if current_user else None,
        status="POSTED"
    )
    db.add(journal_entry)
    db.flush()  # Get the ID

    # Create journal entry lines
    abs_amount = abs(amount)

    if is_expense:
        # Bank charge/expense: DR Expense Account / CR Checking
        line1 = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=adjustment_account.id,
            debit_amount=abs_amount,
            credit_amount=None,
            description=f"{adjustment_type.replace('_', ' ').title()} - {description}"
        )
        line2 = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=checking_account.id,
            debit_amount=None,
            credit_amount=abs_amount,
            description=f"Bank adjustment - {bank_account.account_name}"
        )
    else:
        # Bank credit/income: DR Checking / CR Income Account
        line1 = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=checking_account.id,
            debit_amount=abs_amount,
            credit_amount=None,
            description=f"Bank adjustment - {bank_account.account_name}"
        )
        line2 = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=adjustment_account.id,
            debit_amount=None,
            credit_amount=abs_amount,
            description=f"{adjustment_type.replace('_', ' ').title()} - {description}"
        )

    db.add(line1)
    db.add(line2)

    # Mark bank transaction as cleared in reconciliation
    # Find the checking account GL line we just created
    checking_line = line1 if is_expense else line2

    reconciliation_item = BankReconciliationItem(
        reconciliation_id=reconciliation_id,
        bank_transaction_id=bank_transaction_id,
        journal_entry_line_id=checking_line.id,
        amount=bank_txn.amount,
        item_type="bank_adjustment",
        cleared_date=transaction_date,
        notes=f"Adjustment: {adjustment_type}"
    )
    db.add(reconciliation_item)

    # Commit all changes
    db.commit()

    return {
        "message": "Bank adjustment created successfully",
        "journal_entry_id": journal_entry.id,
        "journal_entry_number": journal_entry.entry_number,
        "bank_transaction_id": bank_transaction_id,
        "amount": float(abs_amount),
        "adjustment_type": adjustment_type
    }
