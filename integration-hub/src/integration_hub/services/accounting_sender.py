"""
Accounting Sender Service

Sends journal entries to the Accounting system via API.
Constructs journal entry with Dr./Cr. lines for inventory purchases.
"""

import httpx
import logging
from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)


class AccountingSenderService:
    """Service for sending journal entries to the Accounting system"""

    def __init__(self, accounting_api_url: str):
        """
        Initialize the service

        Args:
            accounting_api_url: Base URL for accounting API (e.g., http://accounting-app:8000/api)
        """
        self.accounting_api_url = accounting_api_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)

        # GL Account for Accounts Payable (credit side)
        self.AP_ACCOUNT = 2010  # Accounts Payable

    async def send_journal_entry(self, invoice: HubInvoice, items: List[HubInvoiceItem], db: Session) -> Dict:
        """
        Send journal entry to accounting system

        Journal Entry Structure:
        Dr. Inventory Asset Accounts (by category)  $XXX.XX
        Dr. Inventory Asset Accounts (by category)  $XXX.XX
            Cr. Accounts Payable (2010)                 $TOTAL

        Args:
            invoice: HubInvoice model instance
            items: List of HubInvoiceItem instances
            db: Database session for updating status

        Returns:
            Dict with success status and journal_entry_id

        Raises:
            Exception: If sending fails
        """
        try:
            # Build payload for accounting system
            payload = self._build_journal_entry_payload(invoice, items)

            logger.info(f"Sending journal entry for invoice {invoice.invoice_number} to accounting system")

            # POST to accounting API
            response = await self.client.post(
                f"{self.accounting_api_url}/journal-entries/from-hub",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            response.raise_for_status()
            result = response.json()

            # Update invoice with accounting reference
            invoice.sent_to_accounting = True
            invoice.accounting_je_id = result.get('journal_entry_id')
            invoice.accounting_sync_at = datetime.utcnow()
            invoice.accounting_error = None

            db.commit()

            logger.info(f"Successfully sent JE for invoice {invoice.invoice_number} to accounting. JE ID: {result.get('journal_entry_id')}")

            return {
                "success": True,
                "journal_entry_id": result.get('journal_entry_id'),
                "message": "Journal entry sent to accounting system"
            }

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error sending to accounting: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)

            invoice.accounting_error = error_msg
            db.commit()

            raise Exception(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Request error sending to accounting: {str(e)}"
            logger.error(error_msg)

            invoice.accounting_error = error_msg
            db.commit()

            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error sending to accounting: {str(e)}"
            logger.error(error_msg)

            invoice.accounting_error = error_msg
            db.commit()

            raise Exception(error_msg)

    def _build_journal_entry_payload(self, invoice: HubInvoice, items: List[HubInvoiceItem]) -> Dict:
        """
        Build the journal entry payload for accounting system

        Expected accounting API payload format:
        {
            "entry_date": "2025-10-19",
            "description": "Invoice INV-12345 from US Foods",
            "reference_number": "INV-12345",
            "source": "hub",
            "hub_invoice_id": 123,
            "lines": [
                {
                    "account_id": 1418,  # Poultry Inventory (Asset)
                    "debit": 87.50,
                    "credit": 0.00,
                    "description": "Chicken Breast"
                },
                {
                    "account_id": 1417,  # Beef Inventory (Asset)
                    "debit": 150.00,
                    "credit": 0.00,
                    "description": "Ground Beef"
                },
                {
                    "account_id": 2010,  # Accounts Payable (Liability)
                    "debit": 0.00,
                    "credit": 237.50,
                    "description": "AP - US Foods"
                }
            ]
        }
        """
        payload = {
            "entry_date": invoice.invoice_date.isoformat() if invoice.invoice_date else datetime.utcnow().date().isoformat(),
            "description": f"Invoice {invoice.invoice_number} from {invoice.vendor_name}",
            "reference_number": invoice.invoice_number,
            "source": "hub",
            "hub_invoice_id": invoice.id,
            "lines": []
        }

        # Group items by GL asset account (debit side)
        account_totals = {}
        for item in items:
            if not item.is_mapped or not item.gl_asset_account:
                logger.warning(f"Skipping unmapped or incomplete item: {item.item_description}")
                continue

            account_id = item.gl_asset_account
            if account_id not in account_totals:
                account_totals[account_id] = {
                    "amount": Decimal('0.00'),
                    "descriptions": []
                }

            account_totals[account_id]["amount"] += Decimal(str(item.line_total))
            account_totals[account_id]["descriptions"].append(item.item_description)

        # Add debit lines (inventory asset accounts)
        total_debits = Decimal('0.00')
        for account_id, data in account_totals.items():
            amount = float(data["amount"])
            description = ", ".join(data["descriptions"][:3])  # First 3 items
            if len(data["descriptions"]) > 3:
                description += f" (+{len(data['descriptions']) - 3} more)"

            payload["lines"].append({
                "account_id": account_id,
                "debit": amount,
                "credit": 0.00,
                "description": description
            })

            total_debits += data["amount"]

        # Add credit line (accounts payable)
        payload["lines"].append({
            "account_id": self.AP_ACCOUNT,
            "debit": 0.00,
            "credit": float(total_debits),
            "description": f"AP - {invoice.vendor_name}"
        })

        logger.debug(f"Built journal entry payload with {len(payload['lines'])} lines, total: ${total_debits}")

        # Validate debits = credits
        total_credits = Decimal(str(payload["lines"][-1]["credit"]))
        if abs(total_debits - total_credits) > Decimal('0.01'):
            raise ValueError(f"Journal entry unbalanced: Dr ${total_debits} != Cr ${total_credits}")

        return payload

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
_accounting_sender = None


def get_accounting_sender(accounting_api_url: str) -> AccountingSenderService:
    """Get or create accounting sender singleton"""
    global _accounting_sender
    if _accounting_sender is None:
        _accounting_sender = AccountingSenderService(accounting_api_url)
    return _accounting_sender
