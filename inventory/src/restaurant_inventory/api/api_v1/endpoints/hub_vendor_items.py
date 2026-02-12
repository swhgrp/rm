"""
Hub Vendor Items API endpoints (Read-Only)

These endpoints proxy to the Integration Hub to display vendor items.
Hub is the source of truth for vendor item data.
All create/edit/delete operations must be done in Integration Hub.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models import User
from restaurant_inventory.services.hub_client import get_hub_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def hub_vendor_items_health():
    """
    Check Hub connectivity for vendor items.
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
async def list_hub_vendor_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    vendor_id: Optional[int] = None,
    master_item_id: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List vendor items from Hub (source of truth).
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_vendor_items(
            page=page,
            page_size=page_size,
            vendor_id=vendor_id,
            master_item_id=master_item_id,
            search=search,
            is_active=is_active
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching vendor items from Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching vendor items from Hub: {str(e)}"
        )


@router.get("/{vendor_item_id}")
async def get_hub_vendor_item(
    vendor_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get vendor item details from Hub.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_vendor_item(vendor_item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Vendor item not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vendor item {vendor_item_id} from Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching vendor item from Hub: {str(e)}"
        )


@router.get("/by-sku/{vendor_sku}")
async def lookup_hub_vendor_item_by_sku(
    vendor_sku: str,
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Look up vendor item by SKU in Hub.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.get_vendor_item_by_sku(vendor_sku, vendor_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Vendor item with SKU '{vendor_sku}' not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error looking up vendor item by SKU in Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error looking up vendor item in Hub: {str(e)}"
        )


# REMOVED (Feb 2026): POST/PUT/DELETE endpoints and helper functions removed.
# Hub is the sole source of truth for vendor items.
# Vendor items should only be created/edited/deleted in Integration Hub.
# The Inventory UI is now read-only for vendor item data.
