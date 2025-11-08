"""
Auto-Send Orchestrator Service

Orchestrates sending invoices to both Inventory and Accounting systems.
Handles parallel sending, error handling, and status updates.
"""

import asyncio
import logging
from typing import Dict, Tuple
from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.services.inventory_sender import InventorySenderService
from integration_hub.services.accounting_sender import AccountingSenderService

logger = logging.getLogger(__name__)


class AutoSendService:
    """Service for automatically sending invoices to both systems"""

    def __init__(
        self,
        inventory_sender: InventorySenderService,
        accounting_sender: AccountingSenderService
    ):
        """
        Initialize the auto-send service

        Args:
            inventory_sender: Inventory sender service instance
            accounting_sender: Accounting sender service instance
        """
        self.inventory_sender = inventory_sender
        self.accounting_sender = accounting_sender

    async def send_invoice(self, invoice_id: int, db: Session) -> Dict:
        """
        Send invoice to both Inventory and Accounting systems

        This method:
        1. Validates the invoice is ready (all items mapped)
        2. Sends to both systems in parallel
        3. Updates invoice status based on results
        4. Returns summary of what was sent

        Args:
            invoice_id: ID of the HubInvoice to send
            db: Database session

        Returns:
            Dict with results:
            {
                "success": bool,
                "inventory_sent": bool,
                "accounting_sent": bool,
                "inventory_id": int or None,
                "journal_entry_id": int or None,
                "errors": list of error messages
            }
        """
        # Get invoice and items
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        items = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id
        ).all()

        # Validate invoice is ready
        validation_result = self._validate_invoice_ready(invoice, items)
        if not validation_result["ready"]:
            return {
                "success": False,
                "inventory_sent": False,
                "accounting_sent": False,
                "inventory_id": None,
                "journal_entry_id": None,
                "errors": validation_result["errors"]
            }

        logger.info(f"Auto-sending invoice {invoice.invoice_number} (ID: {invoice_id})")

        # Determine which systems need this invoice
        # Send to inventory only if at least one item has an inventory category
        has_inventory_items = any(item.inventory_category for item in items)
        # Always send to accounting (all items have GL accounts)
        needs_accounting = True

        logger.info(f"Invoice {invoice.invoice_number}: has_inventory_items={has_inventory_items}, needs_accounting={needs_accounting}")

        # Send to appropriate systems in parallel
        tasks = []
        send_to_inventory = has_inventory_items
        send_to_accounting = needs_accounting

        if send_to_inventory:
            tasks.append(self._send_to_inventory(invoice, items, db))
        else:
            tasks.append(None)  # Placeholder

        if send_to_accounting:
            tasks.append(self._send_to_accounting(invoice, items, db))
        else:
            tasks.append(None)  # Placeholder

        # Execute tasks
        if send_to_inventory and send_to_accounting:
            inventory_result, accounting_result = await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)
        elif send_to_inventory:
            inventory_result = await tasks[0] if tasks[0] else {"success": False, "skipped": True}
            accounting_result = {"success": True, "skipped": True}
        elif send_to_accounting:
            inventory_result = {"success": True, "skipped": True}
            accounting_result = await tasks[1] if tasks[1] else {"success": False, "skipped": True}
        else:
            inventory_result = {"success": True, "skipped": True}
            accounting_result = {"success": True, "skipped": True}

        # Process results
        inventory_sent = send_to_inventory and not isinstance(inventory_result, Exception)
        accounting_sent = send_to_accounting and not isinstance(accounting_result, Exception)

        # If we skipped a system, mark it as "sent" for status purposes
        # Also set the sent flag on the invoice so the UI shows it correctly
        if not send_to_inventory:
            inventory_sent = True  # Not needed, so consider it "done"
            invoice.sent_to_inventory = True  # Mark as sent in DB so UI reflects this
        if not send_to_accounting:
            accounting_sent = True  # Not needed, so consider it "done"
            invoice.sent_to_accounting = True  # Mark as sent in DB so UI reflects this

        errors = []
        if send_to_inventory and isinstance(inventory_result, Exception):
            errors.append(f"Inventory: {str(inventory_result)}")
        if send_to_accounting and isinstance(accounting_result, Exception):
            errors.append(f"Accounting: {str(accounting_result)}")

        # Update invoice status
        if inventory_sent and accounting_sent:
            invoice.status = 'sent'
            logger.info(f"Invoice {invoice.invoice_number} successfully sent to required systems")
        elif inventory_sent or accounting_sent:
            invoice.status = 'partial'
            logger.warning(f"Invoice {invoice.invoice_number} partially sent: Inv={inventory_sent}, Acct={accounting_sent}")
        else:
            invoice.status = 'error'
            logger.error(f"Invoice {invoice.invoice_number} failed to send")

        db.commit()

        return {
            "success": inventory_sent and accounting_sent,
            "inventory_sent": inventory_sent,
            "accounting_sent": accounting_sent,
            "inventory_id": inventory_result.get("inventory_invoice_id") if (send_to_inventory and inventory_sent and isinstance(inventory_result, dict)) else None,
            "journal_entry_id": accounting_result.get("journal_entry_id") if (send_to_accounting and accounting_sent and isinstance(accounting_result, dict)) else None,
            "errors": errors
        }

    async def _send_to_inventory(self, invoice: HubInvoice, items: list, db: Session) -> Dict:
        """
        Send to inventory system

        Args:
            invoice: HubInvoice instance
            items: List of HubInvoiceItem instances
            db: Database session

        Returns:
            Result dict from inventory sender

        Raises:
            Exception: If sending fails
        """
        try:
            return await self.inventory_sender.send_invoice(invoice, items, db)
        except Exception as e:
            logger.error(f"Failed to send invoice {invoice.invoice_number} to inventory: {str(e)}")
            raise

    async def _send_to_accounting(self, invoice: HubInvoice, items: list, db: Session) -> Dict:
        """
        Send to accounting system

        Args:
            invoice: HubInvoice instance
            items: List of HubInvoiceItem instances
            db: Database session

        Returns:
            Result dict from accounting sender

        Raises:
            Exception: If sending fails
        """
        try:
            return await self.accounting_sender.send_journal_entry(invoice, items, db)
        except Exception as e:
            logger.error(f"Failed to send invoice {invoice.invoice_number} to accounting: {str(e)}")
            raise

    def _validate_invoice_ready(self, invoice: HubInvoice, items: list) -> Dict:
        """
        Validate that invoice is ready to send

        Checks:
        - Invoice status is 'ready'
        - All items are mapped
        - All items have GL accounts
        - Not already sent

        Args:
            invoice: HubInvoice instance
            items: List of HubInvoiceItem instances

        Returns:
            Dict with "ready" bool and "errors" list
        """
        errors = []

        # Check if already sent
        if invoice.sent_to_inventory and invoice.sent_to_accounting:
            errors.append("Invoice already sent to both systems")

        # Check status
        if invoice.status not in ['ready', 'partial']:
            errors.append(f"Invoice status is '{invoice.status}', must be 'ready' or 'partial'")

        # Check items exist
        if not items:
            errors.append("Invoice has no items")

        # Check all items are mapped
        unmapped_items = [item for item in items if not item.is_mapped]
        if unmapped_items:
            errors.append(f"{len(unmapped_items)} items are not mapped")

        # Check all items have GL accounts
        # For expense-only items (no inventory_category), only gl_cogs_account is required
        # For inventory items, both gl_asset_account and gl_cogs_account are required
        items_without_gl = [
            item for item in items
            if item.is_mapped and (
                not item.gl_cogs_account or
                (item.inventory_category and not item.gl_asset_account)
            )
        ]
        if items_without_gl:
            errors.append(f"{len(items_without_gl)} items are missing GL account mappings")

        return {
            "ready": len(errors) == 0,
            "errors": errors
        }

    async def retry_failed_send(self, invoice_id: int, db: Session, retry_system: str = 'both') -> Dict:
        """
        Retry sending to systems that previously failed

        Args:
            invoice_id: ID of the HubInvoice to retry
            db: Database session
            retry_system: Which system to retry ('inventory', 'accounting', or 'both')

        Returns:
            Result dict from send operation
        """
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        items = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id
        ).all()

        logger.info(f"Retrying send for invoice {invoice.invoice_number} (system: {retry_system})")

        results = {
            "success": False,
            "inventory_sent": invoice.sent_to_inventory,
            "accounting_sent": invoice.sent_to_accounting,
            "inventory_id": invoice.inventory_invoice_id,
            "journal_entry_id": invoice.accounting_je_id,
            "errors": []
        }

        try:
            # Retry inventory if needed
            if retry_system in ['inventory', 'both'] and not invoice.sent_to_inventory:
                inventory_result = await self._send_to_inventory(invoice, items, db)
                results["inventory_sent"] = True
                results["inventory_id"] = inventory_result.get("inventory_invoice_id")

            # Retry accounting if needed
            if retry_system in ['accounting', 'both'] and not invoice.sent_to_accounting:
                accounting_result = await self._send_to_accounting(invoice, items, db)
                results["accounting_sent"] = True
                results["journal_entry_id"] = accounting_result.get("journal_entry_id")

            # Update status
            if results["inventory_sent"] and results["accounting_sent"]:
                invoice.status = 'sent'
            elif results["inventory_sent"] or results["accounting_sent"]:
                invoice.status = 'partial'

            db.commit()

            results["success"] = results["inventory_sent"] and results["accounting_sent"]

        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"Retry failed for invoice {invoice.invoice_number}: {str(e)}")

        return results


# Singleton instance
_auto_send_service = None


def get_auto_send_service(
    inventory_sender: InventorySenderService,
    accounting_sender: AccountingSenderService
) -> AutoSendService:
    """Get or create auto-send service singleton"""
    global _auto_send_service
    if _auto_send_service is None:
        _auto_send_service = AutoSendService(inventory_sender, accounting_sender)
    return _auto_send_service
