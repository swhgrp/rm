"""
Bank transaction matching service

Handles composite matching for bank reconciliation:
- Tier 0: Exact match (amount + date)
- Tier 1: Fuzzy match (amount + date window ±3 days)
- Tier 2: Composite match (many GL entries → one bank deposit)
- Fee calculation for credit card batches and delivery platforms
"""
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import uuid

from accounting.models.bank_account import (
    BankTransaction,
    BankTransactionMatch,
    BankCompositeMatch,
    BankMatchingRuleV2
)
from accounting.models.journal_entry import JournalEntryLine
from accounting.models.account import Account


class MatchSuggestion:
    """Represents a suggested match for a bank transaction"""

    def __init__(
        self,
        match_type: str,
        confidence_score: float,
        match_reason: str,
        journal_entry_lines: List[JournalEntryLine] = None,
        amount_difference: Decimal = Decimal("0"),
        date_difference: int = 0,
        suggested_fee_account_id: Optional[int] = None,
        suggested_fee_amount: Optional[Decimal] = None,
        composite_group_id: Optional[str] = None
    ):
        self.match_type = match_type
        self.confidence_score = confidence_score
        self.match_reason = match_reason
        self.journal_entry_lines = journal_entry_lines or []
        self.amount_difference = amount_difference
        self.date_difference = date_difference
        self.suggested_fee_account_id = suggested_fee_account_id
        self.suggested_fee_amount = suggested_fee_amount
        self.composite_group_id = composite_group_id or str(uuid.uuid4())


