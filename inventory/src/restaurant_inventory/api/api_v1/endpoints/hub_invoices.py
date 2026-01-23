"""
Hub Invoice API endpoints

These endpoints proxy to the Integration Hub to display invoices.
Hub is the source of truth for invoice data.

Also provides endpoint to receive invoice notifications from Hub.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import date
import logging

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models import User
from restaurant_inventory.services.hub_client import get_hub_client

logger = logging.getLogger(__name__)

router = APIRouter()


# Health check must be before parametric routes
@router.get("/health")
async def hub_health():
    """
    Check Hub connectivity.
    No authentication required for health check.
    """
    hub_client = get_hub_client()

    try:
        is_healthy = await hub_client.health_check()
        return {
            "hub_reachable": is_healthy,
            "status": "ok" if is_healthy else "unreachable"
        }
    except Exception as e:
        return {
            "hub_reachable": False,
            "status": "error",
            "error": str(e)
        }


@router.get("/")
async def list_hub_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    vendor_name: Optional[str] = None,
    location_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sent_to_inventory: Optional[bool] = None,
    has_inventory_items: Optional[bool] = Query(True, description="Filter to inventory items only (default True, excludes expense-only invoices)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List invoices from Hub (source of truth).

    This replaces the local invoice list for viewing purposes.
    Invoices are still copied to local DB when approved for inventory tracking.

    By default, only shows invoices with inventory items (has_inventory_items=True).
    Expense-only invoices (Cozzini, Palm Beach County, etc.) are excluded.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_invoices(
            page=page,
            page_size=page_size,
            status=status,
            vendor_name=vendor_name,
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            sent_to_inventory=sent_to_inventory,
            has_inventory_items=has_inventory_items
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching invoices from Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching invoices from Hub: {str(e)}"
        )


@router.get("/by-number/{invoice_number}")
async def lookup_hub_invoice(
    invoice_number: str,
    vendor_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Look up invoice by number in Hub.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_invoice_by_number(invoice_number, vendor_name)
        if not result:
            raise HTTPException(status_code=404, detail="Invoice not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error looking up invoice in Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error looking up invoice in Hub: {str(e)}"
        )


@router.get("/{invoice_id}")
async def get_hub_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get invoice details from Hub (source of truth).

    Returns full invoice with all line items and mapping info.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_invoice(invoice_id)
        if not result:
            raise HTTPException(status_code=404, detail="Invoice not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching invoice {invoice_id} from Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching invoice from Hub: {str(e)}"
        )


@router.get("/{invoice_id}/items")
async def get_hub_invoice_items(
    invoice_id: int,
    mapped_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get invoice line items from Hub.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_invoice_items(invoice_id, mapped_only=mapped_only)
        return result
    except Exception as e:
        logger.error(f"Error fetching invoice items from Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching invoice items from Hub: {str(e)}"
        )


@router.post("/from-hub")
def receive_invoice_from_hub(
    invoice_data: Dict,
    db: Session = Depends(get_db)
):
    """
    Receive invoice data from Integration Hub.

    Hub is the source of truth for invoices and vendor items.
    Hub's LocationCostUpdaterService handles all cost updates directly to Inventory DB.

    This endpoint acknowledges receipt for logging/tracking purposes.

    No authentication required - internal service communication.

    Expected payload from Hub:
    {
        "vendor_name": "Gordon Food Service",
        "invoice_number": "945142905",
        "invoice_date": "2026-01-05",
        "total_amount": 165.73,
        "location_id": 3,
        "hub_invoice_id": 552,
        "items": [...]
    }
    """
    try:
        invoice_number = invoice_data.get("invoice_number")
        location_id = invoice_data.get("location_id")
        hub_invoice_id = invoice_data.get("hub_invoice_id")
        items_data = invoice_data.get("items", [])

        logger.info(f"Received invoice {invoice_number} from Hub (hub_id: {hub_invoice_id}, location: {location_id}, items: {len(items_data)})")

        # Hub's LocationCostUpdaterService handles all cost updates directly to Inventory DB.
        # This endpoint just acknowledges receipt.

        return {
            "success": True,
            "invoice_id": hub_invoice_id,
            "invoice_number": invoice_number,
            "message": f"Invoice received. Cost updates handled by Hub's LocationCostUpdaterService.",
            "items_received": len(items_data)
        }

    except Exception as e:
        logger.error(f"Error receiving invoice from Hub: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error receiving invoice from Hub: {str(e)}"
        )
