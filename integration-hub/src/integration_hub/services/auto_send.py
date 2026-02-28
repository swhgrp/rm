"""
Auto-Send Orchestrator Service

Orchestrates sending invoices to both Inventory and Accounting systems.
Handles parallel sending, error handling, and status updates.

Location-Aware Costing:
After sending to Inventory, also updates MasterItemLocationCost table
with weighted average costs for each item at the invoice's location.
"""

import asyncio
import logging
from typing import Dict, Tuple
from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.services.inventory_sender import InventorySenderService
from integration_hub.services.accounting_sender import AccountingSenderService
from integration_hub.services.location_cost_updater import LocationCostUpdaterService
from integration_hub.services.vendor_item_review import check_uom_completeness

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
        validation_result = self._validate_invoice_ready(invoice, items, db)
        if not validation_result["ready"]:
            return {
                "success": False,
                "inventory_sent": False,
                "accounting_sent": False,
                "inventory_id": None,
                "journal_entry_id": None,
                "errors": validation_result["errors"],
                "incomplete_uom_items": validation_result.get("incomplete_uom_items", [])
            }

        logger.info(f"Auto-sending invoice {invoice.invoice_number} (ID: {invoice_id})")

        # Determine which systems need this invoice
        # Send to inventory only if at least one item is a real inventory item (not expense-only)
        expense_methods = {'vendor_expense_rule', 'expense_mapping'}
        has_inventory_items = any(
            item.inventory_category and item.inventory_category != 'Uncategorized'
            and item.mapping_method not in expense_methods
            for item in items
        )
        # Always send to accounting (all items have GL accounts)
        needs_accounting = True

        logger.info(f"Invoice {invoice.invoice_number}: has_inventory_items={has_inventory_items}, needs_accounting={needs_accounting}")

        # Check if already sent - prevent duplicates
        # Only send if not already sent to that system
        send_to_inventory = has_inventory_items and not invoice.sent_to_inventory
        send_to_accounting = needs_accounting and not invoice.sent_to_accounting

        if invoice.sent_to_inventory and invoice.sent_to_accounting:
            logger.info(f"Invoice {invoice.invoice_number} already sent to both systems. Skipping.")
            return {
                "success": True,
                "inventory_sent": True,
                "accounting_sent": True,
                "inventory_id": None,
                "journal_entry_id": invoice.accounting_je_id,
                "errors": [],
                "message": "Invoice already sent to all required systems"
            }

        if send_to_inventory:
            logger.info(f"Sending invoice {invoice.invoice_number} to inventory")
        else:
            if has_inventory_items:
                logger.info(f"Skipping inventory for invoice {invoice.invoice_number} - already sent")

        if send_to_accounting:
            logger.info(f"Sending invoice {invoice.invoice_number} to accounting")
        else:
            if needs_accounting:
                logger.info(f"Skipping accounting for invoice {invoice.invoice_number} - already sent")

        # Send to appropriate systems in parallel
        tasks = []

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

        # If we skipped a system because it doesn't need it OR it was already sent, mark as "done"
        # Note: Don't overwrite sent flags here - they're set by the individual send methods
        if not send_to_inventory:
            # System was skipped because either:
            # 1. No inventory items needed (has_inventory_items=False), OR
            # 2. Already sent previously (invoice.sent_to_inventory=True)
            inventory_sent = True  # Consider it "done" for status purposes
            # NOTE: Do NOT mark sent_to_inventory=True for expense-only invoices
            # The UI will check if all items are expenses and show "N/A" accordingly
        if not send_to_accounting:
            # System was skipped because already sent previously (invoice.sent_to_accounting=True)
            accounting_sent = True  # Consider it "done" for status purposes
            # Note: needs_accounting is always True, so this only happens if already sent

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
        Send to inventory system and update location costs.

        After successfully sending to Inventory, updates the MasterItemLocationCost
        table with weighted average costs for each item at the invoice's location.

        Args:
            invoice: HubInvoice instance
            items: List of HubInvoiceItem instances
            db: Database session

        Returns:
            Result dict from inventory sender with cost update stats

        Raises:
            Exception: If sending fails
        """
        try:
            result = await self.inventory_sender.send_invoice(invoice, items, db)

            # After successful send, update location costs
            if result.get('success') and invoice.location_id:
                try:
                    cost_updater = LocationCostUpdaterService(db)
                    cost_result = cost_updater.update_costs_from_invoice(invoice.id)
                    result['cost_update'] = cost_result
                    logger.info(f"Location costs updated for invoice {invoice.invoice_number}: "
                              f"{cost_result.get('costs_updated', 0)} updated, "
                              f"{cost_result.get('costs_created', 0)} created")
                except Exception as cost_error:
                    # Log but don't fail the whole operation
                    logger.warning(f"Failed to update location costs for invoice {invoice.invoice_number}: {str(cost_error)}")
                    result['cost_update_error'] = str(cost_error)

            return result
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

    def _validate_invoice_ready(self, invoice: HubInvoice, items: list, db: Session) -> Dict:
        """
        Validate that invoice is ready to send

        Checks:
        - Invoice status is 'ready'
        - All items are mapped
        - All items have GL accounts
        - All mapped vendor items have complete UOM
        - Not already sent

        Args:
            invoice: HubInvoice instance
            items: List of HubInvoiceItem instances
            db: Database session

        Returns:
            Dict with "ready" bool, "errors" list, and "incomplete_uom_items" list
        """
        errors = []
        incomplete_uom_items = []

        # Check if already sent
        if invoice.sent_to_inventory and invoice.sent_to_accounting:
            errors.append("Invoice already sent to both systems")

        # Check review flag
        if getattr(invoice, 'needs_review', False) and invoice.needs_review:
            errors.append(f"Invoice is flagged for review ({invoice.review_reason or 'unknown reason'}). "
                         "Approve or clear review flags before sending.")

        # Check status
        # Allow 'ready', 'partial' (for initial send), and 'error' (for retry)
        if invoice.status not in ['ready', 'partial', 'error']:
            errors.append(f"Invoice status is '{invoice.status}', must be 'ready', 'partial', or 'error'")

        # Check location is set (required for proper routing)
        if not invoice.location_id:
            errors.append("Invoice must have a location assigned before sending")

        # Check items exist
        if not items:
            errors.append("Invoice has no items")

        # Check all items are mapped
        unmapped_items = [item for item in items if not item.is_mapped]
        if unmapped_items:
            errors.append(f"{len(unmapped_items)} items are not mapped")

        # Check all items have GL accounts
        # For expense items (vendor_expense_rule, expense_mapping, or no category), only gl_cogs_account is required
        # For inventory items, both gl_asset_account and gl_cogs_account are required
        expense_methods = {'vendor_expense_rule', 'expense_mapping'}
        items_without_gl = [
            item for item in items
            if item.is_mapped and (
                not item.gl_cogs_account or
                (item.inventory_category and item.inventory_category != 'Uncategorized'
                 and item.mapping_method not in expense_methods
                 and not item.gl_asset_account)
            )
        ]
        if items_without_gl:
            errors.append(f"{len(items_without_gl)} items are missing GL account mappings")

        # Check all mapped vendor items have complete UOM
        # Required for accurate inventory costing
        for item in items:
            if item.is_mapped and item.inventory_item_id:
                vendor_item = db.query(HubVendorItem).filter(
                    HubVendorItem.id == item.inventory_item_id
                ).first()

                if vendor_item:
                    uom_check = check_uom_completeness(vendor_item)
                    if not uom_check['is_complete']:
                        incomplete_uom_items.append({
                            'invoice_item_id': item.id,
                            'item_description': item.item_description,
                            'vendor_item_id': vendor_item.id,
                            'vendor_product_name': vendor_item.vendor_product_name,
                            'missing_fields': uom_check['missing_fields']
                        })

        if incomplete_uom_items:
            errors.append(f"{len(incomplete_uom_items)} items have incomplete UOM (missing size/unit/container data)")

        # Check all mapped vendor items are linked to a master item in Inventory
        missing_master_items = []
        for item in items:
            if item.is_mapped and item.inventory_item_id:
                vendor_item = db.query(HubVendorItem).filter(
                    HubVendorItem.id == item.inventory_item_id
                ).first()

                if vendor_item and not vendor_item.inventory_master_item_id:
                    missing_master_items.append({
                        'invoice_item_id': item.id,
                        'item_description': item.item_description,
                        'vendor_item_id': vendor_item.id,
                        'vendor_product_name': vendor_item.vendor_product_name
                    })

        if missing_master_items:
            errors.append(f"{len(missing_master_items)} vendor items not linked to a master item in Inventory")

        return {
            "ready": len(errors) == 0,
            "errors": errors,
            "incomplete_uom_items": incomplete_uom_items
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

        # Validate before retry - same checks as initial send
        validation_result = self._validate_invoice_ready(invoice, items, db)
        if not validation_result["ready"]:
            return {
                "success": False,
                "inventory_sent": invoice.sent_to_inventory,
                "accounting_sent": invoice.sent_to_accounting,
                "inventory_id": invoice.inventory_invoice_id,
                "journal_entry_id": invoice.accounting_je_id,
                "errors": validation_result["errors"],
                "incomplete_uom_items": validation_result.get("incomplete_uom_items", [])
            }

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
