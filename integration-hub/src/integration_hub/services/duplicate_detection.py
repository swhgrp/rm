"""
Duplicate Invoice Detection Service

Identifies potential duplicate invoices using multiple matching strategies:
1. Exact hash match (invoice_hash field)
2. Same vendor + invoice number
3. Same vendor + date + amount (within tolerance)
4. Fuzzy invoice number matching (handles OCR variations)
"""

import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_

from integration_hub.models.hub_invoice import HubInvoice

logger = logging.getLogger(__name__)


def normalize_invoice_number(invoice_num: str) -> str:
    """
    Normalize invoice number for comparison.
    Removes common OCR artifacts and formatting differences.
    """
    if not invoice_num:
        return ""

    # Lowercase and strip
    normalized = invoice_num.lower().strip()

    # Remove common prefixes
    for prefix in ['inv#', 'inv-', 'inv ', 'invoice#', 'invoice-', 'invoice ', '#']:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]

    # Remove spaces, dashes, underscores
    normalized = re.sub(r'[\s\-_\.]+', '', normalized)

    # Keep only alphanumeric
    normalized = re.sub(r'[^a-z0-9]', '', normalized)

    return normalized


def amounts_match(amount1: Decimal, amount2: Decimal, tolerance_percent: float = 0.01) -> bool:
    """Check if two amounts match within tolerance (default 1%)"""
    if amount1 is None or amount2 is None:
        return False

    a1 = float(amount1)
    a2 = float(amount2)

    if a1 == 0 and a2 == 0:
        return True

    if a1 == 0 or a2 == 0:
        return False

    diff_percent = abs(a1 - a2) / max(abs(a1), abs(a2))
    return diff_percent <= tolerance_percent


