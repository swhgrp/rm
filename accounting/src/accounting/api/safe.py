"""
API endpoints for Safe Management
Tracks cash movements in/out of the restaurant safe
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, desc
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.safe_transaction import SafeTransaction
from accounting.models.area import Area
from accounting.models.account import Account
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.schemas.safe_transaction import (
    SafeTransactionCreate,
    SafeTransactionUpdate,
    SafeTransactionResponse,
    SafeBalanceResponse,
    SafeDashboardResponse,
    SafePostRequest,
    SafeReconciliationRequest
)
from accounting.api.auth import require_auth
from accounting.core.permissions import require_permission

router = APIRouter(prefix="/api/safe", tags=["safe"])


def get_user_accessible_areas(db: Session, user: User) -> List[int]:
    """Get list of area IDs that a user has access to based on their role"""
    if user.is_admin:
        # Admins can access all areas
        return [area.id for area in db.query(Area).filter(Area.is_active == True).all()]

    if not user.role_id:
        # User has no role assigned, no access
        return []

    # Get areas assigned to user's role
    from accounting.models.role import role_areas, Role

    role = db.query(Role).filter(Role.id == user.role_id).first()
    if not role:
        return []

    return [area.id for area in role.areas if area.is_active]


def calculate_safe_balance(db: Session, area_id: int, up_to_date: Optional[date] = None) -> Decimal:
    """Calculate current safe balance for an area from its assigned GL safe account"""
    # Get the area to find its safe account
    area = db.query(Area).filter(Area.id == area_id).first()
    if not area or not area.safe_account_id:
        # No safe account configured for this area - return 0
        return Decimal('0')

    # Get the safe GL account for this area
    safe_account = db.query(Account).filter(Account.id == area.safe_account_id).first()

    if not safe_account:
        # Fallback to transaction-based calculation if GL account not found
        query = db.query(func.sum(
            func.case(
                (SafeTransaction.transaction_type == 'deposit', SafeTransaction.amount),
                (SafeTransaction.transaction_type == 'withdrawal', -SafeTransaction.amount),
                (SafeTransaction.transaction_type == 'adjustment', SafeTransaction.amount),
                else_=Decimal('0')
            )
        )).filter(
            SafeTransaction.area_id == area_id,
            SafeTransaction.is_posted == True
        )
        if up_to_date:
            query = query.filter(SafeTransaction.transaction_date <= up_to_date)
        balance = query.scalar()
        return balance or Decimal('0')

    # Calculate from GL (debits - credits for asset account)
    query = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount), Decimal('0')) -
        func.coalesce(func.sum(JournalEntryLine.credit_amount), Decimal('0'))
    ).join(
        JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id
    ).filter(
        JournalEntryLine.account_id == safe_account.id,
        JournalEntryLine.area_id == area_id,
        JournalEntry.status == JournalEntryStatus.POSTED
    )

    if up_to_date:
        query = query.filter(JournalEntry.entry_date <= up_to_date)

    balance = query.scalar()
    return balance or Decimal('0')


@router.get("/dashboard", response_model=SafeDashboardResponse)
def get_safe_dashboard(
    area_id: Optional[int] = Query(None, description="Filter by area"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get safe management dashboard with balances and recent activity"""
    require_permission(current_user, 'safe:view')

    # Get user's accessible areas
    accessible_area_ids = get_user_accessible_areas(db, current_user)
    if not accessible_area_ids:
        # User has no access to any areas
        return SafeDashboardResponse(balances=[], recent_transactions=[])

    # Get areas to show balances for
    areas_query = db.query(Area).filter(
        Area.is_active == True,
        Area.id.in_(accessible_area_ids)
    )
    if area_id:
        # Additional filter if specific area requested
        if area_id not in accessible_area_ids:
            # User trying to access area they don't have permission for
            raise HTTPException(status_code=403, detail="Access denied to this area")
        areas_query = areas_query.filter(Area.id == area_id)

    areas = areas_query.all()

    balances = []
    for area in areas:
        current_balance = calculate_safe_balance(db, area.id)

        # Get last transaction date
        last_txn = db.query(SafeTransaction).filter(
            SafeTransaction.area_id == area.id,
            SafeTransaction.is_posted == True
        ).order_by(desc(SafeTransaction.transaction_date)).first()

        # Count unposted and pending approvals
        unposted = db.query(func.count(SafeTransaction.id)).filter(
            SafeTransaction.area_id == area.id,
            SafeTransaction.is_posted == False
        ).scalar()

        pending_approvals = db.query(func.count(SafeTransaction.id)).filter(
            SafeTransaction.area_id == area.id,
            SafeTransaction.is_posted == False,
            SafeTransaction.approved_at == None
        ).scalar()

        balances.append(SafeBalanceResponse(
            area_id=area.id,
            area_name=area.name,
            current_balance=current_balance,
            last_transaction_date=last_txn.transaction_date if last_txn else None,
            unposted_count=unposted or 0,
            pending_approvals=pending_approvals or 0
        ))

    # Get recent transactions (filtered by accessible areas)
    recent_query = db.query(SafeTransaction).options(
        joinedload(SafeTransaction.area),
        joinedload(SafeTransaction.creator)
    ).filter(
        SafeTransaction.area_id.in_(accessible_area_ids)
    ).order_by(desc(SafeTransaction.created_at)).limit(20)

    if area_id:
        recent_query = recent_query.filter(SafeTransaction.area_id == area_id)

    recent_txns = recent_query.all()

    recent_transactions = []
    for txn in recent_txns:
        recent_transactions.append(SafeTransactionResponse(
            id=txn.id,
            transaction_date=txn.transaction_date,
            area_id=txn.area_id,
            transaction_type=txn.transaction_type,
            amount=txn.amount,
            description=txn.description,
            notes=txn.notes,
            reference_type=txn.reference_type,
            reference_id=txn.reference_id,
            balance_after=txn.balance_after,
            journal_entry_id=txn.journal_entry_id,
            is_posted=txn.is_posted,
            created_by=txn.created_by,
            created_at=txn.created_at,
            approved_by=txn.approved_by,
            approved_at=txn.approved_at,
            posted_by=txn.posted_by,
            posted_at=txn.posted_at,
            area_name=txn.area.name,
            creator_name=txn.creator.full_name if txn.creator else None
        ))

    # Generate alerts
    alerts = []
    for balance in balances:
        if balance.current_balance < 100:
            alerts.append(f"{balance.area_name}: Low safe balance (${balance.current_balance:.2f})")
        if balance.pending_approvals > 0:
            alerts.append(f"{balance.area_name}: {balance.pending_approvals} transactions pending approval")

    return SafeDashboardResponse(
        balances=balances,
        recent_transactions=recent_transactions,
        alerts=alerts
    )


