"""
Bank Accounts API
Endpoints for managing bank accounts, importing statements, and syncing with Plaid
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from decimal import Decimal
import logging

from accounting.db.database import get_db
from accounting.models.bank_account import (
    BankAccount,
    BankTransaction,
    BankStatementImport,
    BankMatchingRule
)
from accounting.models.account import Account
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.schemas.bank_account import (
    BankAccountCreate,
    BankAccountUpdate,
    BankAccountResponse,
    BankTransactionCreate,
    BankTransactionUpdate,
    BankTransactionResponse,
    BankStatementImportResponse,
    BankMatchingRuleCreate,
    BankMatchingRuleUpdate,
    BankMatchingRuleResponse,
    PlaidLinkTokenRequest,
    PlaidLinkTokenResponse,
    PlaidPublicTokenExchange,
    PlaidAccountResponse,
    PlaidExchangeResponse,
    PlaidSyncRequest,
    PlaidSyncResponse,
    TransactionMatchRequest,
    TransactionUnmatchRequest,
    TransactionMatchSuggestion,
    FileUploadResponse
)
from accounting.api.auth import get_current_user
from accounting.models.user import User
from accounting.services.ofx_parser import OFXParserService
from accounting.services.csv_parser import CSVParserService
from accounting.services.plaid_service import get_plaid_service
from accounting.services.transaction_matcher import TransactionMatcher

logger = logging.getLogger(__name__)
router = APIRouter()


def _generate_entry_number(db: Session, entry_date: date, prefix: str = "JE-OB") -> str:
    """Generate sequential entry number for opening balance: PREFIX-YYYYMMDD-NNN"""
    date_str = entry_date.strftime('%Y%m%d')
    entry_prefix = f"{prefix}-{date_str}-"

    # Find the highest number for this date/prefix
    last_entry = db.query(JournalEntry).filter(
        JournalEntry.entry_number.like(f"{entry_prefix}%")
    ).order_by(JournalEntry.entry_number.desc()).first()

    if last_entry:
        last_num = int(last_entry.entry_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1

    return f"{entry_prefix}{new_num:03d}"


def create_opening_balance_journal_entry(
    db: Session,
    bank_account: BankAccount,
    opening_balance: Decimal,
    user_id: int,
    balance_date: Optional[date] = None
) -> Optional[JournalEntry]:
    """
    Create a journal entry for the bank account opening balance.

    Debit: Bank Account GL (asset increases)
    Credit: Opening Balance Equity (3350)

    For negative opening balances (overdraft), entries are reversed.

    Args:
        balance_date: The date for the journal entry (defaults to today if not provided)
    """
    if not opening_balance or opening_balance == 0:
        return None

    if not bank_account.gl_account_id:
        logger.warning(f"Bank account {bank_account.id} has no GL account assigned, skipping opening balance JE")
        return None

    # Get the bank account's GL account
    bank_gl_account = db.query(Account).filter(Account.id == bank_account.gl_account_id).first()
    if not bank_gl_account:
        logger.warning(f"GL account {bank_account.gl_account_id} not found")
        return None

    # Get Opening Balance Equity account (3350) for the offset
    # This can be closed to Retained Earnings later after reconciliation
    opening_bal_equity = db.query(Account).filter(Account.account_number == '3350').first()
    if not opening_bal_equity:
        logger.warning("Opening Balance Equity account (3350) not found, cannot create opening balance JE")
        return None

    # Use provided date or default to today
    entry_date_val = balance_date if balance_date else date.today()
    entry_number = _generate_entry_number(db, entry_date_val, "JE-OB")

    # Create journal entry
    je = JournalEntry(
        entry_date=entry_date_val,
        entry_number=entry_number,
        description=f"Opening balance for {bank_account.account_name}",
        status='POSTED',
        created_by=user_id
    )
    db.add(je)
    db.flush()

    abs_amount = abs(opening_balance)

    if opening_balance > 0:
        # Positive balance: Debit Bank, Credit Opening Balance Equity
        debit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=1,
            account_id=bank_gl_account.id,
            area_id=bank_account.area_id,
            description=f"Opening balance - {bank_account.account_name}",
            debit_amount=abs_amount,
            credit_amount=Decimal('0')
        )
        db.add(debit_line)

        credit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=2,
            account_id=opening_bal_equity.id,
            area_id=bank_account.area_id,
            description=f"Opening balance - {bank_account.account_name}",
            debit_amount=Decimal('0'),
            credit_amount=abs_amount
        )
        db.add(credit_line)
    else:
        # Negative balance (overdraft): Debit Opening Balance Equity, Credit Bank
        debit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=1,
            account_id=opening_bal_equity.id,
            area_id=bank_account.area_id,
            description=f"Opening balance (overdraft) - {bank_account.account_name}",
            debit_amount=abs_amount,
            credit_amount=Decimal('0')
        )
        db.add(debit_line)

        credit_line = JournalEntryLine(
            journal_entry_id=je.id,
            line_number=2,
            account_id=bank_gl_account.id,
            area_id=bank_account.area_id,
            description=f"Opening balance (overdraft) - {bank_account.account_name}",
            debit_amount=Decimal('0'),
            credit_amount=abs_amount
        )
        db.add(credit_line)

    logger.info(f"Created opening balance journal entry {je.id} for bank account {bank_account.id}: ${opening_balance}")
    return je


# ============================================================================
# Bank Account Management
# ============================================================================

@router.get("/", response_model=List[BankAccountResponse])
def list_bank_accounts(
    area_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of bank accounts"""
    query = db.query(BankAccount)

    if area_id:
        query = query.filter(BankAccount.area_id == area_id)

    if status:
        query = query.filter(BankAccount.status == status)

    accounts = query.order_by(BankAccount.account_name).all()

    # Add calculated fields
    for account in accounts:
        # Count unreconciled transactions
        account.unreconciled_count = db.query(BankTransaction).filter(
            BankTransaction.bank_account_id == account.id,
            BankTransaction.status == "unreconciled"
        ).count()

        # Get last reconciliation date
        from accounting.models.bank_account import BankReconciliation
        last_recon = db.query(BankReconciliation).filter(
            BankReconciliation.bank_account_id == account.id
        ).order_by(BankReconciliation.reconciliation_date.desc()).first()

        account.last_reconciliation_date = last_recon.reconciliation_date if last_recon else None

    return accounts


