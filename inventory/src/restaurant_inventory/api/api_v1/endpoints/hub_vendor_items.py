"""
Hub Vendor Items API endpoints

These endpoints proxy to the Integration Hub to display vendor items.
Hub is the source of truth for vendor item data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models import User
from restaurant_inventory.services.hub_client import get_hub_client

logger = logging.getLogger(__name__)

router = APIRouter()


class VendorItemCreate(BaseModel):
    """Create vendor item request - maps Inventory fields to Hub fields"""
    vendor_id: int
    master_item_id: Optional[int] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: str
    purchase_unit_id: int
    conversion_factor: float = 1.0
    minimum_order_quantity: Optional[float] = None
    lead_time_days: Optional[int] = None
    is_preferred: bool = False
    notes: Optional[str] = None
    is_active: bool = True


class VendorItemUpdate(BaseModel):
    """Update vendor item request"""
    master_item_id: Optional[int] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: Optional[str] = None
    purchase_unit_id: Optional[int] = None
    conversion_factor: Optional[float] = None
    minimum_order_quantity: Optional[float] = None
    lead_time_days: Optional[int] = None
    is_preferred: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


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


async def get_unit_info(db: Session, unit_id: int) -> Dict[str, Any]:
    """Look up unit name and abbreviation from local database."""
    from restaurant_inventory.models import UnitOfMeasure
    unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == unit_id).first()
    if unit:
        return {"name": unit.name, "abbreviation": unit.abbreviation}
    return {"name": None, "abbreviation": None}


async def get_master_item_name(db: Session, item_id: int) -> Optional[str]:
    """Look up master item name from local database."""
    from restaurant_inventory.models import Item
    item = db.query(Item).filter(Item.id == item_id).first()
    return item.name if item else None


async def get_hub_vendor_id(inventory_vendor_id: int) -> Optional[int]:
    """
    Map Inventory vendor ID to Hub vendor ID.
    Hub vendors have an inventory_vendor_id field that references Inventory's vendor.id.
    """
    import httpx
    from restaurant_inventory.services.hub_client import HUB_API_URL

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HUB_API_URL}/api/vendors/")
            if response.status_code == 200:
                vendors = response.json()
                for v in vendors:
                    if v.get('inventory_vendor_id') == inventory_vendor_id:
                        return v.get('id')
    except Exception as e:
        logger.error(f"Error looking up Hub vendor: {str(e)}")

    return None


@router.post("/")
async def create_hub_vendor_item(
    item_data: VendorItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new vendor item in Hub.
    Maps Inventory vendor_id to Hub vendor_id.
    Looks up unit and master item names from local database.
    """
    hub_client = get_hub_client()

    try:
        # Map Inventory vendor_id to Hub vendor_id
        hub_vendor_id = await get_hub_vendor_id(item_data.vendor_id)
        if not hub_vendor_id:
            raise HTTPException(
                status_code=400,
                detail=f"Vendor ID {item_data.vendor_id} not found in Hub. Vendor may need to be synced first."
            )

        # Look up unit info
        unit_info = await get_unit_info(db, item_data.purchase_unit_id)

        # Look up master item name if provided
        master_item_name = None
        if item_data.master_item_id:
            master_item_name = await get_master_item_name(db, item_data.master_item_id)

        # Map to Hub's expected field names
        hub_data = {
            "vendor_id": hub_vendor_id,  # Use Hub's vendor ID
            "inventory_master_item_id": item_data.master_item_id,
            "inventory_master_item_name": master_item_name,
            "vendor_sku": item_data.vendor_sku,
            "vendor_product_name": item_data.vendor_product_name,
            "purchase_unit_id": item_data.purchase_unit_id,
            "purchase_unit_name": unit_info["name"],
            "purchase_unit_abbr": unit_info["abbreviation"],
            "conversion_factor": item_data.conversion_factor,
            "is_preferred": item_data.is_preferred,
            "is_active": item_data.is_active,
            "notes": item_data.notes
        }

        result = await hub_client.create_vendor_item(hub_data)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating vendor item in Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error creating vendor item in Hub: {str(e)}"
        )


