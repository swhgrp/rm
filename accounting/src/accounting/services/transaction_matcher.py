"""
Transaction Matching Engine
Matches bank transactions to journal entries using exact and fuzzy matching
"""
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta
from decimal import Decimal
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

try:
    from rapidfuzz import fuzz
except ImportError:
    logger.warning("rapidfuzz library not installed. Fuzzy matching will not be available.")
    fuzz = None

from accounting.models.bank_account import BankTransaction
from accounting.models.journal_entry import JournalEntryLine, JournalEntry

logger = logging.getLogger(__name__)


class TransactionMatcher:
    """Service for matching bank transactions to journal entries"""

    # Matching thresholds
    EXACT_MATCH_SCORE = 100.0
    FUZZY_THRESHOLD = 70.0  # Minimum score for fuzzy match
    DATE_WINDOW_DAYS = 7  # Days before/after to search for matches

    def __init__(self, db: Session):
        """Initialize matcher with database session"""
        self.db = db

    def find_matches(
        self,
        bank_transaction: BankTransaction,
        limit: int = 5
    ) -> List[Dict]:
        """
        Find potential matches for a bank transaction

        Args:
            bank_transaction: The bank transaction to match
            limit: Maximum number of matches to return

        Returns:
            List of match suggestions with scores
        """
        matches = []

        # Get unreconciled journal entry lines for the bank's GL account
        bank_account = bank_transaction.bank_account
        if not bank_account or not bank_account.gl_account_id:
            return matches

        # Date range for matching
        start_date = bank_transaction.transaction_date - timedelta(days=self.DATE_WINDOW_DAYS)
        end_date = bank_transaction.transaction_date + timedelta(days=self.DATE_WINDOW_DAYS)

        # Get candidate journal entry lines
        candidates = self.db.query(JournalEntryLine).join(JournalEntry).filter(
            and_(
                JournalEntryLine.account_id == bank_account.gl_account_id,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
                JournalEntry.status == "POSTED",
                JournalEntryLine.id.notin_(
                    self.db.query(BankTransaction.matched_journal_line_id).filter(
                        BankTransaction.matched_journal_line_id.isnot(None)
                    )
                )
            )
        ).all()

        # Score each candidate
        for candidate in candidates:
            score = self._calculate_match_score(bank_transaction, candidate)

            if score >= self.FUZZY_THRESHOLD:
                # Calculate journal amount safely
                journal_amt = (candidate.debit_amount or 0) if (candidate.debit_amount or 0) > 0 else (candidate.credit_amount or 0) * -1

                match_info = {
                    "bank_transaction_id": bank_transaction.id,
                    "journal_line_id": candidate.id,
                    "journal_entry_id": candidate.journal_entry_id,
                    "entry_date": candidate.journal_entry.entry_date,
                    "description": candidate.journal_entry.description,
                    "amount": journal_amt,
                    "match_score": score,
                    "match_reason": self._get_match_reason(bank_transaction, candidate, score),
                    "amount_difference": abs(bank_transaction.amount - journal_amt),
                    "date_difference": abs((bank_transaction.transaction_date - candidate.journal_entry.entry_date).days)
                }
                matches.append(match_info)

        # Sort by score (highest first) and limit
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches[:limit]

    def _calculate_match_score(
        self,
        bank_txn: BankTransaction,
        journal_line: JournalEntryLine
    ) -> Decimal:
        """Calculate match score between bank transaction and journal line"""
        score = Decimal("0.0")
        max_score = Decimal("100.0")

        # Amount matching (40 points)
        bank_amount = abs(bank_txn.amount)
        journal_amount = journal_line.debit_amount if (journal_line.debit_amount or 0) > 0 else (journal_line.credit_amount or 0)

        if bank_amount == journal_amount:
            score += Decimal("40.0")
        else:
            # Partial points for close amounts
            difference = abs(bank_amount - journal_amount)
            if difference <= Decimal("0.01"):
                score += Decimal("39.0")
            elif difference <= bank_amount * Decimal("0.01"):  # Within 1%
                score += Decimal("35.0")
            elif difference <= bank_amount * Decimal("0.05"):  # Within 5%
                score += Decimal("25.0")

        # Date matching (30 points)
        date_diff = abs((bank_txn.transaction_date - journal_line.journal_entry.entry_date).days)
        if date_diff == 0:
            score += Decimal("30.0")
        elif date_diff <= 1:
            score += Decimal("25.0")
        elif date_diff <= 3:
            score += Decimal("20.0")
        elif date_diff <= 7:
            score += Decimal("15.0")

        # Description matching (30 points) - using fuzzy match if available
        if fuzz and bank_txn.description and journal_line.journal_entry.description:
            desc_score = fuzz.token_set_ratio(
                bank_txn.description.lower(),
                journal_line.journal_entry.description.lower()
            )
            score += Decimal(str(desc_score)) * Decimal("0.3")  # Scale to 30 points

        # Check number matching (bonus 10 points)
        # Note: JournalEntry model doesn't have a direct 'reference' field
        # so we skip this check for now
        # if bank_txn.check_number:
        #     # Could match against entry_number or description
        #     pass

        return min(score, max_score)

    def _get_match_reason(
        self,
        bank_txn: BankTransaction,
        journal_line: JournalEntryLine,
        score: Decimal
    ) -> str:
        """Get human-readable explanation for the match"""
        reasons = []

        # Check amount
        bank_amount = abs(bank_txn.amount)
        journal_amount = (journal_line.debit_amount or 0) if (journal_line.debit_amount or 0) > 0 else (journal_line.credit_amount or 0)

        if bank_amount == journal_amount:
            reasons.append("Exact amount match")
        else:
            diff = abs(bank_amount - journal_amount)
            reasons.append(f"Amount close (${diff:.2f} difference)")

        # Check date
        date_diff = abs((bank_txn.transaction_date - journal_line.journal_entry.entry_date).days)
        if date_diff == 0:
            reasons.append("Same date")
        elif date_diff <= 3:
            reasons.append(f"Date within {date_diff} days")

        # Check description similarity
        if fuzz and bank_txn.description and journal_line.journal_entry.description:
            desc_score = fuzz.token_set_ratio(
                bank_txn.description.lower(),
                journal_line.journal_entry.description.lower()
            )
            if desc_score >= 80:
                reasons.append("Description similar")

        # Check check number
        # Note: JournalEntry doesn't have a 'reference' field, skipping for now
        # if bank_txn.check_number:
        #     reasons.append("Check number present")

        if score >= 95:
            return "High confidence: " + ", ".join(reasons)
        elif score >= 80:
            return "Good match: " + ", ".join(reasons)
        else:
            return "Possible match: " + ", ".join(reasons)

    def auto_match_transactions(
        self,
        bank_account_id: int,
        confidence_threshold: Decimal = Decimal("95.0")
    ) -> Dict:
        """
        Automatically match high-confidence transactions

        Args:
            bank_account_id: Bank account ID
            confidence_threshold: Minimum score for auto-matching (default 95%)

        Returns:
            Dict with match statistics
        """
        matched_count = 0
        skipped_count = 0

        # Get unmatched bank transactions
        unmatched = self.db.query(BankTransaction).filter(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.status == "unreconciled",
                BankTransaction.matched_journal_line_id.is_(None)
            )
        ).all()

        for bank_txn in unmatched:
            matches = self.find_matches(bank_txn, limit=1)

            if matches and matches[0]["match_score"] >= confidence_threshold:
                # Auto-match with highest score
                best_match = matches[0]
                bank_txn.matched_journal_line_id = best_match["journal_line_id"]
                bank_txn.matched_journal_entry_id = best_match["journal_entry_id"]
                bank_txn.match_type = "auto"
                bank_txn.match_confidence = best_match["match_score"]
                matched_count += 1
            else:
                skipped_count += 1

        self.db.commit()

        return {
            "matched": matched_count,
            "skipped": skipped_count,
            "total": len(unmatched)
        }

    def match_transaction(
        self,
        bank_transaction_id: int,
        journal_line_id: int,
        match_type: str = "manual"
    ) -> bool:
        """
        Manually match a bank transaction to a journal line

        Args:
            bank_transaction_id: Bank transaction ID
            journal_line_id: Journal entry line ID
            match_type: Type of match (manual, exact, fuzzy, auto)

        Returns:
            True if successful
        """
        try:
            bank_txn = self.db.query(BankTransaction).filter(
                BankTransaction.id == bank_transaction_id
            ).first()

            journal_line = self.db.query(JournalEntryLine).filter(
                JournalEntryLine.id == journal_line_id
            ).first()

            if not bank_txn or not journal_line:
                return False

            # Calculate confidence score
            score = self._calculate_match_score(bank_txn, journal_line)

            bank_txn.matched_journal_line_id = journal_line_id
            bank_txn.matched_journal_entry_id = journal_line.journal_entry_id
            bank_txn.match_type = match_type
            bank_txn.match_confidence = score

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error matching transaction: {str(e)}")
            self.db.rollback()
            return False

    def unmatch_transaction(self, bank_transaction_id: int) -> bool:
        """
        Remove match from a bank transaction

        Args:
            bank_transaction_id: Bank transaction ID

        Returns:
            True if successful
        """
        try:
            bank_txn = self.db.query(BankTransaction).filter(
                BankTransaction.id == bank_transaction_id
            ).first()

            if not bank_txn:
                return False

            bank_txn.matched_journal_line_id = None
            bank_txn.matched_journal_entry_id = None
            bank_txn.match_type = None
            bank_txn.match_confidence = None

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error unmatching transaction: {str(e)}")
            self.db.rollback()
            return False

    def get_unmatched_transactions(
        self,
        bank_account_id: int,
        limit: Optional[int] = None
    ) -> List[BankTransaction]:
        """Get list of unmatched transactions for a bank account"""
        query = self.db.query(BankTransaction).filter(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.status == "unreconciled",
                BankTransaction.matched_journal_line_id.is_(None)
            )
        ).order_by(BankTransaction.transaction_date.desc())

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_matching_statistics(self, bank_account_id: int) -> Dict:
        """Get matching statistics for a bank account"""
        total = self.db.query(BankTransaction).filter(
            BankTransaction.bank_account_id == bank_account_id
        ).count()

        matched = self.db.query(BankTransaction).filter(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.matched_journal_line_id.isnot(None)
            )
        ).count()

        auto_matched = self.db.query(BankTransaction).filter(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.match_type == "auto"
            )
        ).count()

        return {
            "total_transactions": total,
            "matched": matched,
            "unmatched": total - matched,
            "match_rate": (matched / total * 100) if total > 0 else 0,
            "auto_matched": auto_matched
        }
