"""
Invoice Status Service

Centralized logic for determining and updating invoice status based on mapping state.
This ensures consistent status transitions across all operations.

UOM Validation:
- Invoice cannot reach 'ready' status if any mapped vendor item has incomplete UOM
- Required UOM fields: size_quantity, size_unit_id, container_id, units_per_case

Post-Parse Validation:
- Invoices flagged with needs_review go to 'needs_review' instead of 'ready'
- Low-confidence fuzzy mappings trigger review hold
"""

import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.services.vendor_item_review import check_uom_completeness

logger = logging.getLogger(__name__)


def get_unmapped_count(invoice_id: int, db: Session) -> int:
    """Get count of unmapped items for an invoice"""
    return db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id,
        HubInvoiceItem.is_mapped == False
    ).count()


def get_items_with_incomplete_uom(invoice_id: int, db: Session) -> list:
    """
    Get mapped invoice items where the linked vendor item has incomplete UOM.

    Returns list of dicts with item info for display in error messages.
    """
    # Get all mapped items for this invoice
    mapped_items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id,
        HubInvoiceItem.is_mapped == True,
        HubInvoiceItem.inventory_item_id.isnot(None)
    ).all()

    incomplete_items = []

    for item in mapped_items:
        # Get the linked vendor item
        vendor_item = db.query(HubVendorItem).filter(
            HubVendorItem.id == item.inventory_item_id
        ).first()

        if vendor_item:
            uom_check = check_uom_completeness(vendor_item)
            if not uom_check['is_complete']:
                incomplete_items.append({
                    'invoice_item_id': item.id,
                    'item_description': item.item_description,
                    'item_code': item.item_code,
                    'vendor_item_id': vendor_item.id,
                    'vendor_product_name': vendor_item.vendor_product_name,
                    'missing_fields': uom_check['missing_fields']
                })

    return incomplete_items


def get_items_without_master_item(invoice_id: int, db: Session) -> list:
    """
    Get mapped inventory items where the vendor item has no master item link.

    Vendor items must be linked to a master item in Inventory for cost updates
    to work. Expense items (no inventory_item_id) are excluded from this check.

    Returns list of dicts with item info for display in error messages.
    """
    mapped_items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id,
        HubInvoiceItem.is_mapped == True,
        HubInvoiceItem.inventory_item_id.isnot(None)
    ).all()

    missing_master = []

    for item in mapped_items:
        vendor_item = db.query(HubVendorItem).filter(
            HubVendorItem.id == item.inventory_item_id
        ).first()

        if vendor_item and not vendor_item.inventory_master_item_id:
            missing_master.append({
                'invoice_item_id': item.id,
                'item_description': item.item_description,
                'item_code': item.item_code,
                'vendor_item_id': vendor_item.id,
                'vendor_product_name': vendor_item.vendor_product_name
            })

    return missing_master


def get_incomplete_uom_count(invoice_id: int, db: Session) -> int:
    """Get count of mapped items with incomplete UOM for an invoice"""
    return len(get_items_with_incomplete_uom(invoice_id, db))


def get_total_items_count(invoice_id: int, db: Session) -> int:
    """Get total count of items for an invoice"""
    return db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).count()


