"""
Reports API endpoints - Trial Balance, General Ledger, Cash Flow Statement, etc.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import date
from decimal import Decimal
from io import BytesIO

from accounting.db.database import get_db
from accounting.models.account import Account, AccountType
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.user import User
from accounting.models.area import Area
from accounting.api.auth import require_auth
from accounting.utils.pdf_generator import PDFReportGenerator
from accounting.services.cash_flow_service import CashFlowStatementService
from accounting.schemas.cash_flow import CashFlowStatementResponse
from pydantic import BaseModel


router = APIRouter(prefix="/api/reports", tags=["Reports"])


# Pydantic schemas
class TrialBalanceLineResponse(BaseModel):
    account_id: int
    account_number: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal


class TrialBalanceSummaryResponse(BaseModel):
    as_of_date: date
    total_debits: Decimal
    total_credits: Decimal
    difference: Decimal
    is_balanced: bool
    lines: List[TrialBalanceLineResponse]


class GeneralLedgerLineResponse(BaseModel):
    entry_date: date
    entry_number: str
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    balance: Decimal
    status: str


class GeneralLedgerResponse(BaseModel):
    account_number: str
    account_name: str
    account_type: str
    start_date: date
    end_date: date
    beginning_balance: Decimal
    ending_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    transactions: List[GeneralLedgerLineResponse]


@router.get("/trial-balance", response_model=TrialBalanceSummaryResponse)
def get_trial_balance(
    as_of_date: date = Query(..., description="Date for trial balance"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Trial Balance report as of a specific date
    Shows all accounts with their debit or credit balances

    Multi-Location Support:
    - If area_id is provided: Shows Trial Balance for that specific location
    - If area_id is null: Shows consolidated Trial Balance for all locations
    """
    # Get all active accounts
    accounts = db.query(Account).filter(Account.is_active == True).all()

    trial_balance_lines = []
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')

    for account in accounts:
        # Build filter conditions
        filter_conditions = [
            JournalEntryLine.account_id == account.id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date
        ]

        # Add location filter if specified
        if area_id is not None:
            filter_conditions.append(JournalEntryLine.area_id == area_id)

        # Get all posted journal entry lines for this account up to the as_of_date
        debit_sum = db.query(func.sum(JournalEntryLine.debit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        credit_sum = db.query(func.sum(JournalEntryLine.credit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        # Calculate net balance
        net_balance = debit_sum - credit_sum

        # Determine if this account has a debit or credit balance
        debit_balance = Decimal('0.00')
        credit_balance = Decimal('0.00')

        if net_balance > 0:
            debit_balance = net_balance
        elif net_balance < 0:
            credit_balance = abs(net_balance)

        # Only include accounts with activity
        if debit_balance > 0 or credit_balance > 0:
            trial_balance_lines.append(TrialBalanceLineResponse(
                account_id=account.id,
                account_number=account.account_number,
                account_name=account.account_name,
                account_type=account.account_type.value,
                debit_balance=debit_balance,
                credit_balance=credit_balance
            ))

            total_debits += debit_balance
            total_credits += credit_balance

    # Sort by account number
    trial_balance_lines.sort(key=lambda x: x.account_number)

    difference = abs(total_debits - total_credits)
    is_balanced = difference < Decimal('0.01')

    return TrialBalanceSummaryResponse(
        as_of_date=as_of_date,
        total_debits=total_debits,
        total_credits=total_credits,
        difference=difference,
        is_balanced=is_balanced,
        lines=trial_balance_lines
    )


@router.get("/general-ledger/{account_id}", response_model=GeneralLedgerResponse)
def get_general_ledger(
    account_id: int,
    start_date: date = Query(..., description="Start date for report"),
    end_date: date = Query(..., description="End date for report"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate General Ledger report for a specific account
    Shows all transactions for the account within the date range

    Multi-Location Support:
    - If area_id is provided: Shows GL for that specific location only
    - If area_id is null: Shows consolidated GL for all locations
    """
    # Get the account
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Account not found")

    # Build beginning balance filter conditions
    beginning_filters = [
        JournalEntryLine.account_id == account_id,
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date < start_date
    ]
    if area_id is not None:
        beginning_filters.append(JournalEntryLine.area_id == area_id)

    # Calculate beginning balance (all transactions before start_date)
    beginning_debits = db.query(func.sum(JournalEntryLine.debit_amount)).join(
        JournalEntry
    ).filter(and_(*beginning_filters)).scalar() or Decimal('0.00')

    beginning_credits = db.query(func.sum(JournalEntryLine.credit_amount)).join(
        JournalEntry
    ).filter(and_(*beginning_filters)).scalar() or Decimal('0.00')

    beginning_balance = beginning_debits - beginning_credits

    # Build transaction query filter conditions
    transaction_filters = [
        JournalEntryLine.account_id == account_id,
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date >= start_date,
        JournalEntry.entry_date <= end_date
    ]
    if area_id is not None:
        transaction_filters.append(JournalEntryLine.area_id == area_id)

    # Get all transactions in the date range
    transactions_query = db.query(
        JournalEntry.entry_date,
        JournalEntry.entry_number,
        JournalEntry.description,
        JournalEntryLine.debit_amount,
        JournalEntryLine.credit_amount,
        JournalEntry.status
    ).join(
        JournalEntryLine, JournalEntry.id == JournalEntryLine.journal_entry_id
    ).filter(and_(*transaction_filters)).order_by(JournalEntry.entry_date, JournalEntry.entry_number)

    transactions = transactions_query.all()

    # Build transaction lines with running balance
    transaction_lines = []
    running_balance = beginning_balance
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')

    for txn in transactions:
        debit_amount = txn.debit_amount or Decimal('0.00')
        credit_amount = txn.credit_amount or Decimal('0.00')

        running_balance += debit_amount - credit_amount
        total_debits += debit_amount
        total_credits += credit_amount

        transaction_lines.append(GeneralLedgerLineResponse(
            entry_date=txn.entry_date,
            entry_number=txn.entry_number,
            description=txn.description,
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            balance=running_balance,
            status=txn.status.value
        ))

    ending_balance = running_balance

    return GeneralLedgerResponse(
        account_number=account.account_number,
        account_name=account.account_name,
        account_type=account.account_type.value,
        start_date=start_date,
        end_date=end_date,
        beginning_balance=beginning_balance,
        ending_balance=ending_balance,
        total_debits=total_debits,
        total_credits=total_credits,
        transactions=transaction_lines
    )


@router.get("/account-activity-summary")
def get_account_activity_summary(
    start_date: date = Query(..., description="Start date"),
    end_date: date = Query(..., description="End date"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Get summary of account activity for a date range
    Shows which accounts have transactions
    """
    # Get accounts with activity in the date range
    accounts_with_activity = db.query(
        Account.id,
        Account.account_number,
        Account.account_name,
        Account.account_type,
        func.count(JournalEntryLine.id).label('transaction_count'),
        func.sum(JournalEntryLine.debit_amount).label('total_debits'),
        func.sum(JournalEntryLine.credit_amount).label('total_credits')
    ).join(
        JournalEntryLine, Account.id == JournalEntryLine.account_id
    ).join(
        JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id
    ).filter(
        and_(
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )
    ).group_by(
        Account.id, Account.account_number, Account.account_name, Account.account_type
    ).order_by(Account.account_number).all()

    result = []
    for account in accounts_with_activity:
        result.append({
            "account_id": account.id,
            "account_number": account.account_number,
            "account_name": account.account_name,
            "account_type": account.account_type.value,
            "transaction_count": account.transaction_count,
            "total_debits": float(account.total_debits or 0),
            "total_credits": float(account.total_credits or 0),
            "net_change": float((account.total_debits or 0) - (account.total_credits or 0))
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "accounts": result
    }


# Profit & Loss (Income Statement) Schemas
class PLAccountLine(BaseModel):
    account_id: int
    account_number: str
    account_name: str
    amount: Decimal


class PLSectionResponse(BaseModel):
    section_name: str
    accounts: List[PLAccountLine]
    total: Decimal


class ProfitLossResponse(BaseModel):
    start_date: date
    end_date: date
    revenue_section: PLSectionResponse
    cogs_section: PLSectionResponse
    gross_profit: Decimal
    expense_section: PLSectionResponse
    net_income: Decimal


# Hierarchical P&L Schemas
class HierarchicalPLAccountLine(BaseModel):
    account_id: int
    account_number: str
    account_name: str
    is_summary: bool
    hierarchy_level: int
    amount: Decimal
    children: List['HierarchicalPLAccountLine'] = []

    class Config:
        from_attributes = True


# Enable forward reference for recursive model
HierarchicalPLAccountLine.model_rebuild()


class HierarchicalPLSectionResponse(BaseModel):
    section_name: str
    accounts: List[HierarchicalPLAccountLine]
    total: Decimal


class HierarchicalProfitLossResponse(BaseModel):
    start_date: date
    end_date: date
    area_id: Optional[int]
    area_name: Optional[str]
    area_legal_name: Optional[str]
    area_address_line1: Optional[str]
    area_address_line2: Optional[str]
    area_city: Optional[str]
    area_state: Optional[str]
    area_zip_code: Optional[str]
    revenue_section: HierarchicalPLSectionResponse
    cogs_section: HierarchicalPLSectionResponse
    gross_profit: Decimal
    expense_section: HierarchicalPLSectionResponse
    net_income: Decimal


@router.get("/profit-loss", response_model=ProfitLossResponse)
def get_profit_loss(
    start_date: date = Query(..., description="Start date for P&L"),
    end_date: date = Query(..., description="End date for P&L"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Profit & Loss (Income Statement) report
    Shows Revenue - COGS = Gross Profit, then subtract Expenses = Net Income

    Multi-Location Support:
    - If area_id is provided: Shows P&L for that specific location
    - If area_id is null: Shows consolidated P&L for all locations
    """

    def get_account_balances(account_type: AccountType):
        """Get all accounts of a specific type with their balances"""
        accounts = db.query(Account).filter(
            Account.account_type == account_type,
            Account.is_active == True
        ).all()

        result = []
        total = Decimal('0.00')

        for account in accounts:
            # Build base filter conditions
            filter_conditions = [
                JournalEntryLine.account_id == account.id,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date
            ]

            # Add location filter if specified
            if area_id is not None:
                filter_conditions.append(JournalEntryLine.area_id == area_id)

            # Get debits and credits for this account in the date range
            debits = db.query(func.sum(JournalEntryLine.debit_amount)).join(
                JournalEntry
            ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

            credits = db.query(func.sum(JournalEntryLine.credit_amount)).join(
                JournalEntry
            ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

            # For P&L accounts:
            # Revenue: Credits increase, Debits decrease (normal credit balance)
            # Expenses/COGS: Debits increase, Credits decrease (normal debit balance)
            if account_type == AccountType.REVENUE:
                balance = credits - debits  # Revenue is normally a credit
            else:  # EXPENSE or COGS
                balance = debits - credits  # Expenses are normally debits

            # Only include accounts with activity
            if balance != Decimal('0.00'):
                result.append(PLAccountLine(
                    account_id=account.id,
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=balance
                ))
                total += balance

        return result, total

    # Get Revenue accounts
    revenue_accounts, total_revenue = get_account_balances(AccountType.REVENUE)

    # Get COGS accounts
    cogs_accounts, total_cogs = get_account_balances(AccountType.COGS)

    # Calculate Gross Profit
    gross_profit = total_revenue - total_cogs

    # Get Expense accounts
    expense_accounts, total_expenses = get_account_balances(AccountType.EXPENSE)

    # Calculate Net Income
    net_income = gross_profit - total_expenses

    return ProfitLossResponse(
        start_date=start_date,
        end_date=end_date,
        revenue_section=PLSectionResponse(
            section_name="Revenue",
            accounts=revenue_accounts,
            total=total_revenue
        ),
        cogs_section=PLSectionResponse(
            section_name="Cost of Goods Sold",
            accounts=cogs_accounts,
            total=total_cogs
        ),
        gross_profit=gross_profit,
        expense_section=PLSectionResponse(
            section_name="Operating Expenses",
            accounts=expense_accounts,
            total=total_expenses
        ),
        net_income=net_income
    )


@router.get("/profit-loss-hierarchical", response_model=HierarchicalProfitLossResponse)
def get_profit_loss_hierarchical(
    start_date: date = Query(..., description="Start date for P&L"),
    end_date: date = Query(..., description="End date for P&L"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    hide_zero: bool = Query(False, description="Hide accounts with zero balances"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Hierarchical Profit & Loss (Income Statement) report
    Shows accounts in parent-child hierarchy with proper indentation and subtotals

    Multi-Location Support:
    - If area_id is provided: Shows P&L for that specific location
    - If area_id is null: Shows consolidated P&L for all locations
    """

    # Get area details if filtering by area
    area_name = None
    area_legal_name = None
    area_address_line1 = None
    area_address_line2 = None
    area_city = None
    area_state = None
    area_zip_code = None

    if area_id:
        area = db.query(Area).filter(Area.id == area_id).first()
        if area:
            area_name = area.name
            area_legal_name = area.legal_name
            area_address_line1 = area.address_line1
            area_address_line2 = area.address_line2
            area_city = area.city
            area_state = area.state
            area_zip_code = area.zip_code

    def calculate_account_balance(account: Account) -> Decimal:
        """Calculate balance for a single account in the date range"""
        # Build base filter conditions
        filter_conditions = [
            JournalEntryLine.account_id == account.id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        ]

        # Add location filter if specified
        if area_id is not None:
            filter_conditions.append(JournalEntryLine.area_id == area_id)

        # Get debits and credits for this account in the date range
        debits = db.query(func.sum(JournalEntryLine.debit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        credits = db.query(func.sum(JournalEntryLine.credit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        # For P&L accounts:
        # Revenue: Credits increase, Debits decrease (normal credit balance)
        # Expenses/COGS: Debits increase, Credits decrease (normal debit balance)
        if account.account_type == AccountType.REVENUE:
            return credits - debits  # Revenue is normally a credit
        else:  # EXPENSE or COGS
            return debits - credits  # Expenses are normally debits

    def filter_zero_balances(nodes: List[HierarchicalPLAccountLine]) -> List[HierarchicalPLAccountLine]:
        """Recursively filter out accounts with zero balances"""
        filtered = []
        for node in nodes:
            # Filter children first
            if node.children:
                filtered_children = filter_zero_balances(node.children)
                # If this is a summary account and has non-zero children, keep it
                if filtered_children:
                    node.children = filtered_children
                    filtered.append(node)
                # If it's a non-summary account with non-zero balance, keep it
                elif node.amount != 0:
                    node.children = []
                    filtered.append(node)
            # Leaf account: keep only if non-zero
            elif node.amount != 0:
                filtered.append(node)
        return filtered

    def build_account_tree(accounts: List[Account]) -> List[HierarchicalPLAccountLine]:
        """Build hierarchical tree structure with balances"""
        # Create account map
        account_map = {}
        account_balances = {}

        # First pass: calculate direct balances for all accounts
        for account in accounts:
            direct_balance = calculate_account_balance(account)
            account_balances[account.id] = direct_balance

            account_map[account.id] = {
                'account': account,
                'direct_balance': direct_balance,
                'total_balance': direct_balance,  # Will be updated for summary accounts
                'children': []
            }

        # Second pass: build tree structure and identify root accounts
        root_accounts = []
        for account in accounts:
            if account.parent_account_id and account.parent_account_id in account_map:
                account_map[account.parent_account_id]['children'].append(account_map[account.id])
            else:
                root_accounts.append(account_map[account.id])

        # Third pass: calculate recursive balances for summary accounts (bottom-up)
        def calculate_recursive_balance(node):
            """Recursively calculate total balance including all children"""
            if not node['children']:
                return node['direct_balance']

            # Calculate children balances first (recursion)
            total = Decimal('0.00')
            for child in node['children']:
                total += calculate_recursive_balance(child)

            # For summary accounts, use sum of children
            # For leaf accounts with children (shouldn't happen but just in case), add own balance
            if node['account'].is_summary:
                node['total_balance'] = total
            else:
                node['total_balance'] = node['direct_balance'] + total

            return node['total_balance']

        # Calculate recursive balances for all root accounts
        for root in root_accounts:
            calculate_recursive_balance(root)

        # Fourth pass: convert to response format with hierarchy levels
        def node_to_response(node, level=0) -> HierarchicalPLAccountLine:
            """Convert node to response format"""
            children_responses = []
            for child in sorted(node['children'], key=lambda x: x['account'].account_number):
                children_responses.append(node_to_response(child, level + 1))

            return HierarchicalPLAccountLine(
                account_id=node['account'].id,
                account_number=node['account'].account_number,
                account_name=node['account'].account_name,
                is_summary=node['account'].is_summary,
                hierarchy_level=level,
                amount=node['total_balance'],
                children=children_responses
            )

        # Convert root accounts to response format
        result = []
        for root in sorted(root_accounts, key=lambda x: x['account'].account_number):
            result.append(node_to_response(root))

        return result

    def get_hierarchical_accounts(account_type: AccountType):
        """Get all accounts of a specific type and build hierarchy"""
        accounts = db.query(Account).filter(
            Account.account_type == account_type,
            Account.is_active == True
        ).all()

        # Build the hierarchical tree
        tree = build_account_tree(accounts)

        # Filter zero balances if requested
        if hide_zero:
            tree = filter_zero_balances(tree)

        # Calculate total (sum of root-level account balances)
        total = sum(node.amount for node in tree)

        return tree, total

    # Get Revenue accounts hierarchy
    revenue_accounts, total_revenue = get_hierarchical_accounts(AccountType.REVENUE)

    # Get COGS accounts hierarchy
    cogs_accounts, total_cogs = get_hierarchical_accounts(AccountType.COGS)

    # Calculate Gross Profit
    gross_profit = total_revenue - total_cogs

    # Get Expense accounts hierarchy
    expense_accounts, total_expenses = get_hierarchical_accounts(AccountType.EXPENSE)

    # Calculate Net Income
    net_income = gross_profit - total_expenses

    return HierarchicalProfitLossResponse(
        start_date=start_date,
        end_date=end_date,
        area_id=area_id,
        area_name=area_name,
        area_legal_name=area_legal_name,
        area_address_line1=area_address_line1,
        area_address_line2=area_address_line2,
        area_city=area_city,
        area_state=area_state,
        area_zip_code=area_zip_code,
        revenue_section=HierarchicalPLSectionResponse(
            section_name="Revenue",
            accounts=revenue_accounts,
            total=total_revenue
        ),
        cogs_section=HierarchicalPLSectionResponse(
            section_name="Cost of Goods Sold",
            accounts=cogs_accounts,
            total=total_cogs
        ),
        gross_profit=gross_profit,
        expense_section=HierarchicalPLSectionResponse(
            section_name="Operating Expenses",
            accounts=expense_accounts,
            total=total_expenses
        ),
        net_income=net_income
    )


# Balance Sheet Schemas
class BSAccountLine(BaseModel):
    account_id: int
    account_number: str
    account_name: str
    amount: Decimal


class BSSectionResponse(BaseModel):
    section_name: str
    accounts: List[BSAccountLine]
    total: Decimal


class BalanceSheetResponse(BaseModel):
    as_of_date: date
    asset_section: BSSectionResponse
    liability_section: BSSectionResponse
    equity_section: BSSectionResponse
    total_assets: Decimal
    total_liabilities_equity: Decimal
    is_balanced: bool


# Hierarchical Balance Sheet Schemas
class HierarchicalBSAccountLine(BaseModel):
    account_id: int
    account_number: str
    account_name: str
    is_summary: bool
    hierarchy_level: int
    amount: Decimal
    children: List['HierarchicalBSAccountLine'] = []

    class Config:
        from_attributes = True


# Enable forward reference for recursive model
HierarchicalBSAccountLine.model_rebuild()


class HierarchicalBSSectionResponse(BaseModel):
    section_name: str
    accounts: List[HierarchicalBSAccountLine]
    total: Decimal


class HierarchicalBalanceSheetResponse(BaseModel):
    as_of_date: date
    area_id: Optional[int]
    area_name: Optional[str]
    area_legal_name: Optional[str]
    area_address_line1: Optional[str]
    area_address_line2: Optional[str]
    area_city: Optional[str]
    area_state: Optional[str]
    area_zip_code: Optional[str]
    asset_section: HierarchicalBSSectionResponse
    liability_section: HierarchicalBSSectionResponse
    equity_section: HierarchicalBSSectionResponse
    total_assets: Decimal
    total_liabilities_equity: Decimal
    is_balanced: bool


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
def get_balance_sheet(
    as_of_date: date = Query(..., description="As of date for Balance Sheet"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Balance Sheet report
    Shows Assets = Liabilities + Equity as of a specific date

    Multi-Location Support:
    - If area_id is provided: Shows Balance Sheet for that specific location
    - If area_id is null: Shows consolidated Balance Sheet for all locations
    """

    def get_account_balances(account_type: AccountType):
        """Get all accounts of a specific type with their balances"""
        accounts = db.query(Account).filter(
            Account.account_type == account_type,
            Account.is_active == True
        ).all()

        result = []
        total = Decimal('0.00')

        for account in accounts:
            # Build base filter conditions
            filter_conditions = [
                JournalEntryLine.account_id == account.id,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.entry_date <= as_of_date
            ]

            # Add location filter if specified
            if area_id is not None:
                filter_conditions.append(JournalEntryLine.area_id == area_id)

            # Get all-time debits and credits up to as_of_date
            debits = db.query(func.sum(JournalEntryLine.debit_amount)).join(
                JournalEntry
            ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

            credits = db.query(func.sum(JournalEntryLine.credit_amount)).join(
                JournalEntry
            ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

            # For Balance Sheet accounts:
            # Assets: Debits increase, Credits decrease (normal debit balance)
            # Liabilities/Equity: Credits increase, Debits decrease (normal credit balance)
            if account_type == AccountType.ASSET:
                balance = debits - credits
            else:  # LIABILITY or EQUITY
                balance = credits - debits

            # Only include accounts with balances
            if balance != Decimal('0.00'):
                result.append(BSAccountLine(
                    account_id=account.id,
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=balance
                ))
                total += balance

        return result, total

    # Get Asset accounts
    asset_accounts, total_assets = get_account_balances(AccountType.ASSET)

    # Get Liability accounts
    liability_accounts, total_liabilities = get_account_balances(AccountType.LIABILITY)

    # Get Equity accounts
    equity_accounts, total_equity = get_account_balances(AccountType.EQUITY)

    # Calculate Net Income YTD and add to equity
    # This is a simplified approach - in practice, you'd close revenue/expenses to retained earnings
    ytd_start = date(as_of_date.year, 1, 1)

    # Build YTD revenue filter conditions
    ytd_revenue_filters = [
        Account.account_type == AccountType.REVENUE,
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date >= ytd_start,
        JournalEntry.entry_date <= as_of_date
    ]
    if area_id is not None:
        ytd_revenue_filters.append(JournalEntryLine.area_id == area_id)

    # Get YTD revenue
    ytd_revenue = db.query(
        func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
    ).join(JournalEntry).join(Account).filter(
        and_(*ytd_revenue_filters)
    ).scalar() or Decimal('0.00')

    # Build YTD expenses filter conditions
    ytd_expense_filters = [
        Account.account_type.in_([AccountType.EXPENSE, AccountType.COGS]),
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date >= ytd_start,
        JournalEntry.entry_date <= as_of_date
    ]
    if area_id is not None:
        ytd_expense_filters.append(JournalEntryLine.area_id == area_id)

    # Get YTD expenses and COGS
    ytd_expenses = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
    ).join(JournalEntry).join(Account).filter(
        and_(*ytd_expense_filters)
    ).scalar() or Decimal('0.00')

    # Add net income to equity
    ytd_net_income = ytd_revenue - ytd_expenses
    if ytd_net_income != Decimal('0.00'):
        equity_accounts.append(BSAccountLine(
            account_id=0,  # Special ID for net income (not a real account)
            account_number="NET-INCOME",
            account_name="Net Income (YTD)",
            amount=ytd_net_income
        ))
        total_equity += ytd_net_income

    total_liabilities_equity = total_liabilities + total_equity

    # Check if balanced
    difference = abs(total_assets - total_liabilities_equity)
    is_balanced = difference < Decimal('0.01')

    return BalanceSheetResponse(
        as_of_date=as_of_date,
        asset_section=BSSectionResponse(
            section_name="Assets",
            accounts=asset_accounts,
            total=total_assets
        ),
        liability_section=BSSectionResponse(
            section_name="Liabilities",
            accounts=liability_accounts,
            total=total_liabilities
        ),
        equity_section=BSSectionResponse(
            section_name="Equity",
            accounts=equity_accounts,
            total=total_equity
        ),
        total_assets=total_assets,
        total_liabilities_equity=total_liabilities_equity,
        is_balanced=is_balanced
    )


@router.get("/balance-sheet-hierarchical", response_model=HierarchicalBalanceSheetResponse)
def get_balance_sheet_hierarchical(
    as_of_date: date = Query(..., description="As of date for Balance Sheet"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    hide_zero: bool = Query(False, description="Hide accounts with zero balances"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Hierarchical Balance Sheet report
    Shows accounts in parent-child hierarchy with proper indentation and subtotals
    Assets = Liabilities + Equity as of a specific date

    Multi-Location Support:
    - If area_id is provided: Shows Balance Sheet for that specific location
    - If area_id is null: Shows consolidated Balance Sheet for all locations
    """

    # Get area details if filtering by area
    area_name = None
    area_legal_name = None
    area_address_line1 = None
    area_address_line2 = None
    area_city = None
    area_state = None
    area_zip_code = None

    if area_id:
        area = db.query(Area).filter(Area.id == area_id).first()
        if area:
            area_name = area.name
            area_legal_name = area.legal_name
            area_address_line1 = area.address_line1
            area_address_line2 = area.address_line2
            area_city = area.city
            area_state = area.state
            area_zip_code = area.zip_code

    def calculate_account_balance(account: Account) -> Decimal:
        """Calculate balance for a single account as of date"""
        # Build base filter conditions
        filter_conditions = [
            JournalEntryLine.account_id == account.id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date
        ]

        # Add location filter if specified
        if area_id is not None:
            filter_conditions.append(JournalEntryLine.area_id == area_id)

        # Get all-time debits and credits up to as_of_date
        debits = db.query(func.sum(JournalEntryLine.debit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        credits = db.query(func.sum(JournalEntryLine.credit_amount)).join(
            JournalEntry
        ).filter(and_(*filter_conditions)).scalar() or Decimal('0.00')

        # For Balance Sheet accounts:
        # Assets: Debits increase, Credits decrease (normal debit balance)
        # Liabilities/Equity: Credits increase, Debits decrease (normal credit balance)
        if account.account_type == AccountType.ASSET:
            return debits - credits
        else:  # LIABILITY or EQUITY
            return credits - debits

    def filter_zero_balances(nodes: List[HierarchicalBSAccountLine]) -> List[HierarchicalBSAccountLine]:
        """Recursively filter out accounts with zero balances"""
        filtered = []
        for node in nodes:
            # Filter children first
            if node.children:
                filtered_children = filter_zero_balances(node.children)
                # If this is a summary account and has non-zero children, keep it
                if filtered_children:
                    node.children = filtered_children
                    filtered.append(node)
                # If it's a non-summary account with non-zero balance, keep it
                elif node.amount != 0:
                    node.children = []
                    filtered.append(node)
            # Leaf account: keep only if non-zero
            elif node.amount != 0:
                filtered.append(node)
        return filtered

    def build_account_tree(accounts: List[Account]) -> List[HierarchicalBSAccountLine]:
        """Build hierarchical tree structure with balances"""
        # Create account map
        account_map = {}
        account_balances = {}

        # First pass: calculate direct balances for all accounts
        for account in accounts:
            direct_balance = calculate_account_balance(account)
            account_balances[account.id] = direct_balance

            account_map[account.id] = {
                'account': account,
                'direct_balance': direct_balance,
                'total_balance': direct_balance,  # Will be updated for summary accounts
                'children': []
            }

        # Second pass: build tree structure and identify root accounts
        root_accounts = []
        for account in accounts:
            if account.parent_account_id and account.parent_account_id in account_map:
                account_map[account.parent_account_id]['children'].append(account_map[account.id])
            else:
                root_accounts.append(account_map[account.id])

        # Third pass: calculate recursive balances for summary accounts (bottom-up)
        def calculate_recursive_balance(node):
            """Recursively calculate total balance including all children"""
            if not node['children']:
                return node['direct_balance']

            # Calculate children balances first (recursion)
            total = Decimal('0.00')
            for child in node['children']:
                total += calculate_recursive_balance(child)

            # For summary accounts, use sum of children
            # For leaf accounts with children (shouldn't happen but just in case), add own balance
            if node['account'].is_summary:
                node['total_balance'] = total
            else:
                node['total_balance'] = node['direct_balance'] + total

            return node['total_balance']

        # Calculate recursive balances for all root accounts
        for root in root_accounts:
            calculate_recursive_balance(root)

        # Fourth pass: convert to response format with hierarchy levels
        def node_to_response(node, level=0) -> HierarchicalBSAccountLine:
            """Convert node to response format"""
            children_responses = []
            for child in sorted(node['children'], key=lambda x: x['account'].account_number):
                children_responses.append(node_to_response(child, level + 1))

            return HierarchicalBSAccountLine(
                account_id=node['account'].id,
                account_number=node['account'].account_number,
                account_name=node['account'].account_name,
                is_summary=node['account'].is_summary,
                hierarchy_level=level,
                amount=node['total_balance'],
                children=children_responses
            )

        # Convert root accounts to response format
        result = []
        for root in sorted(root_accounts, key=lambda x: x['account'].account_number):
            result.append(node_to_response(root))

        return result

    def get_hierarchical_accounts(account_type: AccountType):
        """Get all accounts of a specific type and build hierarchy"""
        accounts = db.query(Account).filter(
            Account.account_type == account_type,
            Account.is_active == True
        ).all()

        # Build the hierarchical tree
        tree = build_account_tree(accounts)

        # Filter zero balances if requested
        if hide_zero:
            tree = filter_zero_balances(tree)

        # Calculate total (sum of root-level account balances)
        total = sum(node.amount for node in tree)

        return tree, total

    # Get Asset accounts hierarchy
    asset_accounts, total_assets = get_hierarchical_accounts(AccountType.ASSET)

    # Get Liability accounts hierarchy
    liability_accounts, total_liabilities = get_hierarchical_accounts(AccountType.LIABILITY)

    # Get Equity accounts hierarchy
    equity_accounts, total_equity = get_hierarchical_accounts(AccountType.EQUITY)

    # Calculate Net Income YTD and add to equity
    # This is a simplified approach - in practice, you'd close revenue/expenses to retained earnings
    ytd_start = date(as_of_date.year, 1, 1)

    # Build YTD revenue filter conditions
    ytd_revenue_filters = [
        Account.account_type == AccountType.REVENUE,
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date >= ytd_start,
        JournalEntry.entry_date <= as_of_date
    ]
    if area_id is not None:
        ytd_revenue_filters.append(JournalEntryLine.area_id == area_id)

    # Get YTD revenue
    ytd_revenue = db.query(
        func.coalesce(func.sum(JournalEntryLine.credit_amount - JournalEntryLine.debit_amount), 0)
    ).join(JournalEntry).join(Account).filter(
        and_(*ytd_revenue_filters)
    ).scalar() or Decimal('0.00')

    # Build YTD expenses filter conditions
    ytd_expense_filters = [
        Account.account_type.in_([AccountType.EXPENSE, AccountType.COGS]),
        JournalEntry.status == JournalEntryStatus.POSTED,
        JournalEntry.entry_date >= ytd_start,
        JournalEntry.entry_date <= as_of_date
    ]
    if area_id is not None:
        ytd_expense_filters.append(JournalEntryLine.area_id == area_id)

    # Get YTD expenses and COGS
    ytd_expenses = db.query(
        func.coalesce(func.sum(JournalEntryLine.debit_amount - JournalEntryLine.credit_amount), 0)
    ).join(JournalEntry).join(Account).filter(
        and_(*ytd_expense_filters)
    ).scalar() or Decimal('0.00')

    # Add net income to equity
    ytd_net_income = ytd_revenue - ytd_expenses
    if ytd_net_income != Decimal('0.00'):
        equity_accounts.append(HierarchicalBSAccountLine(
            account_id=0,  # Special ID for net income (not a real account)
            account_number="NET-INCOME",
            account_name="Net Income (YTD)",
            is_summary=False,
            hierarchy_level=0,
            amount=ytd_net_income,
            children=[]
        ))
        total_equity += ytd_net_income

    total_liabilities_equity = total_liabilities + total_equity

    # Check if balanced
    difference = abs(total_assets - total_liabilities_equity)
    is_balanced = difference < Decimal('0.01')

    return HierarchicalBalanceSheetResponse(
        as_of_date=as_of_date,
        area_id=area_id,
        area_name=area_name,
        area_legal_name=area_legal_name,
        area_address_line1=area_address_line1,
        area_address_line2=area_address_line2,
        area_city=area_city,
        area_state=area_state,
        area_zip_code=area_zip_code,
        asset_section=HierarchicalBSSectionResponse(
            section_name="Assets",
            accounts=asset_accounts,
            total=total_assets
        ),
        liability_section=HierarchicalBSSectionResponse(
            section_name="Liabilities",
            accounts=liability_accounts,
            total=total_liabilities
        ),
        equity_section=HierarchicalBSSectionResponse(
            section_name="Equity",
            accounts=equity_accounts,
            total=total_equity
        ),
        total_assets=total_assets,
        total_liabilities_equity=total_liabilities_equity,
        is_balanced=is_balanced
    )


# PDF Export Endpoints

@router.get("/profit-loss-hierarchical/pdf")
async def export_profit_loss_hierarchical_pdf(
    start_date: date = Query(..., description="Start date for P&L"),
    end_date: date = Query(..., description="End date for P&L"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    hide_zero: bool = Query(False, description="Hide accounts with zero balances"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Export Hierarchical Profit & Loss report as PDF
    """
    # Get the hierarchical P&L data (reuse existing endpoint logic)
    # We'll call the existing function to get the data
    pl_data = get_profit_loss_hierarchical(start_date, end_date, area_id, hide_zero, db, user)

    # Convert Pydantic model to dict for PDF generator
    data_dict = pl_data.model_dump(mode='json')

    # Generate PDF
    pdf_gen = PDFReportGenerator(company_name="SW Hospitality Group")
    pdf_buffer = pdf_gen.generate_hierarchical_pl(data_dict)

    # Create filename
    filename = f"PL_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
    if area_id:
        filename += f"_location{area_id}"
    filename += ".pdf"

    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/balance-sheet-hierarchical/pdf")
async def export_balance_sheet_hierarchical_pdf(
    as_of_date: date = Query(..., description="As of date for Balance Sheet"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    hide_zero: bool = Query(False, description="Hide accounts with zero balances"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Export Hierarchical Balance Sheet report as PDF
    """
    # Get the hierarchical Balance Sheet data
    bs_data = get_balance_sheet_hierarchical(as_of_date, area_id, hide_zero, db, user)

    # Convert Pydantic model to dict for PDF generator
    data_dict = bs_data.model_dump(mode='json')

    # Generate PDF
    pdf_gen = PDFReportGenerator(company_name="SW Hospitality Group")
    pdf_buffer = pdf_gen.generate_hierarchical_bs(data_dict)

    # Create filename
    filename = f"BS_{as_of_date.strftime('%Y%m%d')}"
    if area_id:
        filename += f"_location{area_id}"
    filename += ".pdf"

    # Return as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/cash-flow-statement", response_model=CashFlowStatementResponse)
def get_cash_flow_statement(
    start_date: date = Query(..., description="Start date of period"),
    end_date: date = Query(..., description="End date of period"),
    area_id: Optional[int] = Query(None, description="Filter by location/area (null = all locations)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """
    Generate Cash Flow Statement using the Indirect Method

    The indirect method starts with net income from the P&L and reconciles to
    cash from operations by adjusting for:
    1. Non-cash expenses (depreciation, amortization)
    2. Changes in working capital (AR, inventory, AP, accrued expenses)
    3. Investing activities (asset purchases/sales)
    4. Financing activities (loans, equity, distributions)

    Multi-Location Support:
    - If area_id is provided: Shows Cash Flow Statement for that specific location
    - If area_id is null: Shows consolidated Cash Flow Statement for all locations

    Returns:
        CashFlowStatementResponse with complete cash flow statement broken down by
        operating, investing, and financing activities
    """
    service = CashFlowStatementService(db)
    return service.get_cash_flow_statement(start_date, end_date, area_id)
