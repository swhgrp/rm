"""
Hub Invoice API endpoints

These endpoints proxy to the Integration Hub to display invoices.
Hub is the source of truth for invoice data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List invoices from Hub (source of truth).

    This replaces the local invoice list for viewing purposes.
    Invoices are still copied to local DB when approved for inventory tracking.
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
            sent_to_inventory=sent_to_inventory
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