class DuplicateDetectionService:
    """Service for detecting potential duplicate invoices"""

    def __init__(self, db: Session):
        self.db = db

    def _is_same_document_type(self, inv1: HubInvoice, inv2: HubInvoice) -> bool:
        """
        Check if two invoices are the same document type.

        Statements and regular invoices are NOT duplicates even if they share
        the same invoice number - vendors often send both documents with the
        same reference number.

        Returns True if both are statements or both are non-statements.
        """
        inv1_is_statement = inv1.status == 'statement' or getattr(inv1, 'is_statement', False)
        inv2_is_statement = inv2.status == 'statement' or getattr(inv2, 'is_statement', False)
        return inv1_is_statement == inv2_is_statement

    def find_duplicates_for_invoice(
        self,
        invoice_id: int,
        date_window_days: int = 7,
        amount_tolerance: float = 0.01
    ) -> List[Dict]:
        """
        Find potential duplicates for a specific invoice.

        Args:
            invoice_id: The invoice to check for duplicates
            date_window_days: Days before/after to look for duplicates
            amount_tolerance: Percentage tolerance for amount matching

        Returns:
            List of potential duplicate invoices with match reasons
        """
        invoice = self.db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return []

        duplicates = []

        # Strategy 1: Same vendor + invoice number
        inv_num_normalized = normalize_invoice_number(invoice.invoice_number)

        same_number_query = self.db.query(HubInvoice).filter(
            HubInvoice.id != invoice_id,
            HubInvoice.vendor_id == invoice.vendor_id if invoice.vendor_id else HubInvoice.vendor_name == invoice.vendor_name
        ).all()

        for other in same_number_query:
            # IMPORTANT: Don't consider statement vs invoice as duplicates
            if not self._is_same_document_type(invoice, other):
                continue

            other_num_normalized = normalize_invoice_number(other.invoice_number)
            if inv_num_normalized and other_num_normalized and inv_num_normalized == other_num_normalized:
                duplicates.append({
                    'invoice_id': other.id,
                    'invoice_number': other.invoice_number,
                    'vendor_name': other.vendor_name,
                    'invoice_date': other.invoice_date.isoformat() if other.invoice_date else None,
                    'total_amount': float(other.total_amount) if other.total_amount else None,
                    'match_type': 'exact_invoice_number',
                    'confidence': 0.95,
                    'status': other.status,
                    'reason': f"Same vendor, identical invoice number (normalized: {inv_num_normalized})"
                })

        # Strategy 2: Same vendor + date + amount
        if invoice.invoice_date:
            date_start = invoice.invoice_date - timedelta(days=date_window_days)
            date_end = invoice.invoice_date + timedelta(days=date_window_days)

            same_period_query = self.db.query(HubInvoice).filter(
                HubInvoice.id != invoice_id,
                HubInvoice.invoice_date >= date_start,
                HubInvoice.invoice_date <= date_end,
                or_(
                    HubInvoice.vendor_id == invoice.vendor_id,
                    HubInvoice.vendor_name == invoice.vendor_name
                ) if invoice.vendor_id else HubInvoice.vendor_name == invoice.vendor_name
            ).all()

            for other in same_period_query:
                # Skip if already found as invoice number match
                if any(d['invoice_id'] == other.id for d in duplicates):
                    continue

                # IMPORTANT: Don't consider statement vs invoice as duplicates
                if not self._is_same_document_type(invoice, other):
                    continue

                if amounts_match(invoice.total_amount, other.total_amount, amount_tolerance):
                    days_diff = abs((invoice.invoice_date - other.invoice_date).days)
                    confidence = 0.8 - (days_diff * 0.05)  # Reduce confidence for larger date gaps

                    duplicates.append({
                        'invoice_id': other.id,
                        'invoice_number': other.invoice_number,
                        'vendor_name': other.vendor_name,
                        'invoice_date': other.invoice_date.isoformat() if other.invoice_date else None,
                        'total_amount': float(other.total_amount) if other.total_amount else None,
                        'match_type': 'vendor_date_amount',
                        'confidence': max(confidence, 0.5),
                        'status': other.status,
                        'reason': f"Same vendor, matching amount (${invoice.total_amount}), dates within {days_diff} days"
                    })

        # Sort by confidence
        duplicates.sort(key=lambda x: -x['confidence'])

        return duplicates

    def scan_all_duplicates(
        self,
        date_window_days: int = 7,
        amount_tolerance: float = 0.01,
        min_confidence: float = 0.7
    ) -> Dict:
        """
        Scan all invoices for potential duplicates.

        Returns:
            Dict with duplicate groups and statistics
        """
        # Get all invoices
        invoices = self.db.query(HubInvoice).order_by(HubInvoice.created_at.desc()).all()

        # Group by normalized invoice number + vendor + document type (statement vs invoice)
        invoice_groups = {}
        amount_groups = {}

        for inv in invoices:
            # Group by vendor + normalized invoice number + document type
            # CRITICAL: Separate statements from invoices - they are NOT duplicates
            vendor_key = inv.vendor_id or inv.vendor_name
            inv_num_normalized = normalize_invoice_number(inv.invoice_number)
            is_statement = inv.status == 'statement' or getattr(inv, 'is_statement', False)
            doc_type = 'statement' if is_statement else 'invoice'

            if inv_num_normalized:
                # Include document type in key so statements don't group with invoices
                key = f"{vendor_key}:{inv_num_normalized}:{doc_type}"
                if key not in invoice_groups:
                    invoice_groups[key] = []
                invoice_groups[key].append(inv)

            # Group by vendor + amount + date range + document type
            if inv.invoice_date and inv.total_amount:
                # Round amount to whole dollars for grouping
                # Include document type so statements don't group with invoices
                amount_key = f"{vendor_key}:{int(inv.total_amount)}:{doc_type}"
                if amount_key not in amount_groups:
                    amount_groups[amount_key] = []
                amount_groups[amount_key].append(inv)

        # Find duplicate groups
        duplicate_sets = []
        processed_ids = set()

        # Check invoice number groups
        for key, group in invoice_groups.items():
            if len(group) > 1:
                ids = tuple(sorted([i.id for i in group]))
                if ids not in processed_ids:
                    processed_ids.add(ids)
                    duplicate_sets.append({
                        'match_type': 'invoice_number',
                        'confidence': 0.95,
                        'invoices': [
                            {
                                'id': inv.id,
                                'invoice_number': inv.invoice_number,
                                'vendor_name': inv.vendor_name,
                                'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                                'total_amount': float(inv.total_amount) if inv.total_amount else None,
                                'status': inv.status,
                                'created_at': inv.created_at.isoformat() if inv.created_at else None
                            }
                            for inv in group
                        ]
                    })

        # Check amount groups for date proximity
        for key, group in amount_groups.items():
            if len(group) > 1:
                # Check for date proximity within the group
                for i, inv1 in enumerate(group):
                    for inv2 in group[i+1:]:
                        days_diff = abs((inv1.invoice_date - inv2.invoice_date).days)
                        if days_diff <= date_window_days:
                            ids = tuple(sorted([inv1.id, inv2.id]))
                            if ids not in processed_ids:
                                # Check if amounts truly match within tolerance
                                if amounts_match(inv1.total_amount, inv2.total_amount, amount_tolerance):
                                    processed_ids.add(ids)
                                    confidence = 0.8 - (days_diff * 0.03)

                                    if confidence >= min_confidence:
                                        duplicate_sets.append({
                                            'match_type': 'vendor_date_amount',
                                            'confidence': round(confidence, 2),
                                            'invoices': [
                                                {
                                                    'id': inv.id,
                                                    'invoice_number': inv.invoice_number,
                                                    'vendor_name': inv.vendor_name,
                                                    'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                                                    'total_amount': float(inv.total_amount) if inv.total_amount else None,
                                                    'status': inv.status,
                                                    'created_at': inv.created_at.isoformat() if inv.created_at else None
                                                }
                                                for inv in [inv1, inv2]
                                            ]
                                        })

        # Sort by confidence
        duplicate_sets.sort(key=lambda x: -x['confidence'])

        # Calculate statistics
        total_potential_duplicates = sum(len(d['invoices']) for d in duplicate_sets)

        return {
            'duplicate_groups': duplicate_sets,
            'total_groups': len(duplicate_sets),
            'total_potential_duplicates': total_potential_duplicates,
            'scanned_invoices': len(invoices)
        }

    def mark_as_duplicate(
        self,
        duplicate_id: int,
        original_id: int,
        action: str = 'delete'
    ) -> Dict:
        """
        Mark an invoice as a duplicate of another.

        Args:
            duplicate_id: The invoice to mark as duplicate
            original_id: The original invoice to keep
            action: What to do with the duplicate ('delete', 'archive', 'flag')

        Returns:
            Result of the operation
        """
        duplicate = self.db.query(HubInvoice).filter(HubInvoice.id == duplicate_id).first()
        original = self.db.query(HubInvoice).filter(HubInvoice.id == original_id).first()

        if not duplicate:
            return {'error': f'Duplicate invoice {duplicate_id} not found'}
        if not original:
            return {'error': f'Original invoice {original_id} not found'}

        if action == 'delete':
            self.db.delete(duplicate)
            self.db.commit()
            logger.info(f"Deleted duplicate invoice {duplicate_id} (original: {original_id})")
            return {
                'action': 'deleted',
                'duplicate_id': duplicate_id,
                'original_id': original_id,
                'message': f"Deleted invoice {duplicate_id} as duplicate of {original_id}"
            }

        elif action == 'flag':
            # Add flag to status or notes
            duplicate.status = 'duplicate'
            self.db.commit()
            logger.info(f"Flagged invoice {duplicate_id} as duplicate of {original_id}")
            return {
                'action': 'flagged',
                'duplicate_id': duplicate_id,
                'original_id': original_id,
                'message': f"Flagged invoice {duplicate_id} as duplicate"
            }

        else:
            return {'error': f'Unknown action: {action}'}

    def get_duplicate_stats(self) -> Dict:
        """Get statistics about potential duplicates in the system."""
        # Count by match type
        result = self.scan_all_duplicates(min_confidence=0.5)

        by_type = {}
        for group in result['duplicate_groups']:
            match_type = group['match_type']
            if match_type not in by_type:
                by_type[match_type] = 0
            by_type[match_type] += 1

        # Count by vendor
        by_vendor = {}
        for group in result['duplicate_groups']:
            vendor = group['invoices'][0]['vendor_name'] if group['invoices'] else 'Unknown'
            if vendor not in by_vendor:
                by_vendor[vendor] = 0
            by_vendor[vendor] += 1

        return {
            'total_duplicate_groups': result['total_groups'],
            'total_potential_duplicates': result['total_potential_duplicates'],
            'scanned_invoices': result['scanned_invoices'],
            'by_match_type': by_type,
            'by_vendor': dict(sorted(by_vendor.items(), key=lambda x: -x[1])[:10]),
            'high_confidence_groups': len([g for g in result['duplicate_groups'] if g['confidence'] >= 0.9])
        }


def get_duplicate_detection_service(db: Session) -> DuplicateDetectionService:
    """Get duplicate detection service instance"""
    return DuplicateDetectionService(db)
