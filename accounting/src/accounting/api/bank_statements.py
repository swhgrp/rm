"""
Bank statement and matching API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import List, Optional
from datetime import date

from accounting.db.database import get_db
from accounting.models.bank_account import (
    BankStatement,
    BankTransaction,
    BankAccount,
    BankTransactionMatch,
    BankCompositeMatch,
    BankMatchingRuleV2
)
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.models.account import Account
from accounting.models.vendor import Vendor
from accounting.models.vendor_bill import VendorBill
from accounting.schemas.bank_statement import (
    BankStatement as BankStatementSchema,
    BankStatementCreate,
    BankStatementUpdate,
    StatementSummary,
    MatchSuggestionsResponse,
    MatchSuggestionResponse,
    JournalEntryLineInfo,
    ConfirmMatchRequest,
    ConfirmMatchResponse,
    BankMatchingRule as BankMatchingRuleSchema,
    BankMatchingRuleCreate,
    BankMatchingRuleUpdate,
    CreateRuleFromMatchRequest,
    VendorRecognitionResponse,
    VendorInfo,
    OpenBillsResponse,
    OpenBillInfo,
    MatchBillsRequest,
    MatchBillsResponse,
    GLAssignmentRequest,
    GLAssignmentResponse
)
from accounting.services.bank_matching import BankMatchingService
from accounting.utils.vendor_recognition import VendorRecognitionService

router = APIRouter()


# ==================== Bank Statement CRUD ====================

@router.get("/", response_model=List[StatementSummary])
def list_bank_statements(
    bank_account_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all bank statements with summary information"""
    query = db.query(BankStatement).join(BankAccount)

    if bank_account_id:
        query = query.filter(BankStatement.bank_account_id == bank_account_id)

    if status:
        query = query.filter(BankStatement.status == status)

    statements = query.order_by(desc(BankStatement.statement_period_end)).offset(skip).limit(limit).all()

    # Build summary for each statement
    summaries = []
    for stmt in statements:
        # Count transactions
        total_txns = db.query(func.count(BankTransaction.id)).filter(
            BankTransaction.statement_id == stmt.id
        ).scalar()

        # Count matched transactions
        matched_txns = db.query(func.count(BankTransaction.id)).filter(
            and_(
                BankTransaction.statement_id == stmt.id,
                BankTransaction.status == 'reconciled'
            )
        ).scalar()

        summaries.append(StatementSummary(
            id=stmt.id,
            bank_account_id=stmt.bank_account_id,
            bank_account_name=stmt.bank_account.account_name,
            statement_period_start=stmt.statement_period_start,
            statement_period_end=stmt.statement_period_end,
            opening_balance=stmt.opening_balance,
            closing_balance=stmt.closing_balance,
            status=stmt.status,
            transaction_count=total_txns or 0,
            matched_count=matched_txns or 0,
            unmatched_count=(total_txns or 0) - (matched_txns or 0),
            difference=stmt.difference
        ))

    return summaries


@router.post("/", response_model=BankStatementSchema)
def create_bank_statement(
    statement: BankStatementCreate,
    db: Session = Depends(get_db)
):
    """Create a new bank statement"""
    # Verify bank account exists
    bank_account = db.query(BankAccount).filter(BankAccount.id == statement.bank_account_id).first()
    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    # Create statement
    db_statement = BankStatement(
        **statement.model_dump(),
        status='draft'
    )
    db.add(db_statement)
    db.commit()
    db.refresh(db_statement)

    return db_statement


@router.get("/{statement_id}", response_model=BankStatementSchema)
def get_bank_statement(statement_id: int, db: Session = Depends(get_db)):
    """Get a specific bank statement"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    return statement


@router.put("/{statement_id}", response_model=BankStatementSchema)
def update_bank_statement(
    statement_id: int,
    statement_update: BankStatementUpdate,
    db: Session = Depends(get_db)
):
    """Update a bank statement"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    # Can't update locked statements
    if statement.status == 'locked':
        raise HTTPException(status_code=400, detail="Cannot update locked statement")

    # Update fields
    for field, value in statement_update.model_dump(exclude_unset=True).items():
        setattr(statement, field, value)

    db.commit()
    db.refresh(statement)
    return statement


@router.delete("/{statement_id}")
def delete_bank_statement(statement_id: int, db: Session = Depends(get_db)):
    """Delete a bank statement (only if draft)"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if statement.status != 'draft':
        raise HTTPException(status_code=400, detail="Can only delete draft statements")

    db.delete(statement)
    db.commit()
    return {"message": "Statement deleted"}


# ==================== Statement Actions ====================

@router.post("/{statement_id}/start-reconciliation")
def start_reconciliation(statement_id: int, db: Session = Depends(get_db)):
    """Mark statement as in_progress"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if statement.status not in ['draft', 'in_progress']:
        raise HTTPException(status_code=400, detail=f"Cannot start reconciliation from status: {statement.status}")

    statement.status = 'in_progress'
    db.commit()
    return {"message": "Reconciliation started", "status": "in_progress"}


@router.post("/{statement_id}/finalize")
def finalize_reconciliation(
    statement_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Finalize and mark statement as reconciled"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if statement.status != 'in_progress':
        raise HTTPException(status_code=400, detail="Statement must be in_progress to finalize")

    # Calculate GL balance and difference
    # TODO: Implement GL balance calculation
    statement.gl_balance = statement.closing_balance  # Placeholder
    statement.difference = statement.closing_balance - (statement.gl_balance or 0)

    # Check if balanced
    if abs(statement.difference or 0) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Statement is not balanced. Difference: ${statement.difference:.2f}"
        )

    # Mark as reconciled
    statement.status = 'reconciled'
    statement.reconciled_by = user_id
    statement.reconciled_at = func.current_timestamp()

    # TODO: Create snapshot

    db.commit()
    return {"message": "Statement reconciled", "status": "reconciled"}


