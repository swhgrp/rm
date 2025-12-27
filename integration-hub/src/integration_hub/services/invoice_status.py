"""
Invoice Status Service

Centralized logic for determining and updating invoice status based on mapping state.
This ensures consistent status transitions across all operations.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)


def get_unmapped_count(invoice_id: int, db: Session) -> int:
    """Get count of unmapped items for an invoice"""
    return db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id,
        HubInvoiceItem.is_mapped == False
    ).count()


def get_total_items_count(invoice_id: int, db: Session) -> int:
    """Get total count of items for an invoice"""
    return db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).count()


def update_invoice_status(invoice: HubInvoice, db: Session) -> str:
    """
    Update invoice status based on current mapping state.

    Status transitions:
    - If already sent/partial/statement: don't change
    - If has unmapped items: set to 'mapping'
    - If all items mapped: set to 'ready'
    - If no items: keep as 'pending'

    Args:
        invoice: The invoice to update
        db: Database session

    Returns:
        The new status string
    """
    # Don't modify sent, partial, or statement status
    if invoice.status in ['sent', 'partial', 'statement', 'error']:
        logger.debug(f"Invoice {invoice.id} status '{invoice.status}' not modified (protected status)")
        return invoice.status

    total_items = get_total_items_count(invoice.id, db)

    # No items yet - keep as pending
    if total_items == 0:
        if invoice.status != 'pending':
            invoice.status = 'pending'
            logger.info(f"Invoice {invoice.id}: No items, status set to 'pending'")
        return invoice.status

    unmapped_count = get_unmapped_count(invoice.id, db)

    if unmapped_count > 0:
        # Has unmapped items - status should be 'mapping'
        if invoice.status != 'mapping':
            old_status = invoice.status
            invoice.status = 'mapping'
            logger.info(f"Invoice {invoice.id}: {unmapped_count} unmapped items, status changed from '{old_status}' to 'mapping'")
    else:
        # All items mapped - status should be 'ready'
        if invoice.status != 'ready':
            old_status = invoice.status
            invoice.status = 'ready'
            logger.info(f"Invoice {invoice.id}: All {total_items} items mapped, status changed from '{old_status}' to 'ready'")

    return invoice.status


def can_set_status_ready(invoice_id: int, db: Session) -> tuple[bool, str]:
    """
    Check if an invoice can be set to 'ready' status.

    Args:
        invoice_id: The invoice ID to check
        db: Database session

    Returns:
        Tuple of (can_set_ready, reason)
    """
    total_items = get_total_items_count(invoice_id, db)

    if total_items == 0:
        return False, "Invoice has no items"

    unmapped_count = get_unmapped_count(invoice_id, db)

    if unmapped_count > 0:
        return False, f"Invoice has {unmapped_count} unmapped items"

    return True, "All items mapped"


def recalculate_invoice_status(invoice_id: int, db: Session) -> str:
    """
    Recalculate and update status for an invoice by ID.

    Useful for fixing invoices with incorrect status.

    Args:
        invoice_id: The invoice ID
        db: Database session

    Returns:
        The new status string, or None if invoice not found
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        logger.warning(f"Invoice {invoice_id} not found for status recalculation")
        return None

    new_status = update_invoice_status(invoice, db)
    db.commit()
    return new_status


def bulk_recalculate_status(db: Session, status_filter: str = None) -> dict:
    """
    Recalculate status for multiple invoices.

    Args:
        db: Database session
        status_filter: Optional filter by current status (e.g., 'mapping', 'ready')

    Returns:
        Dict with summary of changes
    """
    query = db.query(HubInvoice)

    # Don't touch sent/partial/statement invoices
    query = query.filter(HubInvoice.status.notin_(['sent', 'partial', 'statement', 'error']))

    if status_filter:
        query = query.filter(HubInvoice.status == status_filter)

    invoices = query.all()

    results = {
        'total_checked': len(invoices),
        'updated': 0,
        'no_change': 0,
        'changes': []
    }

    for invoice in invoices:
        old_status = invoice.status
        new_status = update_invoice_status(invoice, db)

        if old_status != new_status:
            results['updated'] += 1
            results['changes'].append({
                'invoice_id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'old_status': old_status,
                'new_status': new_status
            })
        else:
            results['no_change'] += 1

    db.commit()
    logger.info(f"Bulk status recalculation: {results['updated']} updated, {results['no_change']} unchanged")

    return results