@router.put("/{vendor_item_id}")
async def update_hub_vendor_item(
    vendor_item_id: int,
    item_data: VendorItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a vendor item in Hub.
    """
    hub_client = get_hub_client()

    try:
        # Build update data, only including non-None fields
        hub_data = {}

        if item_data.master_item_id is not None:
            hub_data["inventory_master_item_id"] = item_data.master_item_id
            if item_data.master_item_id:
                hub_data["inventory_master_item_name"] = await get_master_item_name(db, item_data.master_item_id)
            else:
                hub_data["inventory_master_item_name"] = None

        if item_data.vendor_sku is not None:
            hub_data["vendor_sku"] = item_data.vendor_sku

        if item_data.vendor_product_name is not None:
            hub_data["vendor_product_name"] = item_data.vendor_product_name

        if item_data.purchase_unit_id is not None:
            hub_data["purchase_unit_id"] = item_data.purchase_unit_id
            unit_info = await get_unit_info(db, item_data.purchase_unit_id)
            hub_data["purchase_unit_name"] = unit_info["name"]
            hub_data["purchase_unit_abbr"] = unit_info["abbreviation"]

        if item_data.conversion_factor is not None:
            hub_data["conversion_factor"] = item_data.conversion_factor

        if item_data.is_preferred is not None:
            hub_data["is_preferred"] = item_data.is_preferred

        if item_data.is_active is not None:
            hub_data["is_active"] = item_data.is_active

        if item_data.notes is not None:
            hub_data["notes"] = item_data.notes

        result = await hub_client.update_vendor_item(vendor_item_id, hub_data)
        if not result:
            raise HTTPException(status_code=404, detail="Vendor item not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating vendor item {vendor_item_id} in Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error updating vendor item in Hub: {str(e)}"
        )


@router.delete("/{vendor_item_id}")
async def delete_hub_vendor_item(
    vendor_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete (soft-delete) a vendor item in Hub.
    """
    hub_client = get_hub_client()

    try:
        result = await hub_client.delete_vendor_item(vendor_item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Vendor item not found in Hub")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vendor item {vendor_item_id} in Hub: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Error deleting vendor item in Hub: {str(e)}"
        )


class VendorItemSync(BaseModel):
    """Sync data from Hub to create/update vendor item in Inventory"""
    hub_vendor_item_id: int
    inventory_vendor_id: int  # Inventory's vendor ID (not Hub's)
    master_item_id: Optional[int] = None
    vendor_sku: Optional[str] = None
    vendor_product_name: str
    purchase_unit_id: int
    conversion_factor: float = 1.0
    unit_price: Optional[float] = None
    is_preferred: bool = False
    notes: Optional[str] = None
    is_active: bool = True


@router.post("/sync")
async def sync_vendor_item_from_hub(
    sync_data: VendorItemSync,
    db: Session = Depends(get_db)
):
    """
    Sync a vendor item from Hub to Inventory.
    Called by Hub when vendor items are created/updated.
    No auth required - internal service call.

    Creates or updates the local vendor_items record based on hub_vendor_item_id.
    """
    from restaurant_inventory.models import VendorItem, Vendor

    try:
        # Verify vendor exists in Inventory
        vendor = db.query(Vendor).filter(Vendor.id == sync_data.inventory_vendor_id).first()
        if not vendor:
            raise HTTPException(
                status_code=400,
                detail=f"Vendor ID {sync_data.inventory_vendor_id} not found in Inventory"
            )

        # Look for existing vendor item by hub_vendor_item_id
        # We need to track this - add a column if not exists
        # For now, try to match by vendor_id + vendor_sku or vendor_product_name
        existing = None

        # First try to match by vendor and SKU
        if sync_data.vendor_sku:
            existing = db.query(VendorItem).filter(
                VendorItem.vendor_id == sync_data.inventory_vendor_id,
                VendorItem.vendor_sku == sync_data.vendor_sku
            ).first()

        # If no match by SKU, try by vendor and exact product name
        if not existing:
            existing = db.query(VendorItem).filter(
                VendorItem.vendor_id == sync_data.inventory_vendor_id,
                VendorItem.vendor_product_name == sync_data.vendor_product_name
            ).first()

        if existing:
            # Update existing record
            existing.master_item_id = sync_data.master_item_id
            existing.vendor_sku = sync_data.vendor_sku
            existing.vendor_product_name = sync_data.vendor_product_name
            existing.purchase_unit_id = sync_data.purchase_unit_id
            existing.conversion_factor = sync_data.conversion_factor
            if sync_data.unit_price is not None:
                existing.unit_price = sync_data.unit_price
            existing.is_preferred = sync_data.is_preferred
            existing.notes = sync_data.notes
            existing.is_active = sync_data.is_active

            db.commit()
            db.refresh(existing)

            logger.info(f"Updated vendor item {existing.id} from Hub item {sync_data.hub_vendor_item_id}")
            return {
                "status": "updated",
                "inventory_vendor_item_id": existing.id,
                "hub_vendor_item_id": sync_data.hub_vendor_item_id
            }
        else:
            # Create new record
            new_item = VendorItem(
                vendor_id=sync_data.inventory_vendor_id,
                master_item_id=sync_data.master_item_id,
                vendor_sku=sync_data.vendor_sku,
                vendor_product_name=sync_data.vendor_product_name,
                purchase_unit_id=sync_data.purchase_unit_id,
                conversion_factor=sync_data.conversion_factor,
                unit_price=sync_data.unit_price,
                is_preferred=sync_data.is_preferred,
                notes=sync_data.notes,
                is_active=sync_data.is_active
            )

            db.add(new_item)
            db.commit()
            db.refresh(new_item)

            logger.info(f"Created vendor item {new_item.id} from Hub item {sync_data.hub_vendor_item_id}")
            return {
                "status": "created",
                "inventory_vendor_item_id": new_item.id,
                "hub_vendor_item_id": sync_data.hub_vendor_item_id
            }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error syncing vendor item from Hub: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing vendor item: {str(e)}"
        )