@router.post("/", response_model=BankAccountResponse)
def create_bank_account(
    account: BankAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new bank account"""
    db_account = BankAccount(
        **account.dict(),
        created_by=current_user.id
    )
    db.add(db_account)
    db.flush()

    # Create opening balance journal entry if opening_balance is set
    if account.opening_balance and account.opening_balance != 0:
        create_opening_balance_journal_entry(
            db=db,
            bank_account=db_account,
            opening_balance=account.opening_balance,
            user_id=current_user.id,
            balance_date=account.opening_balance_date
        )
        # Also set the current balance to the opening balance
        db_account.current_balance = account.opening_balance

    db.commit()
    db.refresh(db_account)

    db_account.unreconciled_count = 0
    db_account.last_reconciliation_date = None

    return db_account


@router.get("/{account_id}", response_model=BankAccountResponse)
def get_bank_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get bank account by ID"""
    account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Add calculated fields
    account.unreconciled_count = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == account.id,
        BankTransaction.status == "unreconciled"
    ).count()

    from accounting.models.bank_account import BankReconciliation
    last_recon = db.query(BankReconciliation).filter(
        BankReconciliation.bank_account_id == account.id
    ).order_by(BankReconciliation.reconciliation_date.desc()).first()

    account.last_reconciliation_date = last_recon.reconciliation_date if last_recon else None

    return account


