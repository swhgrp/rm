"""
Parse Retry Service

Handles automatic retrying of failed invoice parsing with exponential backoff.
Prevents perpetual failures by tracking attempts and marking permanently failed invoices.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.services.invoice_parser import get_invoice_parser

logger = logging.getLogger(__name__)


class ParseRetryService:
    """Service for retrying failed invoice parses with exponential backoff"""

    # Configuration
    MAX_PARSE_ATTEMPTS = 5  # Maximum retry attempts before marking as failed
    BASE_RETRY_DELAY_MINUTES = 2  # Initial delay: 2 minutes
    MAX_RETRY_DELAY_MINUTES = 60  # Maximum delay: 1 hour

    def __init__(self):
        self.parser = None  # Lazy load to avoid issues if OpenAI key not set

    def _get_parser(self):
        """Lazy load parser to handle missing API key gracefully"""
        if self.parser is None:
            try:
                self.parser = get_invoice_parser()
            except ValueError as e:
                logger.error(f"Cannot initialize parser: {e}")
                raise
        return self.parser

    def calculate_next_retry_time(self, attempt_number: int) -> datetime:
        """
        Calculate next retry time using exponential backoff

        Delays: 2min, 4min, 8min, 16min, 32min (capped at 60min)
        """
        delay_minutes = min(
            self.BASE_RETRY_DELAY_MINUTES * (2 ** attempt_number),
            self.MAX_RETRY_DELAY_MINUTES
        )
        return datetime.utcnow() + timedelta(minutes=delay_minutes)

    def get_invoices_needing_parse(self, db: Session, limit: int = 10) -> List[HubInvoice]:
        """
        Get invoices that need parsing or retry

        Returns invoices that:
        1. Are in 'pending' status with no parse attempts yet, OR
        2. Have a next_parse_retry_at time that has passed

        Excludes invoices that have reached MAX_PARSE_ATTEMPTS.
        """
        now = datetime.utcnow()

        invoices = db.query(HubInvoice).filter(
            and_(
                # Must be pending or have retry scheduled
                or_(
                    # New invoices that haven't been parsed yet
                    and_(
                        HubInvoice.status == 'pending',
                        or_(
                            HubInvoice.parse_attempts == None,
                            HubInvoice.parse_attempts == 0
                        )
                    ),
                    # Invoices scheduled for retry
                    and_(
                        HubInvoice.next_parse_retry_at != None,
                        HubInvoice.next_parse_retry_at <= now
                    )
                ),
                # Must have PDF to parse
                HubInvoice.pdf_path != None,
                # Must not have exceeded max attempts
                or_(
                    HubInvoice.parse_attempts == None,
                    HubInvoice.parse_attempts < self.MAX_PARSE_ATTEMPTS
                )
            )
        ).order_by(
            # Prioritize new invoices over retries
            HubInvoice.parse_attempts.asc().nullsfirst(),
            HubInvoice.created_at.asc()
        ).limit(limit).all()

        return invoices

    def parse_with_retry(self, invoice: HubInvoice, db: Session) -> Dict:
        """
        Attempt to parse an invoice, handling failures with retry scheduling

        Returns dict with result status and details
        """
        invoice_id = invoice.id
        current_attempt = (invoice.parse_attempts or 0) + 1

        logger.info(f"Parsing invoice {invoice_id} (attempt {current_attempt}/{self.MAX_PARSE_ATTEMPTS})")

        # Update attempt count and clear retry time
        invoice.parse_attempts = current_attempt
        invoice.next_parse_retry_at = None
        invoice.status = 'parsing'
        db.commit()

        try:
            parser = self._get_parser()
            result = parser.parse_and_save(invoice_id, db)

            # Refresh invoice after parse_and_save may have modified it
            db.refresh(invoice)

            if result.get('success'):
                # Parse succeeded - clear error fields
                invoice.parse_error = None
                invoice.next_parse_retry_at = None
                db.commit()

                logger.info(f"Invoice {invoice_id} parsed successfully on attempt {current_attempt}")
                return {
                    "success": True,
                    "invoice_id": invoice_id,
                    "attempt": current_attempt,
                    "message": result.get('message'),
                    "items_parsed": result.get('items_parsed', 0)
                }

            elif result.get('is_duplicate'):
                # Duplicate detected and handled - not a failure
                logger.info(f"Invoice {invoice_id} was a duplicate and has been removed")
                return {
                    "success": True,
                    "invoice_id": invoice_id,
                    "is_duplicate": True,
                    "message": result.get('message')
                }

            else:
                # Parse failed
                error_message = result.get('message') or result.get('error') or 'Unknown parse error'
                return self._handle_parse_failure(invoice, db, current_attempt, error_message)

        except Exception as e:
            error_message = str(e)
            logger.error(f"Exception parsing invoice {invoice_id}: {error_message}", exc_info=True)
            return self._handle_parse_failure(invoice, db, current_attempt, error_message)

    def _handle_parse_failure(self, invoice: HubInvoice, db: Session, attempt: int, error_message: str) -> Dict:
        """Handle a parse failure - schedule retry or mark as permanently failed"""
        invoice_id = invoice.id
        invoice.parse_error = error_message[:1000]  # Truncate long errors

        if attempt >= self.MAX_PARSE_ATTEMPTS:
            # Max attempts reached - mark as permanently failed
            invoice.status = 'parse_failed'
            invoice.next_parse_retry_at = None
            db.commit()

            logger.error(f"Invoice {invoice_id} failed parsing after {attempt} attempts. Marked as parse_failed.")
            return {
                "success": False,
                "invoice_id": invoice_id,
                "attempt": attempt,
                "permanently_failed": True,
                "error": error_message,
                "message": f"Parsing failed after {attempt} attempts. Manual intervention required."
            }
        else:
            # Schedule retry with exponential backoff
            next_retry = self.calculate_next_retry_time(attempt)
            invoice.status = 'pending'  # Keep as pending for retry
            invoice.next_parse_retry_at = next_retry
            db.commit()

            delay_minutes = (next_retry - datetime.utcnow()).total_seconds() / 60
            logger.warning(f"Invoice {invoice_id} parse attempt {attempt} failed. Retry scheduled in {delay_minutes:.1f} minutes.")

            return {
                "success": False,
                "invoice_id": invoice_id,
                "attempt": attempt,
                "permanently_failed": False,
                "next_retry_at": next_retry.isoformat(),
                "error": error_message,
                "message": f"Parse failed, retry {attempt + 1}/{self.MAX_PARSE_ATTEMPTS} scheduled in {delay_minutes:.1f} minutes"
            }

    def process_pending_parses(self, db: Session, batch_size: int = 5) -> Dict:
        """
        Process a batch of invoices needing parsing

        Called periodically by the scheduler.
        Returns summary of processing results.
        """
        invoices = self.get_invoices_needing_parse(db, limit=batch_size)

        if not invoices:
            return {
                "processed": 0,
                "message": "No invoices need parsing"
            }

        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "permanently_failed": 0,
            "duplicates": 0,
            "details": []
        }

        for invoice in invoices:
            try:
                result = self.parse_with_retry(invoice, db)
                results["processed"] += 1
                results["details"].append(result)

                if result.get("success"):
                    if result.get("is_duplicate"):
                        results["duplicates"] += 1
                    else:
                        results["succeeded"] += 1
                else:
                    results["failed"] += 1
                    if result.get("permanently_failed"):
                        results["permanently_failed"] += 1

            except Exception as e:
                logger.error(f"Error processing invoice {invoice.id}: {e}", exc_info=True)
                results["processed"] += 1
                results["failed"] += 1

        logger.info(f"Parse retry batch complete: {results['succeeded']} succeeded, "
                   f"{results['failed']} failed ({results['permanently_failed']} permanent)")

        return results

    def reset_failed_invoice(self, invoice_id: int, db: Session) -> Dict:
        """
        Reset a failed invoice to allow re-parsing

        Use when manual intervention has fixed the issue (e.g., re-uploaded PDF)
        """
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()

        if not invoice:
            return {"success": False, "error": "Invoice not found"}

        if invoice.status not in ('pending', 'parse_failed'):
            return {
                "success": False,
                "error": f"Cannot reset invoice in '{invoice.status}' status. Only 'pending' or 'parse_failed' invoices can be reset."
            }

        # Reset parse tracking
        invoice.parse_attempts = 0
        invoice.parse_error = None
        invoice.next_parse_retry_at = None
        invoice.status = 'pending'
        db.commit()

        logger.info(f"Invoice {invoice_id} reset for re-parsing")
        return {
            "success": True,
            "message": f"Invoice {invoice_id} reset. It will be parsed in the next batch."
        }

    def get_parse_status_summary(self, db: Session) -> Dict:
        """Get summary of parsing status for dashboard"""
        from sqlalchemy import func

        # Count by status
        status_counts = db.query(
            HubInvoice.status,
            func.count(HubInvoice.id)
        ).group_by(HubInvoice.status).all()

        status_dict = {status: count for status, count in status_counts}

        # Count invoices awaiting retry
        awaiting_retry = db.query(func.count(HubInvoice.id)).filter(
            HubInvoice.next_parse_retry_at != None,
            HubInvoice.status == 'pending'
        ).scalar() or 0

        # Count invoices that failed all retries
        permanently_failed = status_dict.get('parse_failed', 0)

        # Get recent failures for display
        recent_failures = db.query(HubInvoice).filter(
            HubInvoice.status == 'parse_failed'
        ).order_by(HubInvoice.updated_at.desc()).limit(10).all()

        return {
            "status_counts": status_dict,
            "awaiting_retry": awaiting_retry,
            "permanently_failed": permanently_failed,
            "recent_failures": [
                {
                    "id": inv.id,
                    "vendor_name": inv.vendor_name,
                    "invoice_number": inv.invoice_number,
                    "parse_attempts": inv.parse_attempts,
                    "parse_error": inv.parse_error[:200] if inv.parse_error else None,
                    "source_filename": inv.source_filename
                }
                for inv in recent_failures
            ]
        }


# Singleton instance
_parse_retry_service = None


def get_parse_retry_service() -> ParseRetryService:
    """Get or create parse retry service singleton"""
    global _parse_retry_service
    if _parse_retry_service is None:
        _parse_retry_service = ParseRetryService()
    return _parse_retry_service