@router.get("/transactions", response_model=List[SafeTransactionResponse])
def get_safe_transactions(
    area_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[str] = Query(None),
    is_posted: Optional[bool] = Query(None),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get list of safe transactions with filters"""
    require_permission(current_user, 'safe:view')

    # Get user's accessible areas
    accessible_area_ids = get_user_accessible_areas(db, current_user)
    if not accessible_area_ids:
        return []

    query = db.query(SafeTransaction).options(
        joinedload(SafeTransaction.area),
        joinedload(SafeTransaction.creator)
    ).filter(
        SafeTransaction.area_id.in_(accessible_area_ids)
    )

    if area_id:
        # Check if user has access to this specific area
        if area_id not in accessible_area_ids:
            raise HTTPException(status_code=403, detail="Access denied to this area")
        query = query.filter(SafeTransaction.area_id == area_id)
    if start_date:
        query = query.filter(SafeTransaction.transaction_date >= start_date)
    if end_date:
        query = query.filter(SafeTransaction.transaction_date <= end_date)
    if transaction_type:
        query = query.filter(SafeTransaction.transaction_type == transaction_type)
    if is_posted is not None:
        query = query.filter(SafeTransaction.is_posted == is_posted)

    transactions = query.order_by(desc(SafeTransaction.transaction_date), desc(SafeTransaction.id)).all()

    return [SafeTransactionResponse(
        id=txn.id,
        transaction_date=txn.transaction_date,
        area_id=txn.area_id,
        transaction_type=txn.transaction_type,
        amount=txn.amount,
        description=txn.description,
        notes=txn.notes,
        reference_type=txn.reference_type,
        reference_id=txn.reference_id,
        balance_after=txn.balance_after,
        journal_entry_id=txn.journal_entry_id,
        is_posted=txn.is_posted,
        created_by=txn.created_by,
        created_at=txn.created_at,
        approved_by=txn.approved_by,
        approved_at=txn.approved_at,
        posted_by=txn.posted_by,
        posted_at=txn.posted_at,
        area_name=txn.area.name,
        creator_name=txn.creator.full_name if txn.creator else None
    ) for txn in transactions]


@router.post("/transactions", response_model=SafeTransactionResponse)
def create_safe_transaction(
    transaction: SafeTransactionCreate,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Create a new safe transaction"""
    require_permission(current_user, 'safe:edit')

    # Check if user has access to this area
    accessible_area_ids = get_user_accessible_areas(db, current_user)
    if transaction.area_id not in accessible_area_ids:
        raise HTTPException(status_code=403, detail="Access denied to this area")

    # Validate area exists
    area = db.query(Area).filter(Area.id == transaction.area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Create transaction
    new_txn = SafeTransaction(
        transaction_date=transaction.transaction_date,
        area_id=transaction.area_id,
        transaction_type=transaction.transaction_type,
        amount=transaction.amount,
        description=transaction.description,
        notes=transaction.notes,
        reference_type=transaction.reference_type,
        reference_id=transaction.reference_id,
        created_by=current_user.id,
        is_posted=False
    )

    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)

    return SafeTransactionResponse(
        id=new_txn.id,
        transaction_date=new_txn.transaction_date,
        area_id=new_txn.area_id,
        transaction_type=new_txn.transaction_type,
        amount=new_txn.amount,
        description=new_txn.description,
        notes=new_txn.notes,
        reference_type=new_txn.reference_type,
        reference_id=new_txn.reference_id,
        balance_after=new_txn.balance_after,
        journal_entry_id=new_txn.journal_entry_id,
        is_posted=new_txn.is_posted,
        created_by=new_txn.created_by,
        created_at=new_txn.created_at,
        approved_by=new_txn.approved_by,
        approved_at=new_txn.approved_at,
        posted_by=new_txn.posted_by,
        posted_at=new_txn.posted_at,
        area_name=area.name,
        creator_name=current_user.full_name
    )


@router.get("/balance/{area_id}", response_model=SafeBalanceResponse)
def get_safe_balance(
    area_id: int,
    as_of_date: Optional[date] = Query(None, description="Balance as of specific date"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Get current safe balance for a specific area"""
    require_permission(current_user, 'safe:view')

    area = db.query(Area).filter(Area.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    current_balance = calculate_safe_balance(db, area_id, as_of_date)

    # Get last transaction
    last_txn_query = db.query(SafeTransaction).filter(
        SafeTransaction.area_id == area_id,
        SafeTransaction.is_posted == True
    )
    if as_of_date:
        last_txn_query = last_txn_query.filter(SafeTransaction.transaction_date <= as_of_date)

    last_txn = last_txn_query.order_by(desc(SafeTransaction.transaction_date)).first()

    # Count unposted
    unposted = db.query(func.count(SafeTransaction.id)).filter(
        SafeTransaction.area_id == area_id,
        SafeTransaction.is_posted == False
    ).scalar()

    pending_approvals = db.query(func.count(SafeTransaction.id)).filter(
        SafeTransaction.area_id == area_id,
        SafeTransaction.is_posted == False,
        SafeTransaction.approved_at == None
    ).scalar()

    return SafeBalanceResponse(
        area_id=area_id,
        area_name=area.name,
        current_balance=current_balance,
        last_transaction_date=last_txn.transaction_date if last_txn else None,
        unposted_count=unposted or 0,
        pending_approvals=pending_approvals or 0
    )


@router.post("/reconcile", response_model=SafeTransactionResponse)
def reconcile_safe(
    reconciliation: SafeReconciliationRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Perform safe count reconciliation - creates adjustment if needed"""
    require_permission(current_user, 'safe:reconcile')

    area = db.query(Area).filter(Area.id == reconciliation.area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # Calculate expected balance
    expected_balance = calculate_safe_balance(db, reconciliation.area_id, reconciliation.count_date)

    # Calculate variance
    variance = reconciliation.counted_amount - expected_balance

    # If there's a variance, create an adjustment transaction
    if abs(variance) > Decimal('0.01'):
        adjustment_txn = SafeTransaction(
            transaction_date=reconciliation.count_date,
            area_id=reconciliation.area_id,
            transaction_type='adjustment',
            amount=abs(variance),
            description=f"Safe count adjustment - Expected: ${expected_balance:.2f}, Counted: ${reconciliation.counted_amount:.2f}",
            notes=f"Counted by: {reconciliation.counted_by}\n{reconciliation.notes or ''}",
            reference_type='safe_count',
            created_by=current_user.id,
            is_posted=False
        )

        db.add(adjustment_txn)
        db.commit()
        db.refresh(adjustment_txn)

        return SafeTransactionResponse(
            id=adjustment_txn.id,
            transaction_date=adjustment_txn.transaction_date,
            area_id=adjustment_txn.area_id,
            transaction_type=adjustment_txn.transaction_type,
            amount=adjustment_txn.amount,
            description=adjustment_txn.description,
            notes=adjustment_txn.notes,
            reference_type=adjustment_txn.reference_type,
            reference_id=adjustment_txn.reference_id,
            balance_after=adjustment_txn.balance_after,
            journal_entry_id=adjustment_txn.journal_entry_id,
            is_posted=adjustment_txn.is_posted,
            created_by=adjustment_txn.created_by,
            created_at=adjustment_txn.created_at,
            approved_by=adjustment_txn.approved_by,
            approved_at=adjustment_txn.approved_at,
            posted_by=adjustment_txn.posted_by,
            posted_at=adjustment_txn.posted_at,
            area_name=area.name,
            creator_name=current_user.full_name
        )
    else:
        raise HTTPException(status_code=200, detail="Safe balance matches - no adjustment needed")


@router.delete("/transactions/{transaction_id}")
def delete_safe_transaction(
    transaction_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Delete a safe transaction (only if not posted)"""
    require_permission(current_user, 'safe:delete')

    txn = db.query(SafeTransaction).filter(SafeTransaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.is_posted:
        raise HTTPException(status_code=400, detail="Cannot delete posted transaction")

    db.delete(txn)
    db.commit()

    return {"success": True, "message": "Transaction deleted"}


@router.post("/transactions/post", response_model=dict)
def post_safe_transactions(
    post_request: SafePostRequest,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Post safe transactions to GL (creates journal entries)"""
    require_permission(current_user, 'safe:post')

    from accounting.api.journal_entries import generate_entry_number
    from accounting.models.system_setting import SystemSetting

    # Get cash over/short account from settings
    cash_over_short_setting = db.query(SystemSetting).filter(
        SystemSetting.setting_key == 'cash_over_short_account_id'
    ).first()

    posted_count = 0
    errors = []

    for txn_id in post_request.transaction_ids:
        txn = db.query(SafeTransaction).filter(SafeTransaction.id == txn_id).first()

        if not txn:
            errors.append(f"Transaction {txn_id} not found")
            continue

        if txn.is_posted:
            errors.append(f"Transaction {txn_id} already posted")
            continue

        # Get the area and its safe account
        area = db.query(Area).filter(Area.id == txn.area_id).first()
        if not area or not area.safe_account_id:
            errors.append(f"Transaction {txn_id}: No safe GL account configured for area")
            continue

        safe_account = db.query(Account).filter(Account.id == area.safe_account_id).first()
        if not safe_account:
            errors.append(f"Transaction {txn_id}: Safe GL account not found")
            continue

        # Only deposits and adjustments create journal entries
        # Withdrawals are tracking-only (GL already knows from DSS/tip expense)
        if txn.transaction_type == 'withdrawal':
            # Just mark as posted, no JE needed
            txn.is_posted = True
            txn.posted_by = current_user.id
            txn.posted_at = datetime.now()
            posted_count += 1
            continue

        # Generate entry number
        entry_number = generate_entry_number(db, txn.transaction_date)

        # Create journal entry
        je = JournalEntry(
            entry_date=txn.transaction_date,
            entry_number=entry_number,
            description=f"Safe {txn.transaction_type} - {txn.description}",
            reference_type="SAFE_TRANSACTION",
            reference_id=txn.id,
            status=JournalEntryStatus.POSTED,
            created_by=current_user.id,
            posted_at=datetime.now()
        )
        db.add(je)
        db.flush()

        lines = []

        if txn.transaction_type == 'deposit':
            # Deposit: DR Safe, CR Bank (will be linked via bank rec)
            # For now, we'll use a clearing account or require bank account selection
            # This will be enhanced when we integrate with bank reconciliation
            
            # DR: Safe
            lines.append(JournalEntryLine(
                journal_entry_id=je.id,
                line_number=1,
                account_id=safe_account.id,
                area_id=txn.area_id,
                description=txn.description,
                debit_amount=txn.amount,
                credit_amount=Decimal('0.00')
            ))
            
            # CR: Bank/Clearing (placeholder - will be enhanced with bank integration)
            # For now, we need to get the bank account from the transaction
            # This will be improved when we link to bank reconciliation
            # Using 1000 - Cash as placeholder
            cash_clearing = db.query(Account).filter(Account.account_number == '1000').first()
            lines.append(JournalEntryLine(
                journal_entry_id=je.id,
                line_number=2,
                account_id=cash_clearing.id if cash_clearing else safe_account.id,
                area_id=txn.area_id,
                description=txn.description,
                debit_amount=Decimal('0.00'),
                credit_amount=txn.amount
            ))

        elif txn.transaction_type == 'adjustment':
            # Adjustment: Variance to Cash Over/Short
            if not cash_over_short_setting:
                errors.append(f"Transaction {txn_id}: Cash Over/Short account not configured")
                continue
                
            cash_over_short_id = int(cash_over_short_setting.setting_value)
            
            # If positive adjustment (safe has more than expected): CR Safe, DR Cash Over/Short
            # If negative adjustment (safe has less): DR Safe, CR Cash Over/Short
            # We store amount as positive, need to determine direction from context
            
            # For now, assume adjustment amount is what we need to ADD to safe to match count
            lines.append(JournalEntryLine(
                journal_entry_id=je.id,
                line_number=1,
                account_id=safe_account.id,
                area_id=txn.area_id,
                description=txn.description,
                debit_amount=txn.amount,
                credit_amount=Decimal('0.00')
            ))
            
            lines.append(JournalEntryLine(
                journal_entry_id=je.id,
                line_number=2,
                account_id=cash_over_short_id,
                area_id=txn.area_id,
                description=txn.description,
                debit_amount=Decimal('0.00'),
                credit_amount=txn.amount
            ))

        # Add lines to database
        for line in lines:
            db.add(line)

        # Update transaction
        txn.is_posted = True
        txn.journal_entry_id = je.id
        txn.posted_by = current_user.id
        txn.posted_at = datetime.now()
        
        # Calculate and update balance_after from GL
        balance_after = calculate_safe_balance(db, txn.area_id, txn.transaction_date)
        txn.balance_after = balance_after

        posted_count += 1

    db.commit()

    return {
        "success": True,
        "posted_count": posted_count,
        "errors": errors if errors else None
    }
