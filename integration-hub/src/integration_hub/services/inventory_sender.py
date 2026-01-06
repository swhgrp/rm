"""
Inventory Sender Service

Sends invoices to the Inventory system via API.
Constructs invoice payload with line items and posts to inventory system.
"""

import httpx
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

logger = logging.getLogger(__name__)


class InventorySenderService:
    """Service for sending invoices to the Inventory system"""

    def __init__(self, inventory_api_url: str):
        """
        Initialize the service

        Args:
            inventory_api_url: Base URL for inventory API (e.g., http://inventory-app:8000/api)
        """
        self.inventory_api_url = inventory_api_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_invoice(self, invoice: HubInvoice, items: List[HubInvoiceItem], db: Session) -> Dict:
        """
        Send invoice to inventory system

        Args:
            invoice: HubInvoice model instance
            items: List of HubInvoiceItem instances
            db: Database session for updating status

        Returns:
            Dict with success status and inventory_invoice_id

        Raises:
            Exception: If sending fails
        """
        try:
            # Build payload for inventory system
            payload = self._build_inventory_payload(invoice, items)

            logger.info(f"Sending invoice {invoice.invoice_number} to inventory system")

            # POST to inventory API - endpoint is at /hub-invoices/from-hub
            response = await self.client.post(
                f"{self.inventory_api_url}/hub-invoices/from-hub",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            response.raise_for_status()
            result = response.json()

            # Check for duplicate response
            if result.get('status') == 'duplicate':
                logger.warning(f"Duplicate invoice detected: {invoice.invoice_number} - {result.get('message')}")

                # Mark as sent since it already exists in inventory
                invoice.sent_to_inventory = True
                invoice.inventory_invoice_id = result.get('existing_invoice_id')
                invoice.inventory_sync_at = datetime.utcnow()
                invoice.inventory_error = f"Duplicate: {result.get('message')}"

                db.commit()

                return {
                    "success": True,
                    "duplicate": True,
                    "inventory_invoice_id": result.get('existing_invoice_id'),
                    "message": result.get('message')
                }

            # Update invoice with inventory reference
            invoice.sent_to_inventory = True
            invoice.inventory_invoice_id = result.get('invoice_id')
            invoice.inventory_sync_at = datetime.utcnow()
            invoice.inventory_error = None

            db.commit()

            logger.info(f"Successfully sent invoice {invoice.invoice_number} to inventory. ID: {result.get('invoice_id')}")

            return {
                "success": True,
                "inventory_invoice_id": result.get('invoice_id'),
                "message": "Invoice sent to inventory system"
            }

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error sending to inventory: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)

            invoice.inventory_error = error_msg
            db.commit()

            raise Exception(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Request error sending to inventory: {str(e)}"
            logger.error(error_msg)

            invoice.inventory_error = error_msg
            db.commit()

            raise Exception(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error sending to inventory: {str(e)}"
            logger.error(error_msg)

            invoice.inventory_error = error_msg
            db.commit()

            raise Exception(error_msg)

    def _build_inventory_payload(self, invoice: HubInvoice, items: List[HubInvoiceItem]) -> Dict:
        """
        Build the payload for inventory system API

        Expected inventory API payload format:
        {
            "vendor_name": "US Foods",
            "invoice_number": "INV-12345",
            "invoice_date": "2025-10-19",
            "due_date": "2025-11-19",
            "total_amount": 1234.56,
            "location_id": 4,
            "source": "hub",
            "hub_invoice_id": 123,
            "items": [
                {
                    "inventory_item_id": 45,
                    "description": "Chicken Breast",
                    "quantity": 25.0,
                    "unit_of_measure": "LB",
                    "unit_price": 3.50,
                    "line_total": 87.50,
                    "category": "poultry"
                }
            ]
        }
        """
        payload = {
            "vendor_name": invoice.vendor_name,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "total_amount": float(invoice.total_amount),
            "location_id": invoice.location_id,  # Required for proper routing
            "source": "hub",
            "hub_invoice_id": invoice.id,
            "items": []
        }

        # Add line items
        for item in items:
            if not item.is_mapped:
                logger.warning(f"Skipping unmapped item: {item.item_description}")
                continue

            item_payload = {
                "inventory_item_id": item.inventory_item_id,  # This is actually vendor_item_id
                "item_code": item.item_code,  # Vendor's item code from invoice
                "description": item.item_description,
                "quantity": float(item.quantity),
                "unit_of_measure": item.unit_of_measure,
                "pack_size": item.pack_size,  # Units per case (e.g., 12 for a 12-pack)
                "unit_price": float(item.unit_price),
                "line_total": float(item.line_total),
                "category": item.inventory_category
            }

            payload["items"].append(item_payload)

        logger.debug(f"Built inventory payload with {len(payload['items'])} items")

        return payload

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
_inventory_sender = None


def get_inventory_sender(inventory_api_url: str) -> InventorySenderService:
    """Get or create inventory sender singleton"""
    global _inventory_sender
    if _inventory_sender is None:
        _inventory_sender = InventorySenderService(inventory_api_url)
    return _inventory_sender