class BankMatchingService:
    """Service for matching bank transactions to GL entries"""

    def __init__(self, db: Session):
        self.db = db

    def suggest_matches(
        self,
        bank_transaction: BankTransaction,
        date_window_days: int = 7,
        amount_tolerance_percent: float = 5.0
    ) -> List[MatchSuggestion]:
        """
        Find all possible matches for a bank transaction

        Returns suggestions in order of confidence (highest first)
        """
        suggestions = []

        # Tier 0: Exact match
        exact_matches = self._find_exact_matches(bank_transaction)
        suggestions.extend(exact_matches)

        # Tier 1: Fuzzy match (date window)
        if not exact_matches:
            fuzzy_matches = self._find_fuzzy_matches(
                bank_transaction,
                date_window_days=date_window_days
            )
            suggestions.extend(fuzzy_matches)

        # Tier 2: Composite match (many-to-one)
        if bank_transaction.amount > 0:  # Only for deposits
            composite_matches = self._find_composite_matches(
                bank_transaction,
                date_window_days=date_window_days,
                amount_tolerance_percent=amount_tolerance_percent
            )
            suggestions.extend(composite_matches)

        # Rule-based matching (for expenses)
        if bank_transaction.amount < 0:  # Only for withdrawals
            rule_matches = self._find_rule_based_matches(bank_transaction)
            suggestions.extend(rule_matches)

        # Sort by confidence score (highest first)
        suggestions.sort(key=lambda s: s.confidence_score, reverse=True)

        return suggestions

    def _find_exact_matches(
        self,
        bank_transaction: BankTransaction
    ) -> List[MatchSuggestion]:
        """Tier 0: Exact amount and date match"""
        suggestions = []

        # Find uncleared journal entry lines matching amount and date
        je_lines = self.db.query(JournalEntryLine).join(
            JournalEntryLine.journal_entry
        ).filter(
            and_(
                JournalEntryLine.account_id.in_(
                    self._get_undeposited_funds_account_ids()
                ),
                or_(
                    # For deposits: match debit amounts
                    and_(
                        bank_transaction.amount > 0,
                        JournalEntryLine.debit_amount == abs(bank_transaction.amount)
                    ),
                    # For withdrawals: match credit amounts
                    and_(
                        bank_transaction.amount < 0,
                        JournalEntryLine.credit_amount == abs(bank_transaction.amount)
                    )
                ),
                # Date match
                JournalEntryLine.journal_entry.has(
                    entry_date=bank_transaction.transaction_date
                ),
                # Not already matched
                ~JournalEntryLine.id.in_(
                    self.db.query(BankTransactionMatch.journal_entry_line_id).filter(
                        BankTransactionMatch.status.in_(['confirmed', 'cleared'])
                    )
                )
            )
        ).limit(10).all()

        for je_line in je_lines:
            suggestions.append(MatchSuggestion(
                match_type='exact',
                confidence_score=100.0,
                match_reason=f'Exact amount and date match to {je_line.account.code} {je_line.account.name}',
                journal_entry_lines=[je_line],
                amount_difference=Decimal("0"),
                date_difference=0
            ))

        return suggestions

    def _find_fuzzy_matches(
        self,
        bank_transaction: BankTransaction,
        date_window_days: int = 7
    ) -> List[MatchSuggestion]:
        """Tier 1: Amount match with date window"""
        suggestions = []

        date_start = bank_transaction.transaction_date - timedelta(days=date_window_days)
        date_end = bank_transaction.transaction_date + timedelta(days=date_window_days)

        je_lines = self.db.query(JournalEntryLine).join(
            JournalEntryLine.journal_entry
        ).filter(
            and_(
                JournalEntryLine.account_id.in_(
                    self._get_undeposited_funds_account_ids()
                ),
                or_(
                    # For deposits: match debit amounts
                    and_(
                        bank_transaction.amount > 0,
                        JournalEntryLine.debit_amount == abs(bank_transaction.amount)
                    ),
                    # For withdrawals: match credit amounts
                    and_(
                        bank_transaction.amount < 0,
                        JournalEntryLine.credit_amount == abs(bank_transaction.amount)
                    )
                ),
                # Date window
                JournalEntryLine.journal_entry.has(
                    and_(
                        JournalEntryLine.journal_entry.c.entry_date >= date_start,
                        JournalEntryLine.journal_entry.c.entry_date <= date_end
                    )
                ),
                # Not already matched
                ~JournalEntryLine.id.in_(
                    self.db.query(BankTransactionMatch.journal_entry_line_id).filter(
                        BankTransactionMatch.status.in_(['confirmed', 'cleared'])
                    )
                )
            )
        ).limit(10).all()

        for je_line in je_lines:
            date_diff = abs((je_line.journal_entry.entry_date - bank_transaction.transaction_date).days)

            # Confidence decreases with date difference
            confidence = 95.0 - (date_diff * 5.0)  # -5% per day difference
            confidence = max(confidence, 50.0)  # Minimum 50%

            suggestions.append(MatchSuggestion(
                match_type='fuzzy',
                confidence_score=confidence,
                match_reason=f'Amount match with {date_diff} day date difference to {je_line.account.code} {je_line.account.name}',
                journal_entry_lines=[je_line],
                amount_difference=Decimal("0"),
                date_difference=date_diff
            ))

        return suggestions

    def _find_composite_matches(
        self,
        bank_transaction: BankTransaction,
        date_window_days: int = 7,
        amount_tolerance_percent: float = 5.0
    ) -> List[MatchSuggestion]:
        """
        Tier 2: Composite matching (many GL entries → one bank deposit)

        This handles scenarios like:
        - Credit card batches (3 days of CC sales → 1 bank deposit) - EXACT match expected
        - Multiple cash deposits → 1 bank transaction - Small variance allowed
        - Third-party delivery deposits → User handles commission manually

        NOTE: Credit card processors deposit FULL amount (fees charged monthly)
        """
        suggestions = []

        # Only for deposits
        if bank_transaction.amount <= 0:
            return suggestions

        bank_amount = abs(bank_transaction.amount)

        # Find uncleared Undeposited Funds entries within date window
        date_start = bank_transaction.transaction_date - timedelta(days=date_window_days)

        je_lines = self.db.query(JournalEntryLine).join(
            JournalEntryLine.journal_entry
        ).filter(
            and_(
                JournalEntryLine.account_id.in_(
                    self._get_undeposited_funds_account_ids()
                ),
                JournalEntryLine.debit_amount > 0,  # Debits to Undeposited Funds
                # Date before or on bank transaction date
                JournalEntryLine.journal_entry.has(
                    and_(
                        JournalEntryLine.journal_entry.c.entry_date >= date_start,
                        JournalEntryLine.journal_entry.c.entry_date <= bank_transaction.transaction_date
                    )
                ),
                # Not already matched
                ~JournalEntryLine.id.in_(
                    self.db.query(BankTransactionMatch.journal_entry_line_id).filter(
                        BankTransactionMatch.status.in_(['confirmed', 'cleared'])
                    )
                )
            )
        ).order_by(JournalEntryLine.journal_entry.c.entry_date).all()

        if not je_lines:
            return suggestions

        # Try to find combinations that match the bank amount
        best_combinations = self._find_best_combinations(
            je_lines,
            bank_amount,
            tolerance_percent=amount_tolerance_percent
        )

        for combination, total_amount, fee_amount in best_combinations[:3]:  # Top 3 matches
            date_diff = abs((combination[-1].journal_entry.entry_date - bank_transaction.transaction_date).days)

            # Calculate confidence
            amount_diff_percent = abs(float((total_amount - bank_amount) / bank_amount * 100))
            fee_percent = abs(float(fee_amount / total_amount * 100)) if total_amount > 0 else 0

            confidence = 95.0
            confidence -= date_diff * 2.0  # -2% per day
            confidence -= amount_diff_percent * 5.0  # -5% per 1% difference

            # Bonus for exact matches (credit card deposits should be exact)
            if fee_amount == 0:
                confidence += 4.0  # Exact match bonus

            confidence = max(min(confidence, 99.0), 50.0)  # Clamp between 50-99%

            # Determine fee account and whether to suggest adjustment
            fee_account_id = None
            suggest_fee_adjustment = False

            if combination[0].account_id:
                account_code = combination[0].account.code

                # Cash deposits: suggest adjustment for cash over/short
                if account_code == "1091" and abs(fee_amount) > Decimal("0.10"):
                    fee_account_id = self._get_account_id_by_code("6999")  # Cash Over/Short
                    suggest_fee_adjustment = True

                # Credit Card / Third Party: DO NOT suggest fee adjustment
                # User handles these manually (CC fees are monthly, delivery commissions vary)

            # Build match reason
            match_reason = f'Composite match: {len(combination)} transactions totaling ${total_amount:.2f}'

            if fee_amount == 0:
                match_reason += ' (exact match)'
            elif suggest_fee_adjustment:
                match_reason += f' with ${abs(fee_amount):.2f} cash {"over" if fee_amount < 0 else "short"}'
            elif abs(fee_amount) > 0:
                match_reason += f' (${abs(fee_amount):.2f} difference - review manually)'

            suggestions.append(MatchSuggestion(
                match_type='composite',
                confidence_score=confidence,
                match_reason=match_reason,
                journal_entry_lines=combination,
                amount_difference=fee_amount if suggest_fee_adjustment else Decimal("0"),
                date_difference=date_diff,
                suggested_fee_account_id=fee_account_id if suggest_fee_adjustment else None,
                suggested_fee_amount=abs(fee_amount) if suggest_fee_adjustment else None
            ))

        return suggestions

    def _find_best_combinations(
        self,
        je_lines: List[JournalEntryLine],
        target_amount: Decimal,
        tolerance_percent: float = 5.0
    ) -> List[Tuple[List[JournalEntryLine], Decimal, Decimal]]:
        """
        Find the best combinations of journal entry lines that match target amount

        Returns: List of (combination, total_amount, fee_amount) tuples

        Tolerance by account type:
        - Credit Card (1090): Very tight tolerance (0.1%) - expect exact match
        - Cash (1091): Moderate tolerance (0.5%) - allow cash over/short
        - Third Party (1095): Wider tolerance (5%) - commissions vary
        """
        results = []

        # Adjust tolerance based on account type
        if je_lines and je_lines[0].account_id:
            account_code = je_lines[0].account.code
            if account_code == "1090":  # Credit Card - expect exact match
                tolerance = Decimal("0.50")  # $0.50 tolerance max
            elif account_code == "1091":  # Cash - allow over/short
                tolerance = target_amount * Decimal("0.005")  # 0.5%
                tolerance = max(tolerance, Decimal("1.00"))  # At least $1
            elif account_code == "1095":  # Third Party - commissions vary
                tolerance = target_amount * Decimal(str(tolerance_percent / 100))
            else:
                tolerance = target_amount * Decimal("0.01")  # 1% default
        else:
            tolerance = target_amount * Decimal(str(tolerance_percent / 100))

        # Try single entry first
        for je_line in je_lines:
            amount = je_line.debit_amount
            if abs(amount - target_amount) <= tolerance:
                fee = amount - target_amount
                results.append(([je_line], amount, fee))

        # Try combinations of 2-7 entries (most credit card batches are weekly)
        for combo_size in range(2, min(8, len(je_lines) + 1)):
            self._try_combinations(
                je_lines,
                combo_size,
                target_amount,
                tolerance,
                results
            )

        # Sort by how close to target (lowest fee)
        results.sort(key=lambda x: abs(x[2]))

        return results[:5]  # Return top 5 matches

    def _try_combinations(
        self,
        je_lines: List[JournalEntryLine],
        combo_size: int,
        target_amount: Decimal,
        tolerance: Decimal,
        results: List
    ):
        """Try all combinations of given size"""
        from itertools import combinations

        for combo in combinations(je_lines, combo_size):
            total = sum(je.debit_amount for je in combo)
            if abs(total - target_amount) <= tolerance:
                fee = total - target_amount
                results.append((list(combo), total, fee))

    def _find_rule_based_matches(
        self,
        bank_transaction: BankTransaction
    ) -> List[MatchSuggestion]:
        """Find matches based on user-defined rules"""
        suggestions = []

        # Get active rules for this bank account
        rules = self.db.query(BankMatchingRuleV2).filter(
            and_(
                or_(
                    BankMatchingRuleV2.bank_account_id == bank_transaction.bank_account_id,
                    BankMatchingRuleV2.bank_account_id.is_(None)  # Global rules
                ),
                BankMatchingRuleV2.active == True
            )
        ).order_by(BankMatchingRuleV2.priority.desc()).all()

        for rule in rules:
            if self._rule_matches_transaction(rule, bank_transaction):
                confidence = 80.0  # Base confidence for rule matches

                # Increase confidence based on rule usage statistics
                if rule.times_confirmed > 0:
                    success_rate = (rule.times_confirmed / rule.times_suggested * 100)
                    confidence = min(85.0 + (success_rate * 0.1), 95.0)

                match_reason = f'Rule: {rule.rule_name}'
                if rule.notes:
                    match_reason += f' - {rule.notes}'

                suggestions.append(MatchSuggestion(
                    match_type='rule_based',
                    confidence_score=confidence,
                    match_reason=match_reason,
                    journal_entry_lines=[],  # No GL match, will create expense
                    amount_difference=Decimal("0"),
                    date_difference=0,
                    suggested_fee_account_id=rule.target_account_id
                ))

                # Update rule statistics
                rule.times_suggested += 1
                rule.last_used_at = self.db.execute("SELECT CURRENT_TIMESTAMP").scalar()
                self.db.commit()

                break  # Only use first matching rule (highest priority)

        return suggestions

    def _rule_matches_transaction(
        self,
        rule: BankMatchingRuleV2,
        transaction: BankTransaction
    ) -> bool:
        """Check if a rule's conditions match a transaction"""
        conditions = rule.conditions

        # Check description contains
        if 'description_contains' in conditions:
            if not transaction.description:
                return False
            search_term = conditions['description_contains'].upper()
            if search_term not in transaction.description.upper():
                return False

        # Check description starts with
        if 'description_starts_with' in conditions:
            if not transaction.description:
                return False
            prefix = conditions['description_starts_with'].upper()
            if not transaction.description.upper().startswith(prefix):
                return False

        # Check amount range
        if 'amount_min' in conditions:
            if abs(transaction.amount) < Decimal(str(conditions['amount_min'])):
                return False

        if 'amount_max' in conditions:
            if abs(transaction.amount) > Decimal(str(conditions['amount_max'])):
                return False

        # Check amount equals
        if 'amount_equals' in conditions:
            if abs(transaction.amount) != Decimal(str(conditions['amount_equals'])):
                return False

        # Check transaction type
        if 'transaction_type' in conditions:
            if transaction.transaction_type != conditions['transaction_type']:
                return False

        # All conditions passed
        return True

    def _get_undeposited_funds_account_ids(self) -> List[int]:
        """Get IDs of Undeposited Funds accounts"""
        accounts = self.db.query(Account.id).filter(
            Account.code.in_(['1090', '1091', '1095'])  # Undeposited CC, Cash, Third Party
        ).all()
        return [acc.id for acc in accounts]

    def _get_account_id_by_code(self, code: str) -> Optional[int]:
        """Get account ID by account code"""
        account = self.db.query(Account).filter(Account.code == code).first()
        return account.id if account else None

    def confirm_match(
        self,
        bank_transaction: BankTransaction,
        suggestion: MatchSuggestion,
        confirmed_by_user_id: int
    ) -> BankTransactionMatch:
        """
        Confirm a suggested match

        Creates BankTransactionMatch record and optionally BankCompositeMatch records
        """
        # Create main match record
        match = BankTransactionMatch(
            bank_transaction_id=bank_transaction.id,
            match_type=suggestion.match_type,
            confidence_score=suggestion.confidence_score,
            match_reason=suggestion.match_reason,
            amount_difference=suggestion.amount_difference,
            date_difference=suggestion.date_difference,
            confirmed_by=confirmed_by_user_id,
            status='confirmed'
        )

        if suggestion.match_type == 'composite':
            # Create composite match records
            for je_line in suggestion.journal_entry_lines:
                composite_match = BankCompositeMatch(
                    match_group_id=suggestion.composite_group_id,
                    bank_transaction_id=bank_transaction.id,
                    journal_entry_line_id=je_line.id,
                    match_amount=je_line.debit_amount,
                    composite_type='many_to_one',
                    confirmed_by=confirmed_by_user_id,
                    status='confirmed'
                )
                self.db.add(composite_match)

            # Set the first JE line as the primary match
            if suggestion.journal_entry_lines:
                match.journal_entry_line_id = suggestion.journal_entry_lines[0].id

        elif suggestion.journal_entry_lines:
            # Simple 1-to-1 match
            match.journal_entry_line_id = suggestion.journal_entry_lines[0].id

        self.db.add(match)

        # Update bank transaction
        bank_transaction.status = 'reconciled'
        bank_transaction.reconciled_date = bank_transaction.transaction_date
        if suggestion.journal_entry_lines:
            bank_transaction.matched_journal_line_id = suggestion.journal_entry_lines[0].id

        self.db.commit()
        self.db.refresh(match)

        return match
