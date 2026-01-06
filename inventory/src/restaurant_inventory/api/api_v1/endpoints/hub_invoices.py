"""
Hub Invoice API endpoints

These endpoints proxy to the Integration Hub to display invoices.
Hub is the source of truth for invoice data.

Also provides endpoint to receive invoice data from Hub for vendor cost updates.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import date, datetime
from decimal import Decimal
import logging

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models import User, VendorItem, MasterItem
from restaurant_inventory.models.master_item_location_cost import MasterItemLocationCost
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
    Receive invoice data from Integration Hub for vendor cost updates.

    Hub is the source of truth for invoices. This endpoint:
    1. Updates vendor item prices based on invoice line items
    2. Updates master item location costs
    3. Records price history (if applicable)

    No authentication required - internal service communication.

    Expected payload from Hub:
    {
        "vendor_name": "Gordon Food Service",
        "invoice_number": "945142905",
        "invoice_date": "2026-01-05",
        "total_amount": 165.73,
        "location_id": 3,
        "hub_invoice_id": 552,
        "items": [
            {
                "inventory_item_id": 51,  # Hub vendor item ID -> maps to Inventory vendor_item
                "item_code": "3852120",
                "description": "Case Ice Cream...",
                "quantity": 1,
                "unit_price": 39.55,
                "line_total": 39.55,
                "category": "Food - Dairy"
            }
        ]
    }
    """
    try:
        invoice_number = invoice_data.get("invoice_number")
        location_id = invoice_data.get("location_id")
        hub_invoice_id = invoice_data.get("hub_invoice_id")
        items_data = invoice_data.get("items", [])

        logger.info(f"Receiving invoice {invoice_number} from Hub (hub_id: {hub_invoice_id}, location: {location_id})")

        updated_count = 0
        skipped_count = 0
        cost_updates = []

        for item in items_data:
            hub_vendor_item_id = item.get("inventory_item_id")
            unit_price = item.get("unit_price")
            item_code = item.get("item_code")
            description = item.get("description")

            if not hub_vendor_item_id or not unit_price:
                skipped_count += 1
                continue

            # Find the Inventory vendor_item that corresponds to Hub's vendor item
            # Hub stores inventory_vendor_item_id which maps to our vendor_items.id
            vendor_item = db.query(VendorItem).filter(VendorItem.id == hub_vendor_item_id).first()

            if not vendor_item:
                # Try to find by vendor_sku (item_code) as fallback
                if item_code:
                    vendor_item = db.query(VendorItem).filter(
                        VendorItem.vendor_sku == item_code
                    ).first()

            if vendor_item:
                old_price = vendor_item.unit_price
                vendor_item.unit_price = Decimal(str(unit_price))
                vendor_item.last_price = Decimal(str(unit_price))
                vendor_item.price_updated_at = datetime.utcnow()

                # Update master item's location cost if linked
                if vendor_item.master_item_id and location_id:
                    location_cost = db.query(MasterItemLocationCost).filter(
                        MasterItemLocationCost.master_item_id == vendor_item.master_item_id,
                        MasterItemLocationCost.location_id == location_id
                    ).first()

                    if location_cost:
                        location_cost.current_cost = Decimal(str(unit_price))
                        location_cost.last_updated = datetime.utcnow()
                    else:
                        # Create location cost record
                        location_cost = MasterItemLocationCost(
                            master_item_id=vendor_item.master_item_id,
                            location_id=location_id,
                            current_cost=Decimal(str(unit_price)),
                            last_updated=datetime.utcnow()
                        )
                        db.add(location_cost)

                cost_updates.append({
                    "vendor_item_id": vendor_item.id,
                    "item_code": item_code,
                    "old_price": float(old_price) if old_price else None,
                    "new_price": float(unit_price)
                })
                updated_count += 1
            else:
                logger.warning(f"Vendor item not found for hub_id={hub_vendor_item_id}, item_code={item_code}")
                skipped_count += 1

        db.commit()

        logger.info(f"Invoice {invoice_number} processed: {updated_count} items updated, {skipped_count} skipped")

        return {
            "success": True,
            "invoice_id": hub_invoice_id,
            "invoice_number": invoice_number,
            "message": f"Processed {updated_count} vendor item cost updates",
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "cost_updates": cost_updates
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing invoice from Hub: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing invoice from Hub: {str(e)}"
        )
