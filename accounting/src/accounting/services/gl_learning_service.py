"""Service for GL learning and intelligent suggestions"""
import re
from typing import List, Optional, Dict
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from accounting.models.gl_learning import VendorGLMapping, DescriptionPatternMapping, RecurringTransactionPattern
from accounting.models.account import Account
from accounting.models.bank_account import BankTransaction
from accounting.schemas.gl_suggestion import GLSuggestion
from datetime import date, timedelta


class GLLearningService:
    """Service for learning GL assignments and providing intelligent suggestions"""

    def __init__(self, db: Session):
        self.db = db

    def get_suggestions_for_transaction(
        self,
        transaction_id: int,
        description: str,
        amount: Decimal,
        vendor_id: Optional[int] = None,
        transaction_date: Optional[date] = None
    ) -> List[GLSuggestion]:
        """
        Get GL account suggestions for a transaction (Phase 2 Enhanced).

        Returns suggestions in priority order:
        1. Recurring transaction match (if detected)
        2. Vendor-based with amount similarity (if vendor recognized)
        3. Pattern-based with amount similarity (from description)
        4. Amount-range based suggestions
        """
        suggestions = []
        amount_abs = abs(float(amount))

        # 1. Check for recurring transaction patterns (Phase 2)
        recurring_suggestions = self._get_recurring_suggestions(description, amount_abs, vendor_id, transaction_date)
        suggestions.extend(recurring_suggestions)

        # 2. Vendor-based suggestions with amount filtering (Phase 2)
        if vendor_id:
            vendor_suggestions = self._get_vendor_suggestions(vendor_id, amount_abs)
            suggestions.extend(vendor_suggestions)

        # 3. Pattern-based suggestions with amount filtering (Phase 2)
        pattern_suggestions = self._get_pattern_suggestions(description, amount_abs)
        suggestions.extend(pattern_suggestions)

        # 4. Deduplicate and sort by confidence
        suggestions = self._deduplicate_suggestions(suggestions)
        suggestions.sort(key=lambda x: x.confidence_score, reverse=True)

        # Return top 5 suggestions
        return suggestions[:5]

    def _get_vendor_suggestions(self, vendor_id: int, amount: Optional[float] = None) -> List[GLSuggestion]:
        """Get GL suggestions based on vendor history (Phase 2: with amount filtering)"""
        mappings = self.db.query(VendorGLMapping).filter(
            VendorGLMapping.vendor_id == vendor_id
        ).all()

        suggestions = []
        for mapping in mappings:
            # Calculate base confidence
            confidence = mapping.calculate_confidence()

            # Phase 2: Boost confidence if amount is within expected range
            if amount and mapping.avg_amount:
                amount_diff_pct = abs(amount - float(mapping.avg_amount)) / float(mapping.avg_amount) * 100
                if amount_diff_pct < 10:  # Within 10% of average
                    confidence = min(confidence + 15, 100)  # Boost confidence
                    amount_match = True
                elif amount_diff_pct > 50:  # More than 50% different
                    confidence = max(confidence - 10, 10)  # Lower confidence
                    amount_match = False
                else:
                    amount_match = None
            else:
                amount_match = None

            # Get account details
            account = self.db.query(Account).filter(Account.id == mapping.account_id).first()
            if not account:
                continue

            # Create reason (Phase 2: include amount info)
            if mapping.times_accepted > 0:
                reason = f"Used {mapping.times_used} times for this vendor, accepted {mapping.times_accepted} times"
            else:
                reason = f"Previously used {mapping.times_used} times for this vendor"

            if amount_match == True:
                reason += " (amount matches pattern)"
            elif amount_match == False:
                reason += " (unusual amount)"

            suggestions.append(GLSuggestion(
                account_id=account.id,
                account_number=account.account_number,
                account_name=account.account_name,
                confidence_score=Decimal(str(confidence)),
                suggestion_type='vendor',
                reason=reason,
                times_used=mapping.times_used
            ))

        return suggestions

    def _get_pattern_suggestions(self, description: str, amount: Optional[float] = None) -> List[GLSuggestion]:
        """Get GL suggestions based on description patterns (Phase 2: with amount filtering)"""
        if not description:
            return []

        # Extract keywords from description
        keywords = self._extract_keywords(description)

        # Find matching patterns
        suggestions = []
        for keyword in keywords:
            mappings = self.db.query(DescriptionPatternMapping).filter(
                or_(
                    DescriptionPatternMapping.pattern.ilike(f'%{keyword}%'),
                    DescriptionPatternMapping.pattern == keyword.upper()
                )
            ).all()

            for mapping in mappings:
                # Calculate confidence
                confidence = mapping.calculate_confidence()

                # Get account details
                account = self.db.query(Account).filter(Account.id == mapping.account_id).first()
                if not account:
                    continue

                # Create reason
                if mapping.times_accepted > 0:
                    reason = f"Pattern '{mapping.pattern}' matched, accepted {mapping.times_accepted}/{mapping.times_used} times"
                else:
                    reason = f"Pattern '{mapping.pattern}' matched ({mapping.times_used} uses)"

                suggestions.append(GLSuggestion(
                    account_id=account.id,
                    account_number=account.account_number,
                    account_name=account.account_name,
                    confidence_score=Decimal(str(confidence)),
                    suggestion_type='pattern',
                    reason=reason,
                    times_used=mapping.times_used
                ))

        return suggestions

    def _get_recurring_suggestions(
        self,
        description: str,
        amount: float,
        vendor_id: Optional[int] = None,
        transaction_date: Optional[date] = None
    ) -> List[GLSuggestion]:
        """Get suggestions based on recurring transaction patterns (Phase 2)"""
        suggestions = []

        # Find recurring patterns that match
        query = self.db.query(RecurringTransactionPattern).filter(
            RecurringTransactionPattern.is_active == True
        )

        # Filter by vendor if provided
        if vendor_id:
            query = query.filter(RecurringTransactionPattern.vendor_id == vendor_id)

        # Filter by description pattern (fuzzy match)
        if description:
            keywords = self._extract_keywords(description)
            for keyword in keywords[:2]:  # Check top 2 keywords
                query = query.filter(RecurringTransactionPattern.description_pattern.ilike(f'%{keyword}%'))

        recurring_patterns = query.all()

        for pattern in recurring_patterns:
            # Check if amount is within expected range
            amount_matches = False
            if pattern.expected_amount:
                amount_diff = abs(amount - float(pattern.expected_amount))
                amount_matches = amount_diff <= float(pattern.amount_variance or 0)

            # Check if transaction is due (if date provided)
            is_due = pattern.is_due_soon(transaction_date) if transaction_date else False

            # Calculate confidence
            confidence = pattern.calculate_confidence()

            # Boost confidence if amount matches and is due
            if amount_matches:
                confidence = min(confidence + 20, 100)
            if is_due:
                confidence = min(confidence + 15, 100)

            # Get account details
            account = self.db.query(Account).filter(Account.id == pattern.account_id).first()
            if not account:
                continue

            # Create reason
            reason_parts = [f"Recurring ({pattern.occurrence_count} times)"]
            if is_due:
                reason_parts.append("due soon")
            if amount_matches:
                reason_parts.append(f"amount matches ${pattern.expected_amount}")

            suggestions.append(GLSuggestion(
                account_id=account.id,
                account_number=account.account_number,
                account_name=account.account_name,
                confidence_score=Decimal(str(confidence)),
                suggestion_type='recurring',
                reason=", ".join(reason_parts),
                times_used=pattern.occurrence_count
            ))

        return suggestions

    def _extract_keywords(self, description: str) -> List[str]:
        """Extract keywords from transaction description"""
        if not description:
            return []

        # Convert to uppercase for consistency
        desc_upper = description.upper()

        # Common transaction keywords to extract
        keywords = []

        # Known patterns — more specific patterns listed FIRST so they match before generic ones
        patterns = {
            'MERCHANT BANKCD': 'MERCHANT BANKCD',
            'MERCHANT': 'MERCHANT',
            'CASH DEPOSIT': 'CASH DEPOSIT',
            'INTEREST': 'INTEREST',
            'FEE': 'FEE',
            'MAINTENANCE FEE': 'MAINTENANCE FEE',
            'MAINTENANCE': 'MAINTENANCE',
            'ATM': 'ATM',
            'DEBIT CARD': 'DEBIT CARD',
            'CREDIT CARD': 'CREDIT CARD',
            'ACH DEBIT': 'ACH DEBIT',
            'ACH CREDIT': 'ACH CREDIT',
            'CHECK': 'CHECK',
            'DEPOSIT': 'DEPOSIT',
            'WITHDRAWAL': 'WITHDRAWAL',
            'TRANSFER': 'TRANSFER',
            'PAYMENT': 'PAYMENT',
            'REFUND': 'REFUND',
            'WIRE': 'WIRE',
            'PAYROLL': 'PAYROLL',
            'TAX': 'TAX',
            'LOAN': 'LOAN',
            'INSURANCE': 'INSURANCE',
        }

        for pattern, keyword in patterns.items():
            if pattern in desc_upper:
                keywords.append(keyword)

        # Extract vendor-like names (sequences of capital letters)
        # e.g., "AT&T", "SYSCO", "CHEVRON"
        # Filter out common banking noise words
        stop_words = {
            'ORIG', 'NAME', 'DESC', 'DATE', 'ENTRY', 'DESCR', 'TRACE',
            'IND', 'EED', 'SEC', 'CCD', 'TRN', 'PPD', 'WEB', 'TEL',
            'DDA', 'REF', 'NSD', 'LLC', 'INC', 'DBA', 'THE', 'FOR',
        }
        words = re.findall(r'\b[A-Z&]{3,}\b', desc_upper)
        words = [w for w in words if w not in stop_words]
        keywords.extend(words[:3])  # Limit to first 3 vendor names

        return list(set(keywords))  # Remove duplicates

    def _deduplicate_suggestions(self, suggestions: List[GLSuggestion]) -> List[GLSuggestion]:
        """Remove duplicate suggestions, keeping highest confidence"""
        seen_accounts = {}

        for suggestion in suggestions:
            account_id = suggestion.account_id
            if account_id not in seen_accounts:
                seen_accounts[account_id] = suggestion
            else:
                # Keep the one with higher confidence
                if suggestion.confidence_score > seen_accounts[account_id].confidence_score:
                    seen_accounts[account_id] = suggestion

        return list(seen_accounts.values())

    def record_vendor_mapping(
        self,
        vendor_id: int,
        account_id: int,
        was_suggested: bool = False,
        was_accepted: bool = False,
        amount: Optional[float] = None
    ):
        """Record or update a vendor-to-GL mapping (Phase 2: with amount tracking)"""
        # Check if mapping exists
        mapping = self.db.query(VendorGLMapping).filter(
            and_(
                VendorGLMapping.vendor_id == vendor_id,
                VendorGLMapping.account_id == account_id
            )
        ).first()

        if mapping:
            # Update existing mapping
            mapping.times_used += 1
            mapping.last_used_date = date.today()

            if was_suggested:
                if was_accepted:
                    mapping.times_accepted += 1
                else:
                    mapping.times_rejected += 1

            # Phase 2: Update amount tracking
            if amount:
                if mapping.min_amount is None or amount < float(mapping.min_amount):
                    mapping.min_amount = Decimal(str(amount))
                if mapping.max_amount is None or amount > float(mapping.max_amount):
                    mapping.max_amount = Decimal(str(amount))
                # Update rolling average
                if mapping.avg_amount:
                    mapping.avg_amount = (mapping.avg_amount * (mapping.times_used - 1) + Decimal(str(amount))) / mapping.times_used
                else:
                    mapping.avg_amount = Decimal(str(amount))

            # Recalculate confidence
            mapping.confidence_score = mapping.calculate_confidence()
        else:
            # Create new mapping
            mapping = VendorGLMapping(
                vendor_id=vendor_id,
                account_id=account_id,
                times_used=1,
                times_accepted=1 if (was_suggested and was_accepted) else 0,
                times_rejected=1 if (was_suggested and not was_accepted) else 0,
                last_used_date=date.today(),
                min_amount=Decimal(str(amount)) if amount else None,
                max_amount=Decimal(str(amount)) if amount else None,
                avg_amount=Decimal(str(amount)) if amount else None
            )
            mapping.confidence_score = mapping.calculate_confidence()
            self.db.add(mapping)

        self.db.commit()

    def record_pattern_mapping(
        self,
        description: str,
        account_id: int,
        was_suggested: bool = False,
        was_accepted: bool = False,
        amount: Optional[float] = None
    ):
        """Record or update description pattern mappings (Phase 2: with amount tracking)"""
        # Extract keywords
        keywords = self._extract_keywords(description)

        for keyword in keywords:
            # Check if pattern exists
            mapping = self.db.query(DescriptionPatternMapping).filter(
                and_(
                    DescriptionPatternMapping.pattern == keyword,
                    DescriptionPatternMapping.account_id == account_id
                )
            ).first()

            if mapping:
                # Update existing mapping
                mapping.times_used += 1

                if was_suggested:
                    if was_accepted:
                        mapping.times_accepted += 1
                    else:
                        mapping.times_rejected += 1

                # Phase 2: Update amount tracking
                if amount:
                    if mapping.min_amount is None or amount < float(mapping.min_amount):
                        mapping.min_amount = Decimal(str(amount))
                    if mapping.max_amount is None or amount > float(mapping.max_amount):
                        mapping.max_amount = Decimal(str(amount))
                    # Update rolling average
                    if mapping.avg_amount:
                        mapping.avg_amount = (mapping.avg_amount * (mapping.times_used - 1) + Decimal(str(amount))) / mapping.times_used
                    else:
                        mapping.avg_amount = Decimal(str(amount))

                # Recalculate confidence
                mapping.confidence_score = mapping.calculate_confidence()
            else:
                # Create new mapping
                mapping = DescriptionPatternMapping(
                    pattern=keyword,
                    pattern_type='keyword',
                    account_id=account_id,
                    times_used=1,
                    times_accepted=1 if (was_suggested and was_accepted) else 0,
                    times_rejected=1 if (was_suggested and not was_accepted) else 0,
                    min_amount=Decimal(str(amount)) if amount else None,
                    max_amount=Decimal(str(amount)) if amount else None,
                    avg_amount=Decimal(str(amount)) if amount else None
                )
                mapping.confidence_score = mapping.calculate_confidence()
                self.db.add(mapping)

        self.db.commit()

    def learn_from_assignment(
        self,
        description: str,
        account_id: int,
        vendor_id: Optional[int] = None,
        suggested_account_id: Optional[int] = None,
        amount: Optional[Decimal] = None,
        transaction_date: Optional[date] = None
    ):
        """
        Learn from a GL assignment (Phase 2 Enhanced).

        Called whenever a user assigns a transaction to a GL account.
        Updates vendor mappings, pattern mappings, and detects recurring transactions.

        Logic:
        - The CHOSEN account (account_id) always gets times_used++ and times_accepted++
          (if it was the suggestion) — it's always a positive signal.
        - The REJECTED suggestion (suggested_account_id != account_id) gets times_rejected++
          without incrementing times_used — it's a negative signal only.
        """
        was_suggested = suggested_account_id is not None
        was_accepted = suggested_account_id == account_id if was_suggested else False

        amount_abs = abs(float(amount)) if amount else None

        # 1. Record the CHOSEN account as a positive signal
        if vendor_id:
            self.record_vendor_mapping(
                vendor_id=vendor_id,
                account_id=account_id,
                was_suggested=was_accepted,  # Only True if this was the suggestion
                was_accepted=was_accepted,
                amount=amount_abs
            )

        self.record_pattern_mapping(
            description=description,
            account_id=account_id,
            was_suggested=was_accepted,  # Only True if this was the suggestion
            was_accepted=was_accepted,
            amount=amount_abs
        )

        # 2. If a different account was suggested, record the REJECTION on that account
        if was_suggested and not was_accepted:
            self._record_rejection(
                description=description,
                rejected_account_id=suggested_account_id,
                vendor_id=vendor_id
            )

        # Phase 2: Detect and record recurring transactions
        if transaction_date and description:
            self.detect_and_record_recurring_pattern(
                description=description,
                vendor_id=vendor_id,
                account_id=account_id,
                amount=amount_abs,
                transaction_date=transaction_date
            )

    def _record_rejection(
        self,
        description: str,
        rejected_account_id: int,
        vendor_id: Optional[int] = None
    ):
        """
        Record a rejection on the suggested account's mappings.

        Only increments times_rejected (not times_used) since the account
        was suggested but not actually used.
        """
        # Record rejection on vendor mapping if exists
        if vendor_id:
            mapping = self.db.query(VendorGLMapping).filter(
                and_(
                    VendorGLMapping.vendor_id == vendor_id,
                    VendorGLMapping.account_id == rejected_account_id
                )
            ).first()
            if mapping:
                mapping.times_rejected += 1
                mapping.confidence_score = mapping.calculate_confidence()

        # Record rejection on pattern mappings
        keywords = self._extract_keywords(description)
        for keyword in keywords:
            mapping = self.db.query(DescriptionPatternMapping).filter(
                and_(
                    DescriptionPatternMapping.pattern == keyword,
                    DescriptionPatternMapping.account_id == rejected_account_id
                )
            ).first()
            if mapping:
                mapping.times_rejected += 1
                mapping.confidence_score = mapping.calculate_confidence()

        # Record rejection on recurring patterns for the rejected account
        if keywords:
            recurring_patterns = self.db.query(RecurringTransactionPattern).filter(
                RecurringTransactionPattern.account_id == rejected_account_id,
                RecurringTransactionPattern.is_active == True
            ).all()
            for pattern in recurring_patterns:
                # Check if this pattern's description matches the transaction
                pattern_keywords = pattern.description_pattern.upper().split()
                if set(pattern_keywords) & set(keywords):
                    # Deactivate recurring patterns that keep getting rejected
                    pattern.occurrence_count = max(pattern.occurrence_count - 1, 0)
                    pattern.confidence_score = pattern.calculate_confidence()
                    if pattern.occurrence_count <= 0:
                        pattern.is_active = False

        self.db.commit()

    def detect_and_record_recurring_pattern(
        self,
        description: str,
        account_id: int,
        amount: Optional[float] = None,
        vendor_id: Optional[int] = None,
        transaction_date: Optional[date] = None
    ):
        """
        Detect and record recurring transaction patterns (Phase 2).

        Looks for previous similar transactions and determines if they form
        a recurring pattern (2+ occurrences ~30 days apart).
        """
        if not description or not transaction_date:
            return

        # Extract keywords for matching
        keywords = self._extract_keywords(description)
        if not keywords:
            return

        # Find previous transactions with similar descriptions
        # We'll query bank_transactions for similar patterns
        from accounting.models.bank_account import BankTransaction

        # Build a query to find similar transactions assigned to the same GL account
        query = self.db.query(BankTransaction).filter(
            BankTransaction.suggested_account_id == account_id,
            BankTransaction.transaction_date < transaction_date,
            BankTransaction.id != None  # Ensure it has an ID
        )

        # Filter by vendor if provided
        if vendor_id:
            # Note: BankTransaction doesn't have vendor_id, so we'll filter by description
            pass

        # Find transactions with matching keywords in description
        similar_transactions = []
        all_candidates = query.order_by(BankTransaction.transaction_date.desc()).limit(100).all()

        for txn in all_candidates:
            if not txn.description:
                continue

            # Check if any keyword matches
            txn_keywords = self._extract_keywords(txn.description)
            common_keywords = set(keywords) & set(txn_keywords)

            # Require at least 1 matching keyword (or vendor match)
            if common_keywords or (vendor_id and txn.description):
                similar_transactions.append(txn)

        # Need at least 1 previous transaction to establish a pattern
        if len(similar_transactions) < 1:
            return

        # Calculate time intervals between occurrences
        dates = sorted([txn.transaction_date for txn in similar_transactions] + [transaction_date])
        intervals = []
        for i in range(1, len(dates)):
            days_diff = (dates[i] - dates[i-1]).days
            intervals.append(days_diff)

        # Check if intervals suggest a recurring pattern
        # Look for consistency (most intervals within 25-35 days for monthly, or other patterns)
        if len(intervals) < 1:
            return

        avg_interval = sum(intervals) / len(intervals)

        # Determine if this is a recurring pattern
        # For monthly: 25-35 days
        # For bi-weekly: 12-16 days
        # For weekly: 5-9 days
        is_recurring = False
        frequency_days = None

        if 25 <= avg_interval <= 35:
            is_recurring = True
            frequency_days = 30
        elif 12 <= avg_interval <= 16:
            is_recurring = True
            frequency_days = 14
        elif 5 <= avg_interval <= 9:
            is_recurring = True
            frequency_days = 7

        if not is_recurring:
            return

        # Calculate amount statistics
        amounts = [abs(float(txn.amount)) for txn in similar_transactions] + ([amount] if amount else [])
        avg_amount = sum(amounts) / len(amounts) if amounts else None
        min_amount = min(amounts) if amounts else None
        max_amount = max(amounts) if amounts else None
        amount_variance = (max_amount - min_amount) / 2 if (min_amount and max_amount) else 0

        # Create a pattern description from keywords
        pattern_desc = ' '.join(keywords[:3])  # Use top 3 keywords

        # Check if pattern already exists
        existing_pattern = self.db.query(RecurringTransactionPattern).filter(
            and_(
                RecurringTransactionPattern.description_pattern == pattern_desc,
                RecurringTransactionPattern.account_id == account_id,
                or_(
                    RecurringTransactionPattern.vendor_id == vendor_id,
                    and_(
                        RecurringTransactionPattern.vendor_id == None,
                        vendor_id == None
                    )
                )
            )
        ).first()

        if existing_pattern:
            # Update existing pattern
            existing_pattern.occurrence_count = len(dates)
            existing_pattern.last_occurrence_date = transaction_date
            existing_pattern.next_expected_date = transaction_date + timedelta(days=frequency_days)
            existing_pattern.frequency_days = frequency_days
            existing_pattern.expected_amount = Decimal(str(avg_amount)) if avg_amount else None
            existing_pattern.amount_variance = Decimal(str(amount_variance)) if amount_variance else Decimal('0.00')
            existing_pattern.confidence_score = existing_pattern.calculate_confidence()
            existing_pattern.updated_at = func.current_timestamp()
        else:
            # Create new recurring pattern
            new_pattern = RecurringTransactionPattern(
                description_pattern=pattern_desc,
                vendor_id=vendor_id,
                account_id=account_id,
                expected_amount=Decimal(str(avg_amount)) if avg_amount else None,
                amount_variance=Decimal(str(amount_variance)) if amount_variance else Decimal('0.00'),
                frequency_days=frequency_days,
                last_occurrence_date=transaction_date,
                next_expected_date=transaction_date + timedelta(days=frequency_days),
                occurrence_count=len(dates),
                is_active=True
            )
            new_pattern.confidence_score = new_pattern.calculate_confidence()
            self.db.add(new_pattern)

        # Deactivate competing recurring patterns for OTHER accounts with overlapping keywords
        competing = self.db.query(RecurringTransactionPattern).filter(
            RecurringTransactionPattern.account_id != account_id,
            RecurringTransactionPattern.is_active == True
        ).all()
        for comp in competing:
            comp_keywords = set(comp.description_pattern.upper().split())
            if comp_keywords & set(keywords):
                # This pattern overlaps but suggests a different account — decrement it
                comp.occurrence_count = max(comp.occurrence_count - 1, 0)
                comp.confidence_score = comp.calculate_confidence()
                if comp.occurrence_count <= 0:
                    comp.is_active = False

        self.db.commit()

    def batch_learn_from_history(self, limit: Optional[int] = None) -> dict:
        """
        Phase 3: Batch learning from historical transactions.

        Train the system on all previously assigned bank transactions.
        Returns statistics about what was learned.
        """
        from accounting.models.bank_account import BankTransaction
        from accounting.utils.vendor_recognition import VendorRecognitionService

        # Find all transactions that have been assigned to GL accounts
        query = self.db.query(BankTransaction).filter(
            BankTransaction.suggested_account_id != None
        ).order_by(BankTransaction.transaction_date)

        if limit:
            query = query.limit(limit)

        transactions = query.all()

        stats = {
            'total_processed': 0,
            'vendor_mappings_created': 0,
            'pattern_mappings_created': 0,
            'recurring_patterns_detected': 0,
            'errors': []
        }

        vendor_service = VendorRecognitionService(self.db)

        for txn in transactions:
            try:
                # Try to recognize vendor
                vendor_id = None
                if txn.description:
                    extracted_name, vendor, confidence = vendor_service.recognize_vendor(txn.description)
                    if vendor:
                        vendor_id = vendor.id

                # Learn from this assignment
                self.learn_from_assignment(
                    description=txn.description or '',
                    account_id=txn.suggested_account_id,
                    vendor_id=vendor_id,
                    suggested_account_id=None,  # Historical - no suggestion was made
                    amount=txn.amount,
                    transaction_date=txn.transaction_date
                )

                stats['total_processed'] += 1

            except Exception as e:
                stats['errors'].append(f"Transaction {txn.id}: {str(e)}")

        # Count what was created
        from accounting.models.gl_learning import VendorGLMapping, DescriptionPatternMapping, RecurringTransactionPattern

        stats['vendor_mappings_total'] = self.db.query(VendorGLMapping).count()
        stats['pattern_mappings_total'] = self.db.query(DescriptionPatternMapping).count()
        stats['recurring_patterns_total'] = self.db.query(RecurringTransactionPattern).filter(
            RecurringTransactionPattern.is_active == True
        ).count()

        return stats

    def refine_patterns(self, min_confidence: float = 20.0, merge_threshold: float = 0.8) -> dict:
        """
        Phase 3: Pattern refinement.

        1. Archive/deactivate low-confidence patterns (< min_confidence)
        2. Merge similar patterns that point to the same account
        3. Clean up duplicate or obsolete patterns

        Returns statistics about refinements made.
        """
        from accounting.models.gl_learning import DescriptionPatternMapping, RecurringTransactionPattern

        stats = {
            'patterns_archived': 0,
            'patterns_merged': 0,
            'recurring_patterns_deactivated': 0
        }

        # 1. Archive low-confidence pattern mappings
        low_confidence_patterns = self.db.query(DescriptionPatternMapping).filter(
            DescriptionPatternMapping.confidence_score < min_confidence
        ).all()

        for pattern in low_confidence_patterns:
            # Don't delete, just reduce their weight in suggestions by lowering confidence
            if pattern.times_rejected > pattern.times_accepted:
                self.db.delete(pattern)
                stats['patterns_archived'] += 1

        # 2. Merge similar patterns
        # Group patterns by account_id
        all_patterns = self.db.query(DescriptionPatternMapping).all()
        patterns_by_account = {}
        for pattern in all_patterns:
            if pattern.account_id not in patterns_by_account:
                patterns_by_account[pattern.account_id] = []
            patterns_by_account[pattern.account_id].append(pattern)

        # For each account, look for similar patterns
        for account_id, patterns in patterns_by_account.items():
            # Sort by times_used descending
            patterns.sort(key=lambda p: p.times_used, reverse=True)

            merged_patterns = set()
            for i, pattern1 in enumerate(patterns):
                if pattern1.id in merged_patterns:
                    continue

                for j, pattern2 in enumerate(patterns[i+1:], start=i+1):
                    if pattern2.id in merged_patterns:
                        continue

                    # Check if patterns are similar
                    if self._are_patterns_similar(pattern1.pattern, pattern2.pattern, merge_threshold):
                        # Merge pattern2 into pattern1
                        pattern1.times_used += pattern2.times_used
                        pattern1.times_accepted += pattern2.times_accepted
                        pattern1.times_rejected += pattern2.times_rejected

                        # Update amounts
                        if pattern2.min_amount:
                            if pattern1.min_amount is None or pattern2.min_amount < pattern1.min_amount:
                                pattern1.min_amount = pattern2.min_amount
                        if pattern2.max_amount:
                            if pattern1.max_amount is None or pattern2.max_amount > pattern1.max_amount:
                                pattern1.max_amount = pattern2.max_amount
                        if pattern2.avg_amount and pattern1.avg_amount:
                            # Weighted average
                            total_uses = pattern1.times_used
                            pattern1.avg_amount = (
                                (pattern1.avg_amount * pattern1.times_used + pattern2.avg_amount * pattern2.times_used) /
                                total_uses
                            )

                        # Recalculate confidence
                        pattern1.confidence_score = pattern1.calculate_confidence()

                        # Mark pattern2 for deletion
                        merged_patterns.add(pattern2.id)
                        self.db.delete(pattern2)
                        stats['patterns_merged'] += 1

        # 3. Deactivate stale recurring patterns (not seen in 90+ days)
        from datetime import date, timedelta
        cutoff_date = date.today() - timedelta(days=90)

        stale_recurring = self.db.query(RecurringTransactionPattern).filter(
            and_(
                RecurringTransactionPattern.is_active == True,
                RecurringTransactionPattern.last_occurrence_date < cutoff_date
            )
        ).all()

        for pattern in stale_recurring:
            pattern.is_active = False
            stats['recurring_patterns_deactivated'] += 1

        self.db.commit()
        return stats

    def _are_patterns_similar(self, pattern1: str, pattern2: str, threshold: float = 0.8) -> bool:
        """
        Check if two patterns are similar enough to merge.

        Uses Jaccard similarity: intersection / union of character sets.
        """
        set1 = set(pattern1.lower().split())
        set2 = set(pattern2.lower().split())

        if not set1 or not set2:
            return False

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold
