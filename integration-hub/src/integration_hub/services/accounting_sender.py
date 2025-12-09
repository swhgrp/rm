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
from sqlalchemy import create_engine, text

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

        # GL Account for Accounts Payable (credit side) - use account number for lookup
        self.AP_ACCOUNT_NUMBER = "2100"  # Accounts Payable

        # Create connection to accounting database for account lookups
        import os
        self.accounting_db_url = os.getenv(
            "ACCOUNTING_DATABASE_URL",
            "postgresql://accounting_user:Acc0unt1ng_Pr0d_2024!@accounting-db:5432/accounting_db"
        )
        self.accounting_engine = create_engine(self.accounting_db_url)

        # Cache for account number -> ID mappings
        self._account_id_cache = {}

    def _get_account_id(self, account_number: str) -> int:
        """
        Look up account database ID from account number
        Uses caching to minimize database queries

        Args:
            account_number: The account number string (e.g., "7165", "2100")

        Returns:
            int: The database ID of the account

        Raises:
            ValueError: If account not found
        """
        # Check cache first
        if account_number in self._account_id_cache:
            return self._account_id_cache[account_number]

        # Query accounting database
        with self.accounting_engine.connect() as conn:
            result = conn.execute(
                text("SELECT id FROM accounts WHERE account_number = :account_number"),
                {"account_number": account_number}
            )
            row = result.fetchone()

        if not row:
            raise ValueError(f"Account number {account_number} not found in accounting system")

        account_id = row[0]
        # Cache the result
        self._account_id_cache[account_number] = account_id
        logger.debug(f"Looked up account {account_number} -> ID {account_id}")

        return account_id

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
            # Build payload for accounting system (vendor bill format)
            logger.info(f"Building vendor bill payload for invoice {invoice.invoice_number}")
            payload = self._build_vendor_bill_payload(invoice, items)

            logger.info(f"Sending vendor bill for invoice {invoice.invoice_number} to accounting system")
            logger.info(f"Payload: {payload}")

            # POST to accounting API - vendor bills endpoint
            response = await self.client.post(
                f"{self.accounting_api_url}/vendor-bills/from-hub",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            response.raise_for_status()
            result = response.json()

            # Update invoice with accounting reference
            invoice.sent_to_accounting = True
            invoice.accounting_je_id = result.get('journal_entry_id')  # Still track JE for reference
            invoice.accounting_sync_at = datetime.utcnow()
            invoice.accounting_error = None

            db.commit()

            logger.info(f"Successfully sent bill for invoice {invoice.invoice_number} to accounting. Bill ID: {result.get('bill_id')}, JE ID: {result.get('journal_entry_id')}")

            return {
                "success": True,
                "bill_id": result.get('bill_id'),
                "journal_entry_id": result.get('journal_entry_id'),
                "message": "Vendor bill sent to accounting system"
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

    def _build_vendor_bill_payload(self, invoice: HubInvoice, items: List[HubInvoiceItem]) -> Dict:
        """
        Build the vendor bill payload for accounting system

        Expected accounting API payload format:
        {
            "vendor_name": "Gold Coast Linen Service",
            "bill_number": "1103/1009",
            "bill_date": "2025-11-03",
            "due_date": "2025-11-18",
            "total_amount": 111.74,
            "tax_amount": 0.00,
            "hub_invoice_id": 10,
            "location_id": 2,
            "location_name": "SW Grill",
            "lines": [
                {
                    "account_id": 123,  # Database ID (integer)
                    "amount": 111.74,
                    "description": "Linen Service"
                }
            ]
        }

        Note: Hub stores account_number strings (e.g., "7165", "2100"), but accounting API
        expects account database IDs (integers). This method handles the conversion.
        """
        payload = {
            "vendor_name": invoice.vendor_name,
            "bill_number": invoice.invoice_number,
            "bill_date": invoice.invoice_date.isoformat() if invoice.invoice_date else datetime.utcnow().date().isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "total_amount": float(invoice.total_amount),
            "tax_amount": float(invoice.tax_amount) if invoice.tax_amount else 0.00,
            "hub_invoice_id": invoice.id,
            "location_id": invoice.location_id,
            "location_name": invoice.location_name,
            "lines": []
        }

        # Group items by GL account
        # All purchases go directly to COGS/Expense accounts (periodic inventory method)
        # Inventory asset adjustments are made at month-end based on physical counts
        # Note: At this point we have account_number strings, will convert to IDs later
        account_number_totals = {}
        for item in items:
            if not item.is_mapped or not item.gl_cogs_account:
                logger.warning(f"Skipping unmapped or incomplete item: {item.item_description}")
                continue

            # Use COGS account directly for all purchases (periodic inventory method)
            # Convert to string since accounting DB stores account_number as VARCHAR
            account_number = str(item.gl_cogs_account)

            if account_number not in account_number_totals:
                account_number_totals[account_number] = {
                    "amount": Decimal('0.00'),
                    "descriptions": []
                }

            account_number_totals[account_number]["amount"] += Decimal(str(item.total_amount))
            account_number_totals[account_number]["descriptions"].append(item.item_description)

        # Calculate the sum of all line items
        # Note: Invoice items often already include tax as separate line items
        # (e.g., "State Sales Tax", "County Sales Tax") so we should NOT add tax again
        items_total = sum(data["amount"] for data in account_number_totals.values())
        invoice_total = Decimal(str(invoice.total_amount))
        invoice_tax = Decimal(str(invoice.tax_amount)) if invoice.tax_amount else Decimal('0.00')

        # Determine if tax is already included in items
        # If items_total is close to invoice_total, tax is already in items - don't add again
        # If items_total is close to invoice_total - tax, we need to add tax proportionally
        tax_already_in_items = abs(items_total - invoice_total) < Decimal('0.02')

        if tax_already_in_items:
            logger.info(f"Tax appears to be included in line items (items total ${items_total} ≈ invoice total ${invoice_total})")
        else:
            logger.info(f"Tax needs to be distributed (items total ${items_total}, invoice total ${invoice_total}, tax ${invoice_tax})")

        # Add bill lines (expense or asset accounts)
        # Convert account numbers to database IDs
        total_amount = Decimal('0.00')
        logger.info(f"Processing {len(account_number_totals)} account entries for vendor bill")

        for account_number, data in account_number_totals.items():
            # Look up the database ID for this account number
            logger.info(f"Looking up account ID for account_number: {account_number}")
            try:
                account_id = self._get_account_id(account_number)
                logger.info(f"Found account ID {account_id} for account_number {account_number}")
            except ValueError as e:
                logger.error(f"Cannot find account {account_number} in accounting system: {e}")
                raise ValueError(f"Cannot find account {account_number} in accounting system: {e}")

            line_subtotal = data["amount"]

            # Only add proportional tax if it's NOT already included in items
            if not tax_already_in_items and items_total != 0 and invoice_tax != 0:
                # Proportional tax: (line amount / subtotal) * total tax
                line_tax = (line_subtotal / items_total) * invoice_tax
                line_total = line_subtotal + line_tax
            else:
                line_total = line_subtotal

            description = ", ".join(data["descriptions"][:3])  # First 3 items
            if len(data["descriptions"]) > 3:
                description += f" (+{len(data['descriptions']) - 3} more)"

            payload["lines"].append({
                "account_id": account_id,  # Using the actual database ID (integer)
                "amount": float(line_total),
                "description": description
            })

            total_amount += line_total

        logger.debug(f"Built vendor bill payload with {len(payload['lines'])} lines, total: ${total_amount}")

        # Validate total matches invoice total
        invoice_total = Decimal(str(invoice.total_amount))
        difference = total_amount - invoice_total

        # If there's a discrepancy, add an adjustment line to balance
        if abs(difference) > Decimal('0.01'):
            # Adjustment needed: negative if lines > invoice, positive if lines < invoice
            adjustment_amount = invoice_total - total_amount

            if difference > 0:
                logger.info(f"Lines exceed invoice by ${difference} - adding credit/discount adjustment of ${adjustment_amount}")
                adjustment_desc = "Credit / Discount Adjustment"
            else:
                logger.info(f"Lines under invoice by ${-difference} - adding minimum charge adjustment of ${adjustment_amount}")
                adjustment_desc = "Minimum Charge / Adjustment"

            # Use the most common GL account from the existing lines
            if account_number_totals:
                # Find the account with the highest total (most likely the primary expense account)
                primary_account = max(account_number_totals.keys(),
                                     key=lambda k: abs(account_number_totals[k]["amount"]))
                try:
                    adjustment_account_id = self._get_account_id(primary_account)
                except ValueError:
                    # Fallback: use the first account from the lines
                    adjustment_account_id = payload["lines"][0]["account_id"] if payload["lines"] else None

                if adjustment_account_id:
                    payload["lines"].append({
                        "account_id": adjustment_account_id,
                        "amount": float(adjustment_amount),
                        "description": adjustment_desc
                    })
                    total_amount += adjustment_amount
                    logger.info(f"Added adjustment line: ${adjustment_amount} to account {primary_account}")

        return payload

    async def close(self):
        """Close HTTP client and database connections"""
        await self.client.aclose()
        self.accounting_engine.dispose()


# Singleton instance
_accounting_sender = None


def get_accounting_sender(accounting_api_url: str) -> AccountingSenderService:
    """Get or create accounting sender singleton"""
    global _accounting_sender
    if _accounting_sender is None:
        _accounting_sender = AccountingSenderService(accounting_api_url)
    return _accounting_sender
