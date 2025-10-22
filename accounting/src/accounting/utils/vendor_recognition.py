"""
Vendor recognition utilities for bank transaction matching
"""
import re
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from accounting.models.vendor import Vendor


class VendorRecognitionService:
    """Service for extracting and matching vendor names from bank transactions"""

    # Common bank transaction prefixes to strip
    PREFIXES_TO_REMOVE = [
        'ACH DEBIT',
        'ACH CREDIT',
        'CHECK',
        'DEBIT CARD',
        'CREDIT CARD',
        'WIRE TRANSFER',
        'ATM WITHDRAWAL',
        'POS',
        'ONLINE PAYMENT',
        'RECURRING PAYMENT',
        'PURCHASE',
        'PAYMENT',
        'DEPOSIT',
        'WITHDRAWAL',
        'TRANSFER',
    ]

    # Common suffixes to strip
    SUFFIXES_TO_REMOVE = [
        'INC',
        'LLC',
        'CORP',
        'CO',
        'LTD',
        'LP',
        'INCORPORATED',
        'CORPORATION',
        'COMPANY',
    ]

    # Common words to ignore when matching
    NOISE_WORDS = {
        'THE', 'AND', 'OR', 'OF', 'FOR', 'TO', 'FROM', 'AT', 'IN', 'ON',
        'PAYMENT', 'INVOICE', 'BILL', 'CHECK', 'DEPOSIT', 'TRANSFER',
        'ACH', 'WIRE', 'DEBIT', 'CREDIT', 'CARD', 'PURCHASE', 'POS'
    }

    def __init__(self, db: Session):
        self.db = db

    def extract_vendor_name(self, description: str) -> Optional[str]:
        """
        Extract potential vendor name from bank transaction description

        Args:
            description: Raw bank transaction description

        Returns:
            Cleaned vendor name, or None if unable to extract

        Examples:
            "ACH DEBIT GOLD COAST LINEN SERVICE" -> "GOLD COAST LINEN SERVICE"
            "PURCHASE AT SYSCO #12345" -> "SYSCO"
            "CHECK 1234 RESTAURANT DEPOT" -> "RESTAURANT DEPOT"
        """
        if not description:
            return None

        # Convert to uppercase for consistent matching
        cleaned = description.upper().strip()

        # Remove common prefixes
        for prefix in self.PREFIXES_TO_REMOVE:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()

        # Remove transaction IDs (numbers at the end)
        # Example: "GOLD COAST LINEN 123456" -> "GOLD COAST LINEN"
        cleaned = re.sub(r'\s+#?\d{4,}$', '', cleaned)

        # Remove dates (MM/DD or MM-DD or MMDDYY)
        cleaned = re.sub(r'\s+\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?', '', cleaned)

        # Remove common suffixes
        words = cleaned.split()
        if words:
            last_word = words[-1]
            if last_word in self.SUFFIXES_TO_REMOVE:
                words = words[:-1]
            cleaned = ' '.join(words)

        # Remove excessive whitespace
        cleaned = ' '.join(cleaned.split())

        if not cleaned:
            return None

        return cleaned

    def find_matching_vendor(
        self,
        extracted_name: str,
        min_confidence: float = 0.6
    ) -> Optional[Tuple[Vendor, float]]:
        """
        Find vendor in database matching extracted name

        Args:
            extracted_name: Cleaned vendor name from transaction
            min_confidence: Minimum confidence score (0-1)

        Returns:
            Tuple of (Vendor, confidence_score) or None

        Matching Logic:
            1. Exact match on vendor.name -> 1.0 confidence
            2. Exact match on vendor.vendor_code -> 1.0 confidence
            3. Vendor name contains extracted name -> 0.9 confidence
            4. Extracted name contains vendor name -> 0.8 confidence
            5. Fuzzy word match -> 0.6-0.8 confidence
        """
        if not extracted_name:
            return None

        extracted_upper = extracted_name.upper()

        # Get all active vendors
        vendors = self.db.query(Vendor).filter(Vendor.is_active == True).all()

        best_match = None
        best_confidence = 0.0

        for vendor in vendors:
            vendor_name_upper = vendor.vendor_name.upper()
            confidence = 0.0

            # Exact match
            if vendor_name_upper == extracted_upper:
                confidence = 1.0

            # Vendor code match
            elif vendor.vendor_code and vendor.vendor_code.upper() == extracted_upper:
                confidence = 1.0

            # Vendor name contains extracted name
            elif extracted_upper in vendor_name_upper:
                confidence = 0.9

            # Extracted name contains vendor name
            elif vendor_name_upper in extracted_upper:
                confidence = 0.8

            # Fuzzy word match
            else:
                word_match_confidence = self._calculate_word_match_confidence(
                    extracted_upper,
                    vendor_name_upper
                )
                if word_match_confidence >= min_confidence:
                    confidence = word_match_confidence

            # Track best match
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = vendor

        if best_match and best_confidence >= min_confidence:
            return (best_match, best_confidence)

        return None

    def _calculate_word_match_confidence(
        self,
        extracted: str,
        vendor_name: str
    ) -> float:
        """
        Calculate confidence based on word-level matching

        Ignores noise words and calculates percentage of matching words

        Example:
            extracted = "GOLD COAST LINEN"
            vendor_name = "GOLD COAST LINEN SERVICE INC"
            -> 3 out of 3 significant words match -> 1.0 confidence
        """
        # Split into words
        extracted_words = set(extracted.split())
        vendor_words = set(vendor_name.split())

        # Remove noise words
        extracted_words -= self.NOISE_WORDS
        vendor_words -= self.NOISE_WORDS

        if not extracted_words or not vendor_words:
            return 0.0

        # Calculate overlap
        matching_words = extracted_words & vendor_words

        # Confidence = matching words / min(extracted, vendor) words
        # This gives high confidence if all extracted words are in vendor name
        min_word_count = min(len(extracted_words), len(vendor_words))
        confidence = len(matching_words) / min_word_count if min_word_count > 0 else 0.0

        # Scale to 0.6-0.9 range for fuzzy matches
        if confidence > 0:
            confidence = 0.6 + (confidence * 0.3)

        return confidence

    def recognize_vendor(self, description: str) -> Tuple[Optional[str], Optional[Vendor], float]:
        """
        One-step vendor recognition: extract and match

        Args:
            description: Bank transaction description

        Returns:
            Tuple of (extracted_name, vendor, confidence)
        """
        extracted_name = self.extract_vendor_name(description)

        if not extracted_name:
            return (None, None, 0.0)

        match_result = self.find_matching_vendor(extracted_name)

        if match_result:
            vendor, confidence = match_result
            return (extracted_name, vendor, confidence)

        return (extracted_name, None, 0.0)