def update_invoice_status(invoice: HubInvoice, db: Session) -> str:
    """
    Update invoice status based on current mapping state and UOM completeness.

    Status transitions:
    - If already sent/partial/statement: don't change
    - If has unmapped items: set to 'mapping'
    - If all items mapped BUT some have incomplete UOM: stay at 'mapping'
    - If all items mapped AND all have complete UOM: set to 'ready'
    - If no items: keep as 'pending'

    Args:
        invoice: The invoice to update
        db: Database session

    Returns:
        The new status string
    """
    # Don't modify sent, partial, statement, or error status
    if invoice.status in ['sent', 'partial', 'statement', 'error']:
        logger.debug(f"Invoice {invoice.id} status '{invoice.status}' not modified (protected status)")
        return invoice.status

    # Don't modify needs_review unless explicitly cleared (via approve endpoint)
    if invoice.status == 'needs_review':
        logger.debug(f"Invoice {invoice.id} status 'needs_review' not modified (requires manual approval)")
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
        # All items mapped - check UOM completeness and master item linkage before setting to 'ready'
        incomplete_uom_count = get_incomplete_uom_count(invoice.id, db)
        missing_master_items = get_items_without_master_item(invoice.id, db)
        missing_master_count = len(missing_master_items)

        if incomplete_uom_count > 0 or missing_master_count > 0:
            # Has items with incomplete UOM or missing master item - cannot go to 'ready'
            reasons = []
            if incomplete_uom_count > 0:
                reasons.append(f"{incomplete_uom_count} items with incomplete UOM")
            if missing_master_count > 0:
                reasons.append(f"{missing_master_count} items not linked to master item")
            reason_str = ', '.join(reasons)

            if invoice.status != 'mapping':
                old_status = invoice.status
                invoice.status = 'mapping'
                logger.info(f"Invoice {invoice.id}: {reason_str}, status changed from '{old_status}' to 'mapping'")
            else:
                logger.debug(f"Invoice {invoice.id}: {reason_str}, staying at 'mapping'")
        else:
            # All items mapped AND all have complete UOM — check for review flags before 'ready'

            # Check if post-parse validation flagged this invoice
            if getattr(invoice, 'needs_review', False) and invoice.needs_review:
                if invoice.status != 'needs_review':
                    old_status = invoice.status
                    invoice.status = 'needs_review'
                    logger.info(f"Invoice {invoice.id}: flagged for review ({invoice.review_reason}), "
                               f"status changed from '{old_status}' to 'needs_review'")
                return invoice.status

            # Check for low-confidence fuzzy mappings
            low_conf_count = db.query(HubInvoiceItem).filter(
                HubInvoiceItem.invoice_id == invoice.id,
                HubInvoiceItem.is_mapped == True,
                HubInvoiceItem.mapping_confidence < 0.8,
                HubInvoiceItem.mapping_method == 'fuzzy_name'
            ).count()

            if low_conf_count > 0:
                invoice.needs_review = True
                reasons = []
                if invoice.review_reason:
                    try:
                        reasons = json.loads(invoice.review_reason)
                    except (json.JSONDecodeError, TypeError):
                        reasons = []
                reasons.append(f"low_confidence:{low_conf_count}_items")
                invoice.review_reason = json.dumps(reasons)
                if invoice.status != 'needs_review':
                    old_status = invoice.status
                    invoice.status = 'needs_review'
                    logger.info(f"Invoice {invoice.id}: {low_conf_count} low-confidence fuzzy mappings, "
                               f"status changed from '{old_status}' to 'needs_review'")
                return invoice.status

            # All clear — status should be 'ready'
            if invoice.status != 'ready':
                old_status = invoice.status
                invoice.status = 'ready'
                logger.info(f"Invoice {invoice.id}: All {total_items} items mapped with complete UOM, status changed from '{old_status}' to 'ready'")

    return invoice.status


def can_set_status_ready(invoice_id: int, db: Session) -> tuple[bool, str, list]:
    """
    Check if an invoice can be set to 'ready' status.

    Checks:
    1. Invoice has items
    2. All items are mapped
    3. All mapped vendor items have complete UOM

    Args:
        invoice_id: The invoice ID to check
        db: Database session

    Returns:
        Tuple of (can_set_ready, reason, blocking_items)
        - blocking_items: list of items with issues (unmapped or incomplete UOM)
    """
    total_items = get_total_items_count(invoice_id, db)

    if total_items == 0:
        return False, "Invoice has no items", []

    unmapped_count = get_unmapped_count(invoice_id, db)

    if unmapped_count > 0:
        return False, f"Invoice has {unmapped_count} unmapped items", []

    # Check UOM completeness
    incomplete_items = get_items_with_incomplete_uom(invoice_id, db)

    if incomplete_items:
        return False, f"Invoice has {len(incomplete_items)} items with incomplete UOM", incomplete_items

    # Check master item linkage
    missing_master = get_items_without_master_item(invoice_id, db)

    if missing_master:
        return False, f"Invoice has {len(missing_master)} vendor items not linked to a master item", missing_master

    return True, "All items mapped with complete UOM and master item links", []


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
