"""
Batch Operations Service

Provides bulk operations for invoices:
- Batch approve
- Batch mapping (auto-map)
- Batch status updates
- Batch send to systems
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.services.auto_mapper import AutoMapperService

logger = logging.getLogger(__name__)


class BatchOperationsService:
    """Service for performing batch operations on invoices"""

    def __init__(self, db: Session):
        self.db = db

    def batch_approve(
        self,
        invoice_ids: List[int],
        approved_by: int = None
    ) -> Dict:
        """
        Approve multiple invoices at once.

        Args:
            invoice_ids: List of invoice IDs to approve
            approved_by: User ID who approved (optional)

        Returns:
            Dict with results summary
        """
        results = {
            'total': len(invoice_ids),
            'approved': 0,
            'already_approved': 0,
            'failed': 0,
            'errors': []
        }

        for invoice_id in invoice_ids:
            try:
                invoice = self.db.query(HubInvoice).filter(
                    HubInvoice.id == invoice_id
                ).first()

                if not invoice:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Invoice not found'
                    })
                    continue

                # Check if already approved
                if invoice.approved_at:
                    results['already_approved'] += 1
                    continue

                # Approve the invoice
                invoice.approved_at = get_now()
                invoice.approved_by = approved_by

                # Re-evaluate status (checks unmapped, UOM, master items)
                if invoice.status == 'pending':
                    from integration_hub.services.invoice_status import update_invoice_status
                    update_invoice_status(invoice, self.db)

                results['approved'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        self.db.commit()
        logger.info(f"Batch approve completed: {results['approved']} approved, "
                   f"{results['already_approved']} already approved, {results['failed']} failed")

        return results

    def batch_auto_map(self, invoice_ids: List[int]) -> Dict:
        """
        Run auto-mapping on multiple invoices.

        Args:
            invoice_ids: List of invoice IDs to auto-map

        Returns:
            Dict with results summary
        """
        auto_mapper = AutoMapperService(self.db)

        results = {
            'total': len(invoice_ids),
            'processed': 0,
            'total_items': 0,
            'total_mapped': 0,
            'failed': 0,
            'errors': [],
            'per_invoice': []
        }

        for invoice_id in invoice_ids:
            try:
                mapping_result = auto_mapper.map_invoice_items(invoice_id)

                if 'error' in mapping_result:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': mapping_result['error']
                    })
                    continue

                results['processed'] += 1
                results['total_items'] += mapping_result.get('total_items', 0)
                results['total_mapped'] += mapping_result.get('mapped_count', 0)
                results['per_invoice'].append({
                    'invoice_id': invoice_id,
                    'items': mapping_result.get('total_items', 0),
                    'mapped': mapping_result.get('mapped_count', 0)
                })

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        logger.info(f"Batch auto-map completed: {results['processed']} invoices, "
                   f"{results['total_mapped']}/{results['total_items']} items mapped")

        return results

    def batch_update_status(
        self,
        invoice_ids: List[int],
        new_status: str
    ) -> Dict:
        """
        Update status for multiple invoices.

        Args:
            invoice_ids: List of invoice IDs
            new_status: New status to set

        Returns:
            Dict with results summary
        """
        valid_statuses = ['pending', 'mapping', 'ready', 'sent', 'error', 'partial']

        if new_status not in valid_statuses:
            return {
                'error': f'Invalid status. Must be one of: {valid_statuses}'
            }

        results = {
            'total': len(invoice_ids),
            'updated': 0,
            'failed': 0,
            'errors': []
        }

        for invoice_id in invoice_ids:
            try:
                invoice = self.db.query(HubInvoice).filter(
                    HubInvoice.id == invoice_id
                ).first()

                if not invoice:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Invoice not found'
                    })
                    continue

                invoice.status = new_status
                results['updated'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        self.db.commit()
        logger.info(f"Batch status update to '{new_status}': {results['updated']} updated, "
                   f"{results['failed']} failed")

        return results

    def batch_mark_sent(
        self,
        invoice_ids: List[int],
        target: str = 'both'
    ) -> Dict:
        """
        Mark invoices as sent to inventory/accounting.

        Args:
            invoice_ids: List of invoice IDs
            target: 'inventory', 'accounting', or 'both'

        Returns:
            Dict with results summary
        """
        if target not in ['inventory', 'accounting', 'both']:
            return {'error': "target must be 'inventory', 'accounting', or 'both'"}

        results = {
            'total': len(invoice_ids),
            'updated': 0,
            'failed': 0,
            'errors': []
        }

        now = get_now()

        for invoice_id in invoice_ids:
            try:
                invoice = self.db.query(HubInvoice).filter(
                    HubInvoice.id == invoice_id
                ).first()

                if not invoice:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Invoice not found'
                    })
                    continue

                if target in ['inventory', 'both']:
                    invoice.sent_to_inventory = True
                    invoice.inventory_sync_at = now

                if target in ['accounting', 'both']:
                    invoice.sent_to_accounting = True
                    invoice.accounting_sync_at = now

                # Update status
                if invoice.sent_to_inventory and invoice.sent_to_accounting:
                    invoice.status = 'sent'
                elif invoice.sent_to_inventory or invoice.sent_to_accounting:
                    invoice.status = 'partial'

                results['updated'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        self.db.commit()
        logger.info(f"Batch mark sent ({target}): {results['updated']} updated, "
                   f"{results['failed']} failed")

        return results

    def batch_reset_sync(
        self,
        invoice_ids: List[int],
        target: str = 'both'
    ) -> Dict:
        """
        Reset sync status for invoices (allows re-sending).

        Args:
            invoice_ids: List of invoice IDs
            target: 'inventory', 'accounting', or 'both'

        Returns:
            Dict with results summary
        """
        if target not in ['inventory', 'accounting', 'both']:
            return {'error': "target must be 'inventory', 'accounting', or 'both'"}

        results = {
            'total': len(invoice_ids),
            'reset': 0,
            'failed': 0,
            'errors': []
        }

        for invoice_id in invoice_ids:
            try:
                invoice = self.db.query(HubInvoice).filter(
                    HubInvoice.id == invoice_id
                ).first()

                if not invoice:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Invoice not found'
                    })
                    continue

                if target in ['inventory', 'both']:
                    invoice.sent_to_inventory = False
                    invoice.inventory_sync_at = None
                    invoice.inventory_invoice_id = None
                    invoice.inventory_error = None
                    invoice.inventory_sync_error = None

                if target in ['accounting', 'both']:
                    invoice.sent_to_accounting = False
                    invoice.accounting_sync_at = None
                    invoice.accounting_je_id = None
                    invoice.accounting_error = None
                    invoice.accounting_sync_error = None

                # Reset status to ready if both are cleared
                if not invoice.sent_to_inventory and not invoice.sent_to_accounting:
                    invoice.status = 'ready'
                elif not invoice.sent_to_inventory or not invoice.sent_to_accounting:
                    invoice.status = 'partial'

                results['reset'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        self.db.commit()
        logger.info(f"Batch reset sync ({target}): {results['reset']} reset, "
                   f"{results['failed']} failed")

        return results

    def batch_delete(self, invoice_ids: List[int]) -> Dict:
        """
        Delete multiple invoices.

        Args:
            invoice_ids: List of invoice IDs to delete

        Returns:
            Dict with results summary
        """
        results = {
            'total': len(invoice_ids),
            'deleted': 0,
            'failed': 0,
            'errors': []
        }

        for invoice_id in invoice_ids:
            try:
                invoice = self.db.query(HubInvoice).filter(
                    HubInvoice.id == invoice_id
                ).first()

                if not invoice:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Invoice not found'
                    })
                    continue

                # Don't delete invoices that have been sent to systems
                if invoice.sent_to_inventory or invoice.sent_to_accounting:
                    results['failed'] += 1
                    results['errors'].append({
                        'invoice_id': invoice_id,
                        'error': 'Cannot delete invoice already sent to systems'
                    })
                    continue

                self.db.delete(invoice)
                results['deleted'] += 1

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'invoice_id': invoice_id,
                    'error': str(e)
                })

        self.db.commit()
        logger.info(f"Batch delete: {results['deleted']} deleted, {results['failed']} failed")

        return results

    def get_batch_summary(self, invoice_ids: List[int]) -> Dict:
        """
        Get summary statistics for a set of invoices.

        Args:
            invoice_ids: List of invoice IDs

        Returns:
            Dict with summary statistics
        """
        invoices = self.db.query(HubInvoice).filter(
            HubInvoice.id.in_(invoice_ids)
        ).all()

        summary = {
            'total_invoices': len(invoices),
            'found': len(invoices),
            'not_found': len(invoice_ids) - len(invoices),
            'total_amount': 0.0,
            'by_status': {},
            'by_vendor': {},
            'sync_status': {
                'sent_to_inventory': 0,
                'sent_to_accounting': 0,
                'pending_inventory': 0,
                'pending_accounting': 0
            },
            'approved': 0,
            'unapproved': 0
        }

        for invoice in invoices:
            # Total amount
            if invoice.total_amount:
                summary['total_amount'] += float(invoice.total_amount)

            # By status
            status = invoice.status or 'unknown'
            summary['by_status'][status] = summary['by_status'].get(status, 0) + 1

            # By vendor
            vendor = invoice.vendor_name or 'Unknown'
            summary['by_vendor'][vendor] = summary['by_vendor'].get(vendor, 0) + 1

            # Sync status
            if invoice.sent_to_inventory:
                summary['sync_status']['sent_to_inventory'] += 1
            else:
                summary['sync_status']['pending_inventory'] += 1

            if invoice.sent_to_accounting:
                summary['sync_status']['sent_to_accounting'] += 1
            else:
                summary['sync_status']['pending_accounting'] += 1

            # Approval status
            if invoice.approved_at:
                summary['approved'] += 1
            else:
                summary['unapproved'] += 1

        return summary


def get_batch_operations(db: Session) -> BatchOperationsService:
    """Get batch operations service instance"""
    return BatchOperationsService(db)