@router.put("/{account_id}", response_model=BankAccountResponse)
def update_bank_account(
    account_id: int,
    account_update: BankAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update bank account"""
    db_account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Check if opening_balance is being changed
    update_data = account_update.dict(exclude_unset=True)
    old_opening_balance = db_account.opening_balance or Decimal('0')
    new_opening_balance = update_data.get('opening_balance')
    new_balance_date = update_data.get('opening_balance_date')

    # Update fields
    for field, value in update_data.items():
        setattr(db_account, field, value)

    # Create journal entry if opening_balance changed from zero/null to a value
    if new_opening_balance is not None and new_opening_balance != 0:
        if old_opening_balance == 0:
            # First time setting opening balance - create JE
            create_opening_balance_journal_entry(
                db=db,
                bank_account=db_account,
                opening_balance=new_opening_balance,
                user_id=current_user.id,
                balance_date=new_balance_date or db_account.opening_balance_date
            )
            # Also update current balance if not set
            if not db_account.current_balance:
                db_account.current_balance = new_opening_balance
            logger.info(f"Created opening balance JE for existing bank account {account_id}")
        elif new_opening_balance != old_opening_balance:
            # Opening balance changed - create adjustment JE for the difference
            difference = new_opening_balance - old_opening_balance
            create_opening_balance_journal_entry(
                db=db,
                bank_account=db_account,
                opening_balance=difference,
                user_id=current_user.id,
                balance_date=new_balance_date or db_account.opening_balance_date
            )
            logger.info(f"Created adjustment JE for bank account {account_id} opening balance change: {difference}")

    db.commit()
    db.refresh(db_account)

    db_account.unreconciled_count = 0
    db_account.last_reconciliation_date = None

    return db_account


@router.delete("/{account_id}")
def delete_bank_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete bank account (soft delete - set status to inactive)"""
    db_account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    db_account.status = "inactive"
    db.commit()

    return {"message": "Bank account deleted successfully"}


# ============================================================================
# Bank Transactions
# ============================================================================

@router.get("/{account_id}/transactions", response_model=List[BankTransactionResponse])
def list_transactions(
    account_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get transactions for a bank account"""
    query = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == account_id
    )

    if start_date:
        query = query.filter(BankTransaction.transaction_date >= start_date)

    if end_date:
        query = query.filter(BankTransaction.transaction_date <= end_date)

    if status:
        query = query.filter(BankTransaction.status == status)

    transactions = query.order_by(
        BankTransaction.transaction_date.desc()
    ).offset(offset).limit(limit).all()

    # Get match suggestions for unmatched transactions
    matcher = TransactionMatcher(db)
    for txn in transactions:
        if not txn.matched_journal_line_id:
            txn.suggested_matches = matcher.find_matches(txn, limit=3)
        else:
            txn.suggested_matches = []

    return transactions


@router.post("/{account_id}/transactions", response_model=BankTransactionResponse)
def create_transaction(
    account_id: int,
    transaction: BankTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new bank transaction (manual entry)"""
    db_transaction = BankTransaction(
        bank_account_id=account_id,
        **transaction.dict(exclude={"bank_account_id"})
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)

    db_transaction.suggested_matches = []

    return db_transaction


@router.put("/transactions/{transaction_id}", response_model=BankTransactionResponse)
def update_transaction(
    transaction_id: int,
    transaction_update: BankTransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update bank transaction"""
    db_transaction = db.query(BankTransaction).filter(
        BankTransaction.id == transaction_id
    ).first()

    if not db_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = transaction_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_transaction, field, value)

    db.commit()
    db.refresh(db_transaction)

    db_transaction.suggested_matches = []

    return db_transaction


@router.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete bank transaction"""
    db_transaction = db.query(BankTransaction).filter(
        BankTransaction.id == transaction_id
    ).first()

    if not db_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Don't allow deleting reconciled transactions
    if db_transaction.status == "reconciled":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete reconciled transaction"
        )

    db.delete(db_transaction)
    db.commit()

    return {"message": "Transaction deleted successfully"}


# ============================================================================
# File Import (CSV, OFX, QFX)
# ============================================================================

@router.post("/{account_id}/import", response_model=FileUploadResponse)
async def import_statement(
    account_id: int,
    file: UploadFile = File(...),
    file_format: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Import bank statement from file
    Supports CSV, OFX, QFX formats
    """
    # Verify bank account exists
    bank_account = db.query(BankAccount).filter(BankAccount.id == account_id).first()
    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Read file content
    file_content = await file.read()

    # Determine file format if not provided
    if not file_format:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            file_format = 'csv'
        elif filename.endswith('.ofx') or filename.endswith('.qfx'):
            file_format = 'ofx'
        else:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file format. Please specify file_format parameter."
            )

    # Parse file
    if file_format == 'ofx' or file_format == 'qfx':
        result = OFXParserService.parse_file(file_content)
    elif file_format == 'csv':
        result = CSVParserService.parse_file(file_content)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {file_format}")

    if not result["success"]:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {', '.join(result['errors'])}")

    # Create import record
    db_import = BankStatementImport(
        bank_account_id=account_id,
        file_name=file.filename,
        file_format=file_format,
        import_method="manual",
        statement_date=result.get("account_info", {}).get("statement_end_date"),
        beginning_balance=result.get("account_info", {}).get("beginning_balance"),
        ending_balance=result.get("account_info", {}).get("ending_balance"),
        transaction_count=result["transaction_count"],
        imported_by=current_user.id
    )
    db.add(db_import)
    db.flush()

    # Import transactions
    transactions_imported = 0
    duplicates_skipped = 0
    errors = []
    warnings = []

    for txn_data in result["transactions"]:
        # Check for duplicates (same account, date, amount, description)
        existing = db.query(BankTransaction).filter(
            BankTransaction.bank_account_id == account_id,
            BankTransaction.transaction_date == txn_data["transaction_date"],
            BankTransaction.amount == txn_data["amount"],
            BankTransaction.description == txn_data["description"]
        ).first()

        if existing:
            duplicates_skipped += 1
            continue

        # Create transaction
        try:
            db_transaction = BankTransaction(
                bank_account_id=account_id,
                import_id=db_import.id,
                **txn_data
            )
            db.add(db_transaction)
            transactions_imported += 1

        except Exception as e:
            errors.append(f"Error importing transaction: {str(e)}")

    db.commit()

    return FileUploadResponse(
        success=True,
        import_id=db_import.id,
        transactions_imported=transactions_imported,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
        warnings=warnings
    )


@router.get("/{account_id}/imports", response_model=List[BankStatementImportResponse])
def list_imports(
    account_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of statement imports for a bank account"""
    imports = db.query(BankStatementImport).filter(
        BankStatementImport.bank_account_id == account_id
    ).order_by(BankStatementImport.import_date.desc()).limit(limit).all()

    return imports


# ============================================================================
# Transaction Matching
# ============================================================================

@router.get("/transactions/{transaction_id}/matches", response_model=List[TransactionMatchSuggestion])
def get_match_suggestions(
    transaction_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get match suggestions for a bank transaction"""
    transaction = db.query(BankTransaction).filter(
        BankTransaction.id == transaction_id
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    matcher = TransactionMatcher(db)
    matches = matcher.find_matches(transaction, limit=limit)

    return matches


@router.post("/transactions/match", response_model=dict)
def match_transaction(
    match_request: TransactionMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Match a bank transaction to a journal entry line"""
    matcher = TransactionMatcher(db)
    success = matcher.match_transaction(
        match_request.bank_transaction_id,
        match_request.journal_line_id,
        match_request.match_type
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to match transaction")

    return {"message": "Transaction matched successfully"}


@router.post("/transactions/unmatch", response_model=dict)
def unmatch_transaction(
    unmatch_request: TransactionUnmatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove match from a bank transaction"""
    matcher = TransactionMatcher(db)
    success = matcher.unmatch_transaction(unmatch_request.bank_transaction_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to unmatch transaction")

    return {"message": "Transaction unmatched successfully"}


@router.post("/{account_id}/auto-match", response_model=dict)
def auto_match_transactions(
    account_id: int,
    confidence_threshold: Decimal = Decimal("95.0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Automatically match high-confidence transactions"""
    matcher = TransactionMatcher(db)
    result = matcher.auto_match_transactions(account_id, confidence_threshold)

    return result


# ============================================================================
# Matching Rules
# ============================================================================

@router.get("/{account_id}/rules", response_model=List[BankMatchingRuleResponse])
def list_matching_rules(
    account_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get matching rules for a bank account"""
    query = db.query(BankMatchingRule).filter(
        BankMatchingRule.bank_account_id == account_id
    )

    if active_only:
        query = query.filter(BankMatchingRule.active == True)

    rules = query.order_by(BankMatchingRule.priority.desc()).all()

    return rules


@router.post("/{account_id}/rules", response_model=BankMatchingRuleResponse)
def create_matching_rule(
    account_id: int,
    rule: BankMatchingRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new matching rule"""
    db_rule = BankMatchingRule(
        bank_account_id=account_id,
        **rule.dict(exclude={"bank_account_id"}),
        created_by=current_user.id
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)

    return db_rule


@router.put("/rules/{rule_id}", response_model=BankMatchingRuleResponse)
def update_matching_rule(
    rule_id: int,
    rule_update: BankMatchingRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update matching rule"""
    db_rule = db.query(BankMatchingRule).filter(BankMatchingRule.id == rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Matching rule not found")

    update_data = rule_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_rule, field, value)

    db.commit()
    db.refresh(db_rule)

    return db_rule


@router.delete("/rules/{rule_id}")
def delete_matching_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete matching rule"""
    db_rule = db.query(BankMatchingRule).filter(BankMatchingRule.id == rule_id).first()
    if not db_rule:
        raise HTTPException(status_code=404, detail="Matching rule not found")

    db.delete(db_rule)
    db.commit()

    return {"message": "Matching rule deleted successfully"}


# ============================================================================
# Plaid Integration
# ============================================================================

@router.post("/plaid/link-token", response_model=PlaidLinkTokenResponse)
def create_plaid_link_token(
    request: PlaidLinkTokenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create Plaid link token for connecting bank account"""
    plaid = get_plaid_service()

    if not plaid.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Plaid service not configured. Set PLAID_CLIENT_ID and PLAID_SECRET environment variables."
        )

    result = plaid.create_link_token(current_user.id, current_user.full_name or current_user.username)

    if not result:
        raise HTTPException(status_code=500, detail="Failed to create link token")

    return PlaidLinkTokenResponse(**result)


@router.post("/plaid/exchange-token", response_model=PlaidExchangeResponse)
def exchange_plaid_token(
    exchange: PlaidPublicTokenExchange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exchange public token and get account information with credentials"""
    plaid = get_plaid_service()

    if not plaid.is_enabled():
        raise HTTPException(status_code=503, detail="Plaid service not configured")

    # Exchange token
    token_result = plaid.exchange_public_token(exchange.public_token)

    if not token_result:
        raise HTTPException(status_code=400, detail="Failed to exchange token")

    # Get accounts
    accounts = plaid.get_accounts(token_result["access_token"])

    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts found")

    # If bank_account_id provided, link the Plaid account
    if exchange.bank_account_id:
        bank_account = db.query(BankAccount).filter(
            BankAccount.id == exchange.bank_account_id
        ).first()

        if bank_account:
            # Link first account (or specified account)
            bank_account.plaid_access_token = token_result["access_token"]
            bank_account.plaid_item_id = token_result["item_id"]
            bank_account.plaid_account_id = accounts[0]["account_id"]
            bank_account.sync_method = "plaid"
            bank_account.current_balance = accounts[0]["current_balance"]

            db.commit()

    # Return full response including credentials for client-side storage
    return PlaidExchangeResponse(
        access_token=token_result["access_token"],
        item_id=token_result["item_id"],
        accounts=[PlaidAccountResponse(**acc) for acc in accounts]
    )


@router.post("/{account_id}/plaid/sync", response_model=PlaidSyncResponse)
def sync_plaid_transactions(
    account_id: int,
    sync_request: PlaidSyncRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sync transactions from Plaid"""
    bank_account = db.query(BankAccount).filter(BankAccount.id == account_id).first()

    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if not bank_account.plaid_access_token or not bank_account.plaid_account_id:
        raise HTTPException(status_code=400, detail="Bank account not linked to Plaid")

    plaid = get_plaid_service()

    if not plaid.is_enabled():
        raise HTTPException(status_code=503, detail="Plaid service not configured")

    # Sync transactions
    result = plaid.sync_transactions(
        bank_account.plaid_access_token,
        bank_account.plaid_account_id,
        cursor=None  # TODO: Store cursor for incremental syncs
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Sync failed"))

    # Import transactions
    transactions_added = 0

    for txn_data in result["transactions"]:
        # Check for duplicates
        existing = db.query(BankTransaction).filter(
            BankTransaction.plaid_transaction_id == txn_data["plaid_transaction_id"]
        ).first()

        if not existing:
            db_transaction = BankTransaction(
                bank_account_id=account_id,
                **txn_data
            )
            db.add(db_transaction)
            transactions_added += 1

    # Update last sync date
    from datetime import datetime
    bank_account.last_sync_date = datetime.now()

    db.commit()

    return PlaidSyncResponse(
        success=True,
        transactions_added=transactions_added,
        transactions_updated=0,
        transactions_removed=0,
        last_sync_date=bank_account.last_sync_date
    )


# ============================================================================
# Plaid Webhooks
# ============================================================================

@router.post("/plaid/webhook")
async def plaid_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Plaid webhooks for transaction updates and other events.

    Webhook types handled:
    - TRANSACTIONS: Transaction updates (new, modified, removed)
    - ITEM: Item status changes (error, pending expiration)
    - AUTH: Auth data changes
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        body = await request.json()
        webhook_type = body.get("webhook_type")
        webhook_code = body.get("webhook_code")
        item_id = body.get("item_id")

        logger.info(f"Received Plaid webhook: type={webhook_type}, code={webhook_code}, item_id={item_id}")

        # Handle different webhook types
        if webhook_type == "TRANSACTIONS":
            # Transaction webhooks
            if webhook_code == "SYNC_UPDATES_AVAILABLE":
                # New transactions available - find the bank account and trigger sync
                bank_account = db.query(BankAccount).filter(
                    BankAccount.plaid_item_id == item_id
                ).first()

                if bank_account:
                    logger.info(f"Transactions available for bank account {bank_account.id}, auto-sync can be triggered")
                    # Note: Auto-sync could be triggered here if desired
                    # For now, just log it - user can manually sync

            elif webhook_code == "INITIAL_UPDATE":
                logger.info(f"Initial transaction data available for item {item_id}")

            elif webhook_code == "HISTORICAL_UPDATE":
                logger.info(f"Historical transaction data available for item {item_id}")

        elif webhook_type == "ITEM":
            # Item webhooks
            if webhook_code == "ERROR":
                error = body.get("error", {})
                logger.error(f"Plaid item error for {item_id}: {error}")

                # Update bank account status
                bank_account = db.query(BankAccount).filter(
                    BankAccount.plaid_item_id == item_id
                ).first()

                if bank_account:
                    bank_account.notes = f"Plaid Error: {error.get('error_message', 'Unknown error')}. {bank_account.notes or ''}"
                    db.commit()

            elif webhook_code == "PENDING_EXPIRATION":
                logger.warning(f"Plaid access token pending expiration for item {item_id}")

            elif webhook_code == "USER_PERMISSION_REVOKED":
                logger.warning(f"User revoked permission for item {item_id}")

                # Mark bank account as disconnected
                bank_account = db.query(BankAccount).filter(
                    BankAccount.plaid_item_id == item_id
                ).first()

                if bank_account:
                    bank_account.sync_method = "manual"
                    bank_account.plaid_access_token = None
                    bank_account.notes = f"Plaid connection revoked by user. {bank_account.notes or ''}"
                    db.commit()

        elif webhook_type == "AUTH":
            logger.info(f"Auth webhook received for item {item_id}: {webhook_code}")

        # Always return 200 to acknowledge receipt
        return {"status": "received", "webhook_type": webhook_type, "webhook_code": webhook_code}

    except Exception as e:
        logger.error(f"Error processing Plaid webhook: {str(e)}")
        # Still return 200 to prevent Plaid from retrying
        return {"status": "error", "message": str(e)}
