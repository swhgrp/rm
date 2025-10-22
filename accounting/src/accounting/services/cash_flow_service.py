"""
Cash Flow Statement Service - Indirect Method

The indirect method starts with net income from the P&L and adjusts to arrive
at cash from operations by:
1. Adding back non-cash expenses (depreciation, amortization)
2. Adjusting for changes in working capital accounts
3. Adding investing activities (purchases/sales of assets)
4. Adding financing activities (loans, equity, distributions)
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from decimal import Decimal
from datetime import date
from typing import List, Optional, Tuple

from accounting.models.account import Account, AccountType, CashFlowClass
from accounting.models.journal_entry import JournalEntry, JournalEntryLine, JournalEntryStatus
from accounting.models.area import Area
from accounting.schemas.cash_flow import (
    CashFlowLineItem,
    CashFlowStatementResponse
)


class CashFlowStatementService:
    """Service for generating Cash Flow Statements"""

    def __init__(self, db: Session):
        self.db = db

    def get_cash_flow_statement(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int] = None
    ) -> CashFlowStatementResponse:
        """
        Generate Cash Flow Statement using Indirect Method

        Args:
            start_date: Start of period
            end_date: End of period
            area_id: Location filter (None = consolidated)

        Returns:
            CashFlowStatementResponse with complete cash flow statement
        """
        # Get area name
        area_name = "All Locations"
        if area_id:
            area = self.db.query(Area).filter(Area.id == area_id).first()
            if area:
                area_name = area.name

        # Calculate net income from P&L
        net_income = self._calculate_net_income(start_date, end_date, area_id)

        # Operating Activities - Adjustments
        operating_adjustments = self._get_operating_adjustments(start_date, end_date, area_id)

        # Operating Activities - Working Capital Changes
        working_capital_changes = self._get_working_capital_changes(start_date, end_date, area_id)

        # Calculate net cash from operating
        total_adjustments = sum(item.amount for item in operating_adjustments)
        total_wc_changes = sum(item.amount for item in working_capital_changes)
        net_cash_from_operating = net_income + total_adjustments + total_wc_changes

        # Investing Activities
        investing_activities = self._get_investing_activities(start_date, end_date, area_id)
        net_cash_from_investing = sum(item.amount for item in investing_activities)

        # Financing Activities
        financing_activities = self._get_financing_activities(start_date, end_date, area_id)
        net_cash_from_financing = sum(item.amount for item in financing_activities)

        # Net increase in cash
        net_increase_in_cash = (
            net_cash_from_operating +
            net_cash_from_investing +
            net_cash_from_financing
        )

        # Get beginning and ending cash balances
        cash_beginning = self._get_cash_balance(start_date, area_id, is_beginning=True)
        cash_ending = self._get_cash_balance(end_date, area_id, is_beginning=False)

        return CashFlowStatementResponse(
            start_date=start_date,
            end_date=end_date,
            area_name=area_name,
            area_id=area_id,
            net_income=net_income,
            operating_adjustments=operating_adjustments,
            operating_working_capital_changes=working_capital_changes,
            net_cash_from_operating=net_cash_from_operating,
            investing_activities=investing_activities,
            net_cash_from_investing=net_cash_from_investing,
            financing_activities=financing_activities,
            net_cash_from_financing=net_cash_from_financing,
            net_increase_in_cash=net_increase_in_cash,
            cash_beginning_of_period=cash_beginning,
            cash_end_of_period=cash_ending
        )

    def _calculate_net_income(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> Decimal:
        """Calculate net income (Revenue - COGS - Expenses)"""
        # Revenue (credit balance)
        revenue = self._get_account_balance(
            AccountType.REVENUE,
            start_date,
            end_date,
            area_id,
            is_credit=True
        )

        # COGS (debit balance)
        cogs = self._get_account_balance(
            AccountType.COGS,
            start_date,
            end_date,
            area_id,
            is_credit=False
        )

        # Expenses (debit balance)
        expenses = self._get_account_balance(
            AccountType.EXPENSE,
            start_date,
            end_date,
            area_id,
            is_credit=False
        )

        return revenue - cogs - expenses

    def _get_operating_adjustments(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> List[CashFlowLineItem]:
        """
        Get adjustments to reconcile net income to cash from operations

        This includes non-cash expenses like:
        - Depreciation
        - Amortization
        - Bad debt expense
        """
        adjustments = []

        # Get all non-cash accounts
        non_cash_accounts = self.db.query(Account).filter(
            Account.cash_flow_class == CashFlowClass.NON_CASH,
            Account.is_active == True
        ).all()

        for account in non_cash_accounts:
            # Get net activity for this account
            amount = self._get_account_activity(
                account.id,
                start_date,
                end_date,
                area_id
            )

            if amount != 0:
                # Non-cash expenses are debits, so we add them back
                # (they reduced net income but didn't use cash)
                adjustments.append(CashFlowLineItem(
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=amount,
                    description=f"Add back {account.account_name.lower()}"
                ))

        return adjustments

    def _get_working_capital_changes(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> List[CashFlowLineItem]:
        """
        Get changes in working capital accounts

        Operating working capital accounts:
        - Accounts Receivable (asset - increase uses cash)
        - Inventory (asset - increase uses cash)
        - Prepaid Expenses (asset - increase uses cash)
        - Accounts Payable (liability - increase provides cash)
        - Accrued Expenses (liability - increase provides cash)
        """
        changes = []

        # Get all operating-classified accounts that aren't cash
        operating_accounts = self.db.query(Account).filter(
            Account.cash_flow_class == CashFlowClass.OPERATING,
            Account.is_active == True,
            or_(
                Account.account_type == AccountType.ASSET,
                Account.account_type == AccountType.LIABILITY
            )
        ).all()

        for account in operating_accounts:
            # Calculate change in account balance during period
            beginning_balance = self._get_account_balance_at_date(
                account.id,
                start_date,
                area_id,
                before_date=True
            )

            ending_balance = self._get_account_balance_at_date(
                account.id,
                end_date,
                area_id,
                before_date=False
            )

            change = ending_balance - beginning_balance

            if change != 0:
                # For assets: increase is negative (uses cash), decrease is positive (provides cash)
                # For liabilities: increase is positive (provides cash), decrease is negative (uses cash)
                if account.account_type == AccountType.ASSET:
                    cash_effect = -change
                else:  # LIABILITY
                    cash_effect = change

                changes.append(CashFlowLineItem(
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=cash_effect,
                    description=f"{'Increase' if change > 0 else 'Decrease'} in {account.account_name.lower()}"
                ))

        return changes

    def _get_investing_activities(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> List[CashFlowLineItem]:
        """
        Get investing activities

        This includes:
        - Purchase of fixed assets (uses cash - negative)
        - Sale of fixed assets (provides cash - positive)
        - Investments
        """
        activities = []

        # Get all investing-classified accounts
        investing_accounts = self.db.query(Account).filter(
            Account.cash_flow_class == CashFlowClass.INVESTING,
            Account.is_active == True
        ).all()

        for account in investing_accounts:
            # Calculate change in account balance during period
            beginning_balance = self._get_account_balance_at_date(
                account.id,
                start_date,
                area_id,
                before_date=True
            )

            ending_balance = self._get_account_balance_at_date(
                account.id,
                end_date,
                area_id,
                before_date=False
            )

            change = ending_balance - beginning_balance

            if change != 0:
                # For asset accounts: increase is negative (purchase - uses cash)
                #                     decrease is positive (sale - provides cash)
                cash_effect = -change if account.account_type == AccountType.ASSET else change

                activities.append(CashFlowLineItem(
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=cash_effect,
                    description=f"{'Purchase' if change > 0 else 'Sale'} of {account.account_name.lower()}"
                ))

        return activities

    def _get_financing_activities(
        self,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> List[CashFlowLineItem]:
        """
        Get financing activities

        This includes:
        - Loans received (provides cash - positive)
        - Loan payments (uses cash - negative)
        - Owner contributions (provides cash - positive)
        - Owner distributions (uses cash - negative)
        """
        activities = []

        # Get all financing-classified accounts
        financing_accounts = self.db.query(Account).filter(
            Account.cash_flow_class == CashFlowClass.FINANCING,
            Account.is_active == True
        ).all()

        for account in financing_accounts:
            # Calculate change in account balance during period
            beginning_balance = self._get_account_balance_at_date(
                account.id,
                start_date,
                area_id,
                before_date=True
            )

            ending_balance = self._get_account_balance_at_date(
                account.id,
                end_date,
                area_id,
                before_date=False
            )

            change = ending_balance - beginning_balance

            if change != 0:
                # For liabilities: increase is positive (new loan - provides cash)
                #                  decrease is negative (payment - uses cash)
                # For equity: increase is positive (contribution - provides cash)
                #             decrease is negative (distribution - uses cash)
                if account.account_type in [AccountType.LIABILITY, AccountType.EQUITY]:
                    cash_effect = change
                else:
                    cash_effect = -change

                activities.append(CashFlowLineItem(
                    account_number=account.account_number,
                    account_name=account.account_name,
                    amount=cash_effect,
                    description=self._get_financing_description(account, change)
                ))

        return activities

    def _get_financing_description(self, account: Account, change: Decimal) -> str:
        """Generate description for financing activity"""
        if account.account_type == AccountType.LIABILITY:
            if change > 0:
                return f"Proceeds from {account.account_name.lower()}"
            else:
                return f"Payment on {account.account_name.lower()}"
        else:  # EQUITY
            if change > 0:
                return f"Owner contribution - {account.account_name.lower()}"
            else:
                return f"Owner distribution - {account.account_name.lower()}"

    def _get_cash_balance(
        self,
        as_of_date: date,
        area_id: Optional[int],
        is_beginning: bool
    ) -> Decimal:
        """Get cash balance at a specific date"""
        # Get all cash accounts (account numbers starting with 1000)
        cash_accounts = self.db.query(Account).filter(
            Account.account_number.like('1000%'),
            Account.is_active == True
        ).all()

        total_cash = Decimal('0.00')
        for account in cash_accounts:
            balance = self._get_account_balance_at_date(
                account.id,
                as_of_date,
                area_id,
                before_date=is_beginning
            )
            total_cash += balance

        return total_cash

    def _get_account_balance(
        self,
        account_type: AccountType,
        start_date: date,
        end_date: date,
        area_id: Optional[int],
        is_credit: bool
    ) -> Decimal:
        """Get total balance for all accounts of a specific type within date range"""
        # Build query
        query = self.db.query(
            func.sum(JournalEntryLine.credit_amount if is_credit else JournalEntryLine.debit_amount).label('total')
        ).join(
            JournalEntry
        ).join(
            Account
        ).filter(
            Account.account_type == account_type,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        # Add area filter if specified
        if area_id is not None:
            query = query.filter(JournalEntryLine.area_id == area_id)

        result = query.scalar()
        return Decimal(str(result)) if result else Decimal('0.00')

    def _get_account_activity(
        self,
        account_id: int,
        start_date: date,
        end_date: date,
        area_id: Optional[int]
    ) -> Decimal:
        """Get net activity (debits - credits) for an account during a period"""
        # Build query for debits
        debit_query = self.db.query(
            func.sum(JournalEntryLine.debit_amount).label('total')
        ).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        # Build query for credits
        credit_query = self.db.query(
            func.sum(JournalEntryLine.credit_amount).label('total')
        ).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date
        )

        # Add area filter if specified
        if area_id is not None:
            debit_query = debit_query.filter(JournalEntryLine.area_id == area_id)
            credit_query = credit_query.filter(JournalEntryLine.area_id == area_id)

        debits = debit_query.scalar() or Decimal('0.00')
        credits = credit_query.scalar() or Decimal('0.00')

        return Decimal(str(debits)) - Decimal(str(credits))

    def _get_account_balance_at_date(
        self,
        account_id: int,
        as_of_date: date,
        area_id: Optional[int],
        before_date: bool = False
    ) -> Decimal:
        """
        Get account balance as of a specific date

        Args:
            account_id: Account to get balance for
            as_of_date: Date to calculate balance
            area_id: Location filter
            before_date: If True, get balance before this date (for beginning balance)
        """
        # Get account to determine normal balance
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return Decimal('0.00')

        # Build query for debits
        debit_query = self.db.query(
            func.sum(JournalEntryLine.debit_amount).label('total')
        ).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED
        )

        # Build query for credits
        credit_query = self.db.query(
            func.sum(JournalEntryLine.credit_amount).label('total')
        ).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED
        )

        # Add date filter
        if before_date:
            debit_query = debit_query.filter(JournalEntry.entry_date < as_of_date)
            credit_query = credit_query.filter(JournalEntry.entry_date < as_of_date)
        else:
            debit_query = debit_query.filter(JournalEntry.entry_date <= as_of_date)
            credit_query = credit_query.filter(JournalEntry.entry_date <= as_of_date)

        # Add area filter if specified
        if area_id is not None:
            debit_query = debit_query.filter(JournalEntryLine.area_id == area_id)
            credit_query = credit_query.filter(JournalEntryLine.area_id == area_id)

        debits = debit_query.scalar() or Decimal('0.00')
        credits = credit_query.scalar() or Decimal('0.00')

        # Calculate balance based on account type
        if account.account_type in [AccountType.ASSET, AccountType.EXPENSE, AccountType.COGS]:
            # Debit balance accounts
            return Decimal(str(debits)) - Decimal(str(credits))
        else:
            # Credit balance accounts (LIABILITY, EQUITY, REVENUE)
            return Decimal(str(credits)) - Decimal(str(debits))