@router.post("/sync-delete")
async def sync_vendor_item_delete_from_hub(
    hub_vendor_item_id: int,
    inventory_vendor_id: int,
    vendor_sku: Optional[str] = None,
    vendor_product_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Sync a vendor item deletion from Hub to Inventory.
    Called by Hub when vendor items are deactivated/deleted.
    Soft-deletes by setting is_active=False.
    """
    from restaurant_inventory.models import VendorItem

    try:
        # Find the item to deactivate
        existing = None

        if vendor_sku:
            existing = db.query(VendorItem).filter(
                VendorItem.vendor_id == inventory_vendor_id,
                VendorItem.vendor_sku == vendor_sku
            ).first()

        if not existing and vendor_product_name:
            existing = db.query(VendorItem).filter(
                VendorItem.vendor_id == inventory_vendor_id,
                VendorItem.vendor_product_name == vendor_product_name
            ).first()

        if existing:
            existing.is_active = False
            db.commit()

            logger.info(f"Deactivated vendor item {existing.id} from Hub deletion")
            return {
                "status": "deactivated",
                "inventory_vendor_item_id": existing.id,
                "hub_vendor_item_id": hub_vendor_item_id
            }
        else:
            return {
                "status": "not_found",
                "hub_vendor_item_id": hub_vendor_item_id
            }

    except Exception as e:
        db.rollback()
        logger.error(f"Error syncing vendor item deletion from Hub: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing vendor item deletion: {str(e)}"
        )