@router.post("/{statement_id}/lock")
def lock_statement(
    statement_id: int,
    user_id: int = Query(...),
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lock a reconciled statement"""
    statement = db.query(BankStatement).filter(BankStatement.id == statement_id).first()
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")

    if statement.status != 'reconciled':
        raise HTTPException(status_code=400, detail="Can only lock reconciled statements")

    statement.status = 'locked'
    statement.locked_by = user_id
    statement.locked_at = func.current_timestamp()
    statement.locked_reason = reason

    # TODO: Create snapshot

    db.commit()
    return {"message": "Statement locked", "status": "locked"}


# ==================== Matching Endpoints ====================

@router.get("/transactions/{transaction_id}/suggest-matches", response_model=MatchSuggestionsResponse)
def suggest_matches_for_transaction(
    transaction_id: int,
    date_window_days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db)
):
    """Get match suggestions for a bank transaction"""
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Initialize matching service
    matching_service = BankMatchingService(db)

    # Get suggestions
    suggestions = matching_service.suggest_matches(
        transaction,
        date_window_days=date_window_days
    )

    # Convert to response format
    suggestion_responses = []
    for suggestion in suggestions:
        # Build JE line info
        je_line_infos = []
        for je_line in suggestion.journal_entry_lines:
            je_line_infos.append(JournalEntryLineInfo(
                id=je_line.id,
                journal_entry_id=je_line.journal_entry_id,
                account_id=je_line.account_id,
                account_code=je_line.account.code,
                account_name=je_line.account.name,
                debit_amount=je_line.debit_amount,
                credit_amount=je_line.credit_amount,
                description=je_line.description,
                entry_date=je_line.journal_entry.entry_date
            ))

        suggestion_responses.append(MatchSuggestionResponse(
            match_type=suggestion.match_type,
            confidence_score=suggestion.confidence_score,
            match_reason=suggestion.match_reason,
            journal_entry_lines=je_line_infos,
            amount_difference=suggestion.amount_difference,
            date_difference=suggestion.date_difference,
            suggested_fee_account_id=suggestion.suggested_fee_account_id,
            suggested_fee_amount=suggestion.suggested_fee_amount,
            composite_group_id=suggestion.composite_group_id
        ))

    return MatchSuggestionsResponse(
        bank_transaction_id=transaction.id,
        bank_amount=transaction.amount,
        bank_date=transaction.transaction_date,
        bank_description=transaction.description,
        suggestions=suggestion_responses,
        total_suggestions=len(suggestion_responses)
    )


@router.post("/transactions/{transaction_id}/confirm-match", response_model=ConfirmMatchResponse)
def confirm_transaction_match(
    transaction_id: int,
    confirm_request: ConfirmMatchRequest,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Confirm a match suggestion"""
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Get suggestions again
    matching_service = BankMatchingService(db)
    suggestions = matching_service.suggest_matches(transaction)

    if confirm_request.suggestion_index >= len(suggestions):
        raise HTTPException(status_code=400, detail="Invalid suggestion index")

    suggestion = suggestions[confirm_request.suggestion_index]

    # Confirm the match
    match = matching_service.confirm_match(transaction, suggestion, user_id)

    # TODO: Create clearing journal entry if needed
    # TODO: Create fee adjustment journal entry if requested

    return ConfirmMatchResponse(
        match_id=match.id,
        bank_transaction_id=transaction.id,
        match_type=match.match_type,
        status=match.status,
        clearing_journal_entry_id=match.clearing_journal_entry_id,
        adjustment_journal_entry_id=match.adjustment_journal_entry_id,
        message="Match confirmed successfully"
    )


# ==================== Matching Rules ====================

@router.get("/matching-rules/", response_model=List[BankMatchingRuleSchema])
def list_matching_rules(
    bank_account_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List matching rules"""
    query = db.query(BankMatchingRuleV2)

    if bank_account_id:
        query = query.filter(
            (BankMatchingRuleV2.bank_account_id == bank_account_id) |
            (BankMatchingRuleV2.bank_account_id.is_(None))
        )

    if active_only:
        query = query.filter(BankMatchingRuleV2.active == True)

    rules = query.order_by(desc(BankMatchingRuleV2.priority)).all()
    return rules


@router.post("/matching-rules/", response_model=BankMatchingRuleSchema)
def create_matching_rule(
    rule: BankMatchingRuleCreate,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Create a new matching rule"""
    db_rule = BankMatchingRuleV2(
        **rule.model_dump(),
        created_by=user_id
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


@router.put("/matching-rules/{rule_id}", response_model=BankMatchingRuleSchema)
def update_matching_rule(
    rule_id: int,
    rule_update: BankMatchingRuleUpdate,
    db: Session = Depends(get_db)
):
    """Update a matching rule"""
    rule = db.query(BankMatchingRuleV2).filter(BankMatchingRuleV2.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in rule_update.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/matching-rules/{rule_id}")
def delete_matching_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete a matching rule"""
    rule = db.query(BankMatchingRuleV2).filter(BankMatchingRuleV2.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}


@router.post("/matching-rules/from-match", response_model=BankMatchingRuleSchema)
def create_rule_from_match(
    request: CreateRuleFromMatchRequest,
    transaction_id: int = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Create a matching rule from a confirmed match"""
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Build conditions from transaction
    conditions = {}
    if transaction.description:
        # Extract key part of description (remove numbers, dates, etc.)
        desc_parts = transaction.description.upper().split()
        if desc_parts:
            conditions["description_contains"] = desc_parts[0]  # First word usually vendor name

    # Get the matched account
    target_account_id = None
    if transaction.matched_journal_line_id:
        je_line = db.query(JournalEntryLine).filter(
            JournalEntryLine.id == transaction.matched_journal_line_id
        ).first()
        if je_line:
            target_account_id = je_line.account_id

    # Create rule
    db_rule = BankMatchingRuleV2(
        bank_account_id=None if request.apply_to_all_accounts else transaction.bank_account_id,
        rule_name=request.rule_name,
        rule_type=request.rule_type,
        priority=request.priority,
        conditions=conditions,
        action_type="suggest_gl_account",
        target_account_id=target_account_id,
        requires_confirmation=True,
        active=True,
        notes=request.notes,
        created_by=user_id
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)

    return db_rule


# ==================== Vendor Recognition Endpoints ====================

@router.get("/transactions/{transaction_id}/recognize-vendor", response_model=VendorRecognitionResponse)
def recognize_vendor_from_transaction(
    transaction_id: int,
    db: Session = Depends(get_db)
):
    """
    Extract vendor from transaction description and find matching vendor

    This endpoint:
    1. Extracts potential vendor name from bank transaction description
    2. Matches against vendors in database
    3. Counts open bills for matched vendor
    4. Checks if any open bills exactly match transaction amount

    Example:
        Transaction: "ACH DEBIT GOLD COAST LINEN SERVICE"
        -> Extracts: "GOLD COAST LINEN SERVICE"
        -> Matches vendor ID 15
        -> Returns: 9 open bills, 1 exact match
    """
    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Initialize vendor recognition service
    vendor_service = VendorRecognitionService(db)

    # Extract and match vendor
    extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)

    # Count open bills if vendor found
    open_bills_count = 0
    has_exact_match = False

    if vendor:
        # Count unpaid/partial bills matching vendor name
        # Note: vendor_bills.vendor_id is VARCHAR, not FK to vendors.id
        # It stores vendor_code or vendor_name
        open_bills = db.query(VendorBill).filter(
            (VendorBill.vendor_name == vendor.vendor_name) |
            (VendorBill.vendor_id == vendor.vendor_code) |
            (VendorBill.vendor_name == vendor.vendor_code) |  # Bill uses code as name
            (VendorBill.vendor_id == vendor.vendor_name),     # Bill uses name as ID
            VendorBill.status.in_(['DRAFT', 'APPROVED', 'PARTIALLY_PAID'])
        ).all()

        open_bills_count = len(open_bills)

        # Check for exact amount match
        # Note: Bank transactions are negative for expenses, bills are positive
        transaction_amount_abs = abs(transaction.amount)

        for bill in open_bills:
            bill_amount_due = bill.total_amount - bill.paid_amount
            if abs(bill_amount_due - transaction_amount_abs) < 0.01:  # Within 1 cent
                has_exact_match = True
                break

    # Build response
    vendor_info = None
    if vendor:
        vendor_info = VendorInfo(
            id=vendor.id,
            vendor_name=vendor.vendor_name,
            vendor_code=vendor.vendor_code
        )

    return VendorRecognitionResponse(
        extracted_vendor_name=extracted_name,
        matched_vendor=vendor_info,
        open_bills_count=open_bills_count,
        has_exact_match=has_exact_match,
        confidence=confidence
    )


@router.get("/transactions/{transaction_id}/open-bills", response_model=OpenBillsResponse)
def get_open_bills_for_transaction(
    transaction_id: int,
    date_window_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """
    Get all open bills for vendor with match scoring

    This endpoint:
    1. Recognizes vendor from transaction description
    2. Fetches all unpaid/partial bills for that vendor
    3. Scores each bill by amount match and date proximity
    4. Highlights exact matches (100% confidence)

    Used for displaying the "Open Bills" modal in the UI

    Example Response:
    {
        "vendor": {"id": 15, "name": "Gold Coast Linen Service"},
        "open_bills": [
            {
                "bill_number": "BILL/2025/10/0003",
                "amount_due": -71.56,
                "match_confidence": 100.0,
                "is_exact_match": true,
                "amount_difference": 0.00
            },
            ...
        ],
        "total_bills": 9,
        "exact_matches": 1
    }
    """
    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Recognize vendor
    vendor_service = VendorRecognitionService(db)
    extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)

    if not vendor:
        # No vendor matched - return empty response
        return OpenBillsResponse(
            bank_transaction_id=transaction.id,
            bank_amount=transaction.amount,
            bank_date=transaction.transaction_date,
            bank_description=transaction.description,
            vendor=None,
            open_bills=[],
            total_bills=0,
            exact_matches=0
        )

    # Get open bills for vendor
    from datetime import timedelta
    date_min = transaction.transaction_date - timedelta(days=date_window_days)
    date_max = transaction.transaction_date + timedelta(days=date_window_days)

    open_bills_query = db.query(VendorBill).filter(
        (VendorBill.vendor_name == vendor.vendor_name) |
        (VendorBill.vendor_id == vendor.vendor_code) |
        (VendorBill.vendor_name == vendor.vendor_code) |
        (VendorBill.vendor_id == vendor.vendor_name),
        VendorBill.status.in_(['DRAFT', 'APPROVED', 'PARTIALLY_PAID']),
        VendorBill.bill_date >= date_min,
        VendorBill.bill_date <= date_max
    ).order_by(VendorBill.bill_date.desc())

    open_bills = open_bills_query.all()

    # Score each bill
    transaction_amount_abs = abs(transaction.amount)
    bill_infos = []
    exact_matches = 0

    for bill in open_bills:
        # Calculate amount due (total - paid)
        bill_amount_due = bill.total_amount - bill.paid_amount

        # Calculate amount difference
        amount_diff = abs(bill_amount_due - transaction_amount_abs)

        # Calculate match confidence
        if amount_diff < 0.01:  # Exact match (within 1 cent)
            match_confidence = 100.0
            is_exact_match = True
            exact_matches += 1
        elif amount_diff < (transaction_amount_abs * 0.01):  # Within 1%
            match_confidence = 95.0
            is_exact_match = False
        elif amount_diff < (transaction_amount_abs * 0.05):  # Within 5%
            match_confidence = 85.0
            is_exact_match = False
        else:
            # Base confidence on percentage difference
            pct_diff = (amount_diff / transaction_amount_abs) * 100
            match_confidence = max(50.0, 100.0 - pct_diff)
            is_exact_match = False

        # Calculate date difference
        date_diff = abs((bill.bill_date - transaction.transaction_date).days)

        # Adjust confidence for date proximity
        if date_diff > 7:
            match_confidence -= min(20, (date_diff - 7) * 2)

        bill_infos.append(OpenBillInfo(
            id=bill.id,
            bill_number=bill.bill_number,
            bill_date=bill.bill_date,
            due_date=bill.due_date,
            total_amount=bill.total_amount,
            paid_amount=bill.paid_amount,
            amount_due=bill_amount_due,
            description=bill.description,
            match_confidence=round(match_confidence, 1),
            is_exact_match=is_exact_match,
            amount_difference=amount_diff,
            date_difference=date_diff
        ))

    # Sort by confidence (exact matches first)
    bill_infos.sort(key=lambda x: (not x.is_exact_match, -x.match_confidence))

    # Build response
    vendor_info = VendorInfo(
        id=vendor.id,
        vendor_name=vendor.vendor_name,
        vendor_code=vendor.vendor_code
    )

    return OpenBillsResponse(
        bank_transaction_id=transaction.id,
        bank_amount=transaction.amount,
        bank_date=transaction.transaction_date,
        bank_description=transaction.description,
        vendor=vendor_info,
        open_bills=bill_infos,
        total_bills=len(bill_infos),
        exact_matches=exact_matches
    )


@router.post("/transactions/{transaction_id}/match-bills", response_model=MatchBillsResponse)
def match_transaction_to_bills(
    transaction_id: int,
    match_request: MatchBillsRequest,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    Match a bank transaction to one or more vendor bills

    This endpoint:
    1. Validates all bills exist and are unpaid
    2. Calculates total amount of selected bills
    3. Creates clearing journal entry to match bank transaction to bills
    4. Updates bill statuses to 'paid'
    5. Marks bank transaction as reconciled

    Supports:
    - Single bill matching (1 transaction -> 1 bill)
    - Multi-bill matching (1 transaction -> multiple bills)

    Example:
        Transaction: -$150.00
        Bill 1: $75.00
        Bill 2: $75.00
        -> Creates clearing JE to match all three
    """
    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Validate bills exist
    bills = db.query(VendorBill).filter(VendorBill.id.in_(match_request.bill_ids)).all()

    if len(bills) != len(match_request.bill_ids):
        raise HTTPException(status_code=404, detail="One or more bills not found")

    # Calculate total amount due
    total_bill_amount = sum((bill.total_amount - bill.paid_amount) for bill in bills)
    transaction_amount_abs = abs(transaction.amount)

    # Check if amounts match (within $0.10)
    amount_difference = abs(total_bill_amount - transaction_amount_abs)

    if amount_difference > 0.10:
        # Allow but warn
        pass  # Could raise warning or require confirmation

    # Create clearing journal entry if requested
    clearing_je_id = None
    adjustment_je_id = None

    if match_request.create_clearing_entry:
        # Get bank account GL account
        bank_account = db.query(BankAccount).filter(BankAccount.id == transaction.bank_account_id).first()
        if not bank_account or not bank_account.gl_account_id:
            raise HTTPException(status_code=400, detail="Bank account GL account not configured")

        # Get Accounts Payable account (2100)
        ap_account = db.query(Account).filter(Account.account_number == '2100').first()
        if not ap_account:
            raise HTTPException(status_code=400, detail="Accounts Payable account (2100) not found")

        # Create clearing journal entry
        # DR Bank Account (to clear the negative transaction)
        # CR Accounts Payable (to clear the bills)
        from datetime import datetime

        # Generate unique entry number
        # Find the highest number from existing BANK entries
        max_bank_entry = db.query(JournalEntry.entry_number).filter(
            JournalEntry.entry_number.like('JE-BANK-%')
        ).order_by(JournalEntry.entry_number.desc()).first()

        if max_bank_entry:
            try:
                last_num = int(max_bank_entry[0].split('-')[-1])
                next_num = last_num + 1
            except (ValueError, IndexError):
                next_num = 1
        else:
            next_num = 1

        clearing_je = JournalEntry(
            entry_date=transaction.transaction_date,
            entry_number=f"JE-BANK-{next_num:06d}",
            description=f"Payment to {bills[0].vendor_name if len(bills) == 1 else 'Multiple Vendors'} - Bank Rec Match",
            reference_type='bank_transaction',
            reference_id=transaction.id,
            status='POSTED',
            created_by=user_id,
            approved_by=user_id,
            posted_at=datetime.now()
        )
        db.add(clearing_je)
        db.flush()  # Get the JE ID

        # Line 1: DR Bank Account (increases asset, clears negative transaction)
        line1 = JournalEntryLine(
            journal_entry_id=clearing_je.id,
            account_id=bank_account.gl_account_id,
            debit_amount=transaction_amount_abs,
            credit_amount=0,
            description=f"Clear bank transaction - {transaction.description[:100]}"
        )
        db.add(line1)

        # Line 2: CR Accounts Payable (decreases liability, clears bills)
        line2 = JournalEntryLine(
            journal_entry_id=clearing_je.id,
            account_id=ap_account.id,
            debit_amount=0,
            credit_amount=total_bill_amount,
            description=f"Clear vendor bill(s): {', '.join([b.bill_number for b in bills])}"
        )
        db.add(line2)

        clearing_je_id = clearing_je.id

        # If there's a difference, create adjustment entry
        if amount_difference > 0.01:
            # Get adjustment account (6999 - Miscellaneous Expense or Cash Over/Short)
            adj_account = db.query(Account).filter(
                Account.account_number.in_(['6999', '6900', '8000'])
            ).first()

            if adj_account:
                # Create adjustment JE
                adjustment_je = JournalEntry(
                    entry_date=transaction.transaction_date,
                    entry_number=f"JE-BANK-ADJ-{next_num:06d}",
                    description=f"Payment adjustment - ${amount_difference:.2f} difference",
                    reference_type='bank_transaction',
                    reference_id=transaction.id,
                    status='POSTED',
                    created_by=user_id,
                    approved_by=user_id,
                    posted_at=datetime.now()
                )
                db.add(adjustment_je)
                db.flush()

                # Determine if we're over or under
                if total_bill_amount > transaction_amount_abs:
                    # Bills total more than payment - we owe less AP
                    # DR Accounts Payable (reduce liability)
                    # CR Adjustment Account (income/gain)
                    adj_line1 = JournalEntryLine(
                        journal_entry_id=adjustment_je.id,
                        account_id=ap_account.id,
                        debit_amount=amount_difference,
                        credit_amount=0,
                        description="Adjustment - overpaid"
                    )
                    adj_line2 = JournalEntryLine(
                        journal_entry_id=adjustment_je.id,
                        account_id=adj_account.id,
                        debit_amount=0,
                        credit_amount=amount_difference,
                        description="Payment adjustment gain"
                    )
                else:
                    # Payment more than bills - we paid too much
                    # DR Adjustment Account (expense/loss)
                    # CR Accounts Payable (increase liability for overpayment)
                    adj_line1 = JournalEntryLine(
                        journal_entry_id=adjustment_je.id,
                        account_id=adj_account.id,
                        debit_amount=amount_difference,
                        credit_amount=0,
                        description="Payment adjustment loss"
                    )
                    adj_line2 = JournalEntryLine(
                        journal_entry_id=adjustment_je.id,
                        account_id=ap_account.id,
                        debit_amount=0,
                        credit_amount=amount_difference,
                        description="Adjustment - underpaid"
                    )

                db.add(adj_line1)
                db.add(adj_line2)
                adjustment_je_id = adjustment_je.id

    # Update bill statuses
    for bill in bills:
        bill_amount_due = bill.total_amount - bill.paid_amount
        payment_amount = min(bill_amount_due, transaction_amount_abs)

        bill.paid_amount += payment_amount
        if bill.paid_amount >= bill.total_amount:
            bill.status = 'PAID'
        elif bill.paid_amount > 0:
            bill.status = 'PARTIALLY_PAID'

    # Mark transaction as matched
    transaction.status = 'reconciled'

    # Create match record
    match_record = BankTransactionMatch(
        bank_transaction_id=transaction.id,
        match_type='vendor_bill',
        confidence_score=100.0,
        match_reason=f"Matched to {len(bills)} vendor bill(s): {', '.join([b.bill_number for b in bills])}",
        amount_difference=amount_difference,
        confirmed_by=user_id,
        confirmed_at=func.current_timestamp(),
        clearing_journal_entry_id=clearing_je_id,
        adjustment_journal_entry_id=adjustment_je_id,
        status='confirmed'
    )
    db.add(match_record)

    # Commit all changes
    db.commit()

    return MatchBillsResponse(
        bank_transaction_id=transaction.id,
        matched_bill_ids=match_request.bill_ids,
        total_amount_matched=total_bill_amount,
        clearing_journal_entry_id=clearing_je_id,
        adjustment_journal_entry_id=adjustment_je_id,
        status='confirmed',
        message=f"Successfully matched transaction to {len(bills)} bill(s)"
    )


@router.post("/transactions/{transaction_id}/assign-gl", response_model=GLAssignmentResponse)
def assign_transaction_to_gl(
    transaction_id: int,
    gl_request: GLAssignmentRequest,
    user_id: int = Query(..., description="User ID performing the assignment"),
    db: Session = Depends(get_db)
):
    """
    Assign a bank transaction directly to a GL account.

    This creates a journal entry that:
    - Debits the Bank Account (clearing the transaction)
    - Credits/Debits the selected GL account (depending on transaction type)

    Used for:
    - Bank fees
    - Interest income/expense
    - Payroll transfers
    - Owner draws/contributions
    - Direct expense payments not tracked as vendor bills
    """
    from datetime import datetime

    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status == 'reconciled':
        raise HTTPException(status_code=400, detail="Transaction already reconciled")

    # Get bank account
    bank_account = db.query(BankAccount).filter(BankAccount.id == transaction.bank_account_id).first()
    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if not bank_account.gl_account_id:
        raise HTTPException(status_code=400, detail="Bank account has no linked GL account")

    # Get the GL account to assign to
    gl_account = db.query(Account).filter(Account.id == gl_request.account_id).first()
    if not gl_account:
        raise HTTPException(status_code=404, detail="GL account not found")

    # Determine debit/credit based on transaction amount
    # Negative amounts = money out of bank (expense, payment)
    # Positive amounts = money into bank (revenue, deposit)
    transaction_amount = float(transaction.amount)
    is_expense = transaction_amount < 0
    transaction_amount_abs = abs(transaction_amount)

    # Generate unique entry number (exclude JE-BANK-ADJ- entries)
    max_bank_entry = db.query(JournalEntry.entry_number).filter(
        JournalEntry.entry_number.like('JE-BANK-%'),
        ~JournalEntry.entry_number.like('JE-BANK-ADJ-%')
    ).order_by(JournalEntry.entry_number.desc()).first()

    if max_bank_entry:
        try:
            last_num = int(max_bank_entry[0].split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    # Create journal entry
    memo = gl_request.memo or transaction.description
    je = JournalEntry(
        entry_date=transaction.transaction_date,
        entry_number=f"JE-BANK-{next_num:06d}",
        description=f"Bank Rec - {memo[:100]}",
        reference_type='bank_transaction',
        reference_id=transaction.id,
        status='POSTED',
        created_by=user_id,
        approved_by=user_id,
        posted_at=datetime.now()
        # Note: area_id is tracked on journal_entry_lines, not on journal_entry
    )
    db.add(je)
    db.flush()  # Get the JE ID

    # Use bank account's area_id for all journal entry lines
    # This ensures transactions inherit the location from their bank account
    area_id = bank_account.area_id

    # Create journal entry lines
    if is_expense:
        # Money OUT: DR Expense/Asset, CR Bank
        # Line 1: Debit the GL account (expense/asset increase)
        line1 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=gl_request.account_id,
            debit_amount=transaction_amount_abs,
            credit_amount=0,
            description=memo,
            area_id=area_id
        )
        # Line 2: Credit the Bank account (asset decrease)
        line2 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=bank_account.gl_account_id,
            debit_amount=0,
            credit_amount=transaction_amount_abs,
            description=f"Bank: {transaction.description[:100]}",
            area_id=area_id
        )
    else:
        # Money IN: DR Bank, CR Revenue/Liability
        # Line 1: Debit the Bank account (asset increase)
        line1 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=bank_account.gl_account_id,
            debit_amount=transaction_amount_abs,
            credit_amount=0,
            description=f"Bank: {transaction.description[:100]}",
            area_id=area_id
        )
        # Line 2: Credit the GL account (revenue/liability increase)
        line2 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=gl_request.account_id,
            debit_amount=0,
            credit_amount=transaction_amount_abs,
            description=memo,
            area_id=area_id
        )

    db.add(line1)
    db.add(line2)

    # Update transaction status and GL assignment
    transaction.status = 'reconciled'
    transaction.matched_journal_line_id = line2.id if is_expense else line1.id
    transaction.suggested_account_id = gl_request.account_id  # Store GL account for display

    # Create match record
    match_record = BankTransactionMatch(
        bank_transaction_id=transaction.id,
        match_type='gl_account',
        confidence_score=100.0,
        match_reason=f"Manually assigned to GL account: {gl_account.account_number} - {gl_account.account_name}",
        amount_difference=0,
        confirmed_by=user_id,
        confirmed_at=func.current_timestamp(),
        clearing_journal_entry_id=je.id,
        status='confirmed'
    )
    db.add(match_record)

    # Commit all changes
    db.commit()

    # Learn from this assignment for future suggestions
    try:
        from accounting.services.gl_learning_service import GLLearningService
        from accounting.utils.vendor_recognition import VendorRecognitionService

        # Try to recognize vendor
        vendor_id = None
        if transaction.description:
            vendor_service = VendorRecognitionService(db)
            extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)
            if vendor:
                vendor_id = vendor.id

        # Record the learning (Phase 2: with amount and transaction_date)
        learning_service = GLLearningService(db)
        learning_service.learn_from_assignment(
            description=transaction.description or '',
            account_id=gl_request.account_id,
            vendor_id=vendor_id,
            suggested_account_id=None,  # No suggestion was made for this assignment
            amount=transaction.amount,
            transaction_date=transaction.transaction_date
        )
    except Exception as e:
        # Don't fail the assignment if learning fails
        print(f"Warning: Failed to record GL learning: {e}")

    return GLAssignmentResponse(
        bank_transaction_id=transaction.id,
        journal_entry_id=je.id,
        account_id=gl_request.account_id,
        status='confirmed',
        message=f"Successfully assigned to {gl_account.account_number} - {gl_account.account_name}"
    )


@router.put("/transactions/{transaction_id}/update-gl", response_model=GLAssignmentResponse)
def update_transaction_gl_assignment(
    transaction_id: int,
    gl_request: GLAssignmentRequest,
    user_id: int = Query(..., description="User ID performing the update"),
    db: Session = Depends(get_db)
):
    """
    Update the GL account assignment for a bank transaction.

    This endpoint allows changing the GL account even after a transaction has been reconciled.
    It updates the suggested_account_id field without creating a new journal entry.

    Note: This only updates the display/tracking field. To change the actual journal entry,
    you would need to void the old entry and create a new one.
    """
    from datetime import datetime

    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Get the GL account to assign to
    gl_account = db.query(Account).filter(Account.id == gl_request.account_id).first()
    if not gl_account:
        raise HTTPException(status_code=404, detail="GL account not found")

    # Store old account for learning feedback
    old_account_id = transaction.suggested_account_id

    # Simply update the suggested_account_id field
    transaction.suggested_account_id = gl_request.account_id

    db.commit()

    # Learn from this update
    try:
        from accounting.services.gl_learning_service import GLLearningService
        from accounting.utils.vendor_recognition import VendorRecognitionService

        # Try to recognize vendor
        vendor_id = None
        if transaction.description:
            vendor_service = VendorRecognitionService(db)
            extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)
            if vendor:
                vendor_id = vendor.id

        # Record the learning (Phase 2: with amount and transaction_date)
        learning_service = GLLearningService(db)
        learning_service.learn_from_assignment(
            description=transaction.description or '',
            account_id=gl_request.account_id,
            vendor_id=vendor_id,
            suggested_account_id=old_account_id,  # Previous suggestion (if any)
            amount=transaction.amount,
            transaction_date=transaction.transaction_date
        )
    except Exception as e:
        # Don't fail the update if learning fails
        print(f"Warning: Failed to record GL learning: {e}")

    return GLAssignmentResponse(
        bank_transaction_id=transaction.id,
        journal_entry_id=transaction.matched_journal_entry_id or 0,
        account_id=gl_request.account_id,
        status='updated',
        message=f"GL account updated to {gl_account.account_number} - {gl_account.account_name}"
    )


@router.get("/transactions/{transaction_id}/gl-suggestions")
def get_gl_suggestions(
    transaction_id: int,
    db: Session = Depends(get_db)
):
    """
    Get intelligent GL account suggestions for a transaction.

    Uses machine learning from past assignments to suggest appropriate GL accounts.
    Combines vendor-based and pattern-based learning for best results.
    """
    from accounting.services.gl_learning_service import GLLearningService
    from accounting.utils.vendor_recognition import VendorRecognitionService
    from accounting.schemas.gl_suggestion import GLSuggestionsResponse

    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Try to recognize vendor from description
    vendor_id = None
    vendor_name = None
    if transaction.description:
        vendor_service = VendorRecognitionService(db)
        extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)
        if vendor:
            vendor_id = vendor.id
            vendor_name = vendor.vendor_name

    # Get suggestions from learning service (Phase 2: with transaction_date)
    learning_service = GLLearningService(db)
    suggestions = learning_service.get_suggestions_for_transaction(
        transaction_id=transaction.id,
        description=transaction.description or '',
        amount=transaction.amount,
        vendor_id=vendor_id,
        transaction_date=transaction.transaction_date
    )

    # Phase 3: Auto-assignment for high confidence (>90%)
    auto_assign_enabled = False
    auto_assign_account_id = None
    if suggestions and len(suggestions) > 0:
        top_suggestion = suggestions[0]
        if float(top_suggestion.confidence_score) >= 90.0:
            auto_assign_enabled = True
            auto_assign_account_id = top_suggestion.account_id

    return GLSuggestionsResponse(
        bank_transaction_id=transaction.id,
        description=transaction.description or '',
        amount=transaction.amount,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        suggestions=suggestions,
        total_suggestions=len(suggestions),
        auto_assign_enabled=auto_assign_enabled,
        auto_assign_account_id=auto_assign_account_id
    )


@router.post("/batch-learn")
def batch_learn_from_history(
    limit: Optional[int] = Query(None, description="Limit number of transactions to process"),
    db: Session = Depends(get_db)
):
    """
    Phase 3: Batch learning from historical transactions.

    Trains the GL learning system on all previously assigned bank transactions.
    This is useful for:
    - Initial setup after implementing the learning system
    - Retraining the system after clearing learning data
    - Updating learning data after bulk imports

    Returns statistics about what was learned.
    """
    from accounting.services.gl_learning_service import GLLearningService

    learning_service = GLLearningService(db)
    stats = learning_service.batch_learn_from_history(limit=limit)

    return {
        "success": True,
        "message": "Batch learning completed",
        "statistics": stats
    }


@router.post("/refine-patterns")
def refine_learning_patterns(
    min_confidence: float = Query(20.0, description="Minimum confidence to keep patterns"),
    merge_threshold: float = Query(0.8, description="Similarity threshold for merging patterns"),
    db: Session = Depends(get_db)
):
    """
    Phase 3: Pattern refinement and cleanup.

    Performs maintenance on learning patterns:
    - Archives low-confidence patterns that are rejected more than accepted
    - Merges similar patterns pointing to the same account
    - Deactivates stale recurring patterns (90+ days old)

    This should be run periodically to keep the learning system optimized.
    """
    from accounting.services.gl_learning_service import GLLearningService

    learning_service = GLLearningService(db)
    stats = learning_service.refine_patterns(
        min_confidence=min_confidence,
        merge_threshold=merge_threshold
    )

    return {
        "success": True,
        "message": "Pattern refinement completed",
        "statistics": stats
    }


@router.post("/transactions/{transaction_id}/confirm-auto-match", response_model=GLAssignmentResponse)
def confirm_auto_match(
    transaction_id: int,
    gl_request: GLAssignmentRequest,
    user_id: int = Query(..., description="User ID confirming the auto-match"),
    db: Session = Depends(get_db)
):
    """
    Confirm and approve an auto-matched transaction.

    This endpoint:
    1. Verifies the auto-match exists with sufficient confidence
    2. Creates a journal entry (similar to assign-gl)
    3. Marks the transaction as reconciled
    4. Records confirmation timestamp and user
    5. Provides feedback to the learning system
    """
    from datetime import datetime

    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status == 'reconciled':
        raise HTTPException(status_code=400, detail="Transaction already reconciled")

    # Verify this is actually an auto-match with sufficient confidence
    if not transaction.suggested_account_id or not transaction.suggestion_confidence:
        raise HTTPException(status_code=400, detail="Transaction does not have an auto-match suggestion")

    if transaction.suggestion_confidence < 70:
        raise HTTPException(status_code=400, detail="Auto-match confidence is too low to verify (<70%)")

    # Get bank account
    bank_account = db.query(BankAccount).filter(BankAccount.id == transaction.bank_account_id).first()
    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if not bank_account.gl_account_id:
        raise HTTPException(status_code=400, detail="Bank account has no linked GL account")

    # Get the GL account
    gl_account = db.query(Account).filter(Account.id == gl_request.account_id).first()
    if not gl_account:
        raise HTTPException(status_code=404, detail="GL account not found")

    # Determine debit/credit based on transaction amount
    transaction_amount = float(transaction.amount)
    is_expense = transaction_amount < 0
    transaction_amount_abs = abs(transaction_amount)

    # Generate unique entry number
    max_bank_entry = db.query(JournalEntry.entry_number).filter(
        JournalEntry.entry_number.like('JE-BANK-%'),
        ~JournalEntry.entry_number.like('JE-BANK-ADJ-%')
    ).order_by(JournalEntry.entry_number.desc()).first()

    if max_bank_entry:
        try:
            last_num = int(max_bank_entry[0].split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    # Create journal entry
    memo = gl_request.memo or transaction.description
    je = JournalEntry(
        entry_date=transaction.transaction_date,
        entry_number=f"JE-BANK-{next_num:06d}",
        description=f"Bank Rec (Auto-Match) - {memo[:100]}",
        reference_type='bank_transaction',
        reference_id=transaction.id,
        status='POSTED',
        created_by=user_id,
        approved_by=user_id,
        posted_at=datetime.now()
    )
    db.add(je)
    db.flush()

    # Use bank account's area_id
    area_id = bank_account.area_id

    # Create journal entry lines
    if is_expense:
        # Money OUT: DR Expense/Asset, CR Bank
        line1 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=gl_request.account_id,
            debit_amount=transaction_amount_abs,
            credit_amount=0,
            description=memo,
            area_id=area_id
        )
        line2 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=bank_account.gl_account_id,
            debit_amount=0,
            credit_amount=transaction_amount_abs,
            description=f"Bank: {transaction.description[:100]}",
            area_id=area_id
        )
    else:
        # Money IN: DR Bank, CR Revenue/Liability
        line1 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=bank_account.gl_account_id,
            debit_amount=transaction_amount_abs,
            credit_amount=0,
            description=f"Bank: {transaction.description[:100]}",
            area_id=area_id
        )
        line2 = JournalEntryLine(
            journal_entry_id=je.id,
            account_id=gl_request.account_id,
            debit_amount=0,
            credit_amount=transaction_amount_abs,
            description=memo,
            area_id=area_id
        )

    db.add(line1)
    db.add(line2)

    # Update transaction status - mark as confirmed
    transaction.status = 'reconciled'
    transaction.matched_journal_line_id = line2.id if is_expense else line1.id
    transaction.confirmed_at = func.current_timestamp()
    transaction.confirmed_by = user_id

    # Create match record
    match_record = BankTransactionMatch(
        bank_transaction_id=transaction.id,
        match_type='gl_account',
        confidence_score=transaction.suggestion_confidence,
        match_reason=f"Auto-match confirmed (confidence: {transaction.suggestion_confidence:.0f}%): {gl_account.account_number} - {gl_account.account_name}",
        amount_difference=0,
        confirmed_by=user_id,
        confirmed_at=func.current_timestamp(),
        clearing_journal_entry_id=je.id,
        status='confirmed'
    )
    db.add(match_record)

    # Commit all changes
    db.commit()

    # Provide positive feedback to learning system (auto-match was correct!)
    try:
        from accounting.services.gl_learning_service import GLLearningService
        from accounting.utils.vendor_recognition import VendorRecognitionService

        # Try to recognize vendor
        vendor_id = None
        if transaction.description:
            vendor_service = VendorRecognitionService(db)
            extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)
            if vendor:
                vendor_id = vendor.id

        # Record positive feedback (suggestion was accepted)
        learning_service = GLLearningService(db)
        learning_service.learn_from_assignment(
            description=transaction.description or '',
            account_id=gl_request.account_id,
            vendor_id=vendor_id,
            suggested_account_id=transaction.suggested_account_id,  # The suggestion that was confirmed
            amount=transaction.amount,
            transaction_date=transaction.transaction_date
        )
    except Exception as e:
        print(f"Warning: Failed to record GL learning feedback: {e}")

    return GLAssignmentResponse(
        bank_transaction_id=transaction.id,
        journal_entry_id=je.id,
        account_id=gl_request.account_id,
        status='confirmed',
        message=f"Auto-match verified and confirmed: {gl_account.account_number} - {gl_account.account_name}"
    )


@router.post("/transactions/{transaction_id}/reject-auto-match")
def reject_auto_match(
    transaction_id: int,
    user_id: int = Query(..., description="User ID rejecting the auto-match"),
    db: Session = Depends(get_db)
):
    """
    Reject an auto-matched suggestion.

    This endpoint:
    1. Clears the suggested_account_id and suggestion_confidence
    2. Keeps transaction as unreconciled
    3. Provides negative feedback to the learning system
    4. Returns success message
    """

    # Get transaction
    transaction = db.query(BankTransaction).filter(BankTransaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status == 'reconciled':
        raise HTTPException(status_code=400, detail="Transaction already reconciled - cannot reject")

    # Verify this is actually an auto-match
    if not transaction.suggested_account_id or not transaction.suggestion_confidence:
        raise HTTPException(status_code=400, detail="Transaction does not have an auto-match suggestion")

    # Store for feedback
    rejected_account_id = transaction.suggested_account_id
    rejected_confidence = transaction.suggestion_confidence

    # Clear the auto-match suggestion
    transaction.suggested_account_id = None
    transaction.suggestion_confidence = None

    db.commit()

    # Provide negative feedback to learning system (auto-match was wrong)
    try:
        from accounting.services.gl_learning_service import GLLearningService
        from accounting.utils.vendor_recognition import VendorRecognitionService

        # Try to recognize vendor
        vendor_id = None
        if transaction.description:
            vendor_service = VendorRecognitionService(db)
            extracted_name, vendor, confidence = vendor_service.recognize_vendor(transaction.description)
            if vendor:
                vendor_id = vendor.id

        # Record negative feedback (suggestion was rejected)
        learning_service = GLLearningService(db)
        learning_service.record_rejection(
            description=transaction.description or '',
            suggested_account_id=rejected_account_id,
            vendor_id=vendor_id,
            amount=transaction.amount,
            transaction_date=transaction.transaction_date
        )
    except Exception as e:
        print(f"Warning: Failed to record GL learning rejection: {e}")

    return {
        "success": True,
        "message": "Auto-match suggestion rejected. Transaction remains unreconciled.",
        "transaction_id": transaction_id,
        "rejected_account_id": rejected_account_id,
        "rejected_confidence": float(rejected_confidence)
    }
