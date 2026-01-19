"""
POS Integration API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import List, Optional
from datetime import datetime, date

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.user import User
from restaurant_inventory.models.pos_sale import POSConfiguration, POSSale, POSSaleItem, POSItemMapping
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.recipe import Recipe
from restaurant_inventory.schemas.pos import (
    POSConfigurationCreate,
    POSConfigurationUpdate,
    POSConfigurationResponse,
    POSConnectionTest,
    POSSyncRequest,
    POSSyncResponse,
    POSSaleResponse,
    POSSaleItemResponse,
    POSItemMappingCreate,
    POSItemMappingUpdate,
    POSItemMappingResponse,
    UnmappedPOSItem
)
from restaurant_inventory.core.clover_client import CloverAPIClient
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.services.pos_sync import POSSyncService
from restaurant_inventory.services.inventory_deduction import InventoryDeductionService

router = APIRouter()


@router.get("/configurations", response_model=List[POSConfigurationResponse])
async def get_pos_configurations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all POS configurations"""
    configs = db.query(POSConfiguration).all()

    # Mask sensitive data
    for config in configs:
        config.api_key = "****" if config.api_key else None
        config.access_token = "****" if config.access_token else None

    return configs


@router.get("/configurations/{location_id}", response_model=POSConfigurationResponse)
async def get_pos_configuration(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get POS configuration for a specific location"""
    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Mask sensitive data
    config.api_key = "****" if config.api_key else None
    config.access_token = "****" if config.access_token else None

    return config


@router.post("/configurations", response_model=POSConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_pos_configuration(
    config: POSConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create POS configuration for a location"""

    # Check if configuration already exists for this location
    existing = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == config.location_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="POS configuration already exists for this location"
        )

    # Create configuration
    db_config = POSConfiguration(**config.dict())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="create",
        entity_type="pos_configuration",
        entity_id=db_config.id
    )

    # Mask sensitive data in response
    db_config.api_key = "****" if db_config.api_key else None
    db_config.access_token = "****" if db_config.access_token else None

    return db_config


@router.put("/configurations/{location_id}", response_model=POSConfigurationResponse)
async def update_pos_configuration(
    location_id: int,
    config_update: POSConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update POS configuration"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Update fields
    update_data = config_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_at = get_now()
    db.commit()
    db.refresh(config)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="update",
        entity_type="pos_configuration",
        entity_id=config.id,
        changes=update_data
    )

    # Mask sensitive data
    config.api_key = "****" if config.api_key else None
    config.access_token = "****" if config.access_token else None

    return config


@router.post("/configurations/{location_id}/test", response_model=POSConnectionTest)
async def test_pos_connection(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Test POS API connection"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    if not config.merchant_id or not config.access_token:
        raise HTTPException(
            status_code=400,
            detail="Missing merchant_id or access_token in configuration"
        )

    try:
        # Log what we're testing with (for debugging)
        print(f"Testing Clover connection:")
        print(f"  Merchant ID: {config.merchant_id}")
        print(f"  Environment: {config.api_environment}")
        print(f"  Token (first 10 chars): {config.access_token[:10] if config.access_token else 'None'}...")

        # Initialize Clover client
        client = CloverAPIClient(
            merchant_id=config.merchant_id,
            access_token=config.access_token,
            environment=config.api_environment
        )

        print(f"  Base URL: {client.base_url}")
        print(f"  Full URL: {client.base_url}/v3/merchants/{config.merchant_id}")

        # Test connection
        is_connected = await client.test_connection()

        if is_connected:
            return POSConnectionTest(
                success=True,
                message="Successfully connected to Clover POS",
                merchant_id=config.merchant_id
            )
        else:
            return POSConnectionTest(
                success=False,
                message="Failed to connect to Clover POS. Please check your credentials."
            )

    except Exception as e:
        print(f"Connection test exception: {str(e)}")
        return POSConnectionTest(
            success=False,
            message=f"Connection error: {str(e)}"
        )


@router.delete("/configurations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pos_configuration(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete POS configuration"""

    config = db.query(POSConfiguration).filter(
        POSConfiguration.location_id == location_id
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="POS configuration not found")

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="delete",
        entity_type="pos_configuration",
        entity_id=config.id
    )

    db.delete(config)
    db.commit()

    return None


@router.post("/sync/{location_id}", response_model=POSSyncResponse)
async def sync_pos_sales(
    location_id: int,
    sync_request: Optional[POSSyncRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Sync sales from POS for a specific location

    This will fetch orders from the POS system and import them into the database.
    """
    try:
        # Parse dates if provided
        start_date = None
        end_date = None
        limit = 100

        if sync_request:
            if sync_request.start_date:
                start_date = datetime.fromisoformat(sync_request.start_date).date()
            if sync_request.end_date:
                end_date = datetime.fromisoformat(sync_request.end_date).date()
            limit = sync_request.limit

        # Create sync service
        sync_service = POSSyncService(db)

        # Sync sales
        synced, skipped, errors = await sync_service.sync_sales(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        # Audit log
        log_audit_event(
            db=db,
            user=current_user,
            action="sync",
            entity_type="pos_sales",
            entity_id=location_id,
            changes={"synced": synced, "skipped": skipped, "errors": len(errors)}
        )

        success = len(errors) == 0 or synced > 0
        message = f"Synced {synced} orders, skipped {skipped} existing orders"
        if errors:
            message += f", {len(errors)} errors occurred"

        return POSSyncResponse(
            success=success,
            message=message,
            orders_synced=synced,
            orders_skipped=skipped,
            errors=errors if errors else None
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/process-deductions/{location_id}")
async def process_inventory_deductions(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Retroactively process inventory deductions for existing sales that haven't been deducted yet.

    This is useful for sales that were synced before the inventory deduction feature was implemented.
    """
    try:
        # Get all unprocessed sales for this location with items eagerly loaded
        from sqlalchemy.orm import joinedload
        unprocessed_sales = db.query(POSSale).options(
            joinedload(POSSale.line_items)
        ).filter(
            POSSale.location_id == location_id,
            POSSale.inventory_deducted == False
        ).all()

        if not unprocessed_sales:
            return {
                "success": True,
                "message": "No unprocessed sales found",
                "sales_processed": 0,
                "items_deducted": 0,
                "items_skipped": 0
            }

        # Process deductions
        deduction_service = InventoryDeductionService(db)
        result = deduction_service.process_bulk_sales(unprocessed_sales)

        # Audit log
        log_audit_event(
            db=db,
            user=current_user,
            action="process_deductions",
            entity_type="pos_sales",
            entity_id=location_id,
            changes={
                "sales_processed": len(unprocessed_sales),
                "items_deducted": result['total_items_deducted'],
                "items_skipped": result['total_items_skipped']
            }
        )

        return {
            "success": True,
            "message": f"Processed {len(unprocessed_sales)} sales",
            "sales_processed": len(unprocessed_sales),
            "items_deducted": result['total_items_deducted'],
            "items_skipped": result['total_items_skipped'],
            "transactions_created": result['total_transactions_created'],
            "errors": result['errors'] if result['errors'] else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process deductions: {str(e)}")


@router.get("/sales", response_model=List[POSSaleResponse])
async def get_pos_sales(
    location_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of synced POS sales

    Filters:
    - location_id: Filter by location
    - start_date: Filter by start date (ISO format)
    - end_date: Filter by end date (ISO format)
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date).date() if start_date else None
        end = datetime.fromisoformat(end_date).date() if end_date else None

        # Get sales
        sync_service = POSSyncService(db)
        sales = sync_service.get_sales(
            location_id=location_id,
            start_date=start,
            end_date=end,
            limit=limit,
            offset=offset
        )

        return sales

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")


@router.get("/sales/{sale_id}", response_model=POSSaleResponse)
async def get_pos_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific POS sale"""
    sync_service = POSSyncService(db)
    sale = sync_service.get_sale(sale_id)

    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    return sale

# ===== Item Mapping Endpoints =====

@router.get("/item-mappings", response_model=List[POSItemMappingResponse])
async def get_item_mappings(
    location_id: Optional[int] = None,
    unmapped_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all POS item mappings"""
    query = db.query(POSItemMapping)

    if location_id:
        query = query.filter(POSItemMapping.location_id == location_id)

    mappings = query.all()

    # Enrich with recipe/item names and sales stats
    results = []
    for mapping in mappings:
        mapping_dict = {
            "id": mapping.id,
            "pos_provider": mapping.pos_provider,
            "pos_item_id": mapping.pos_item_id,
            "pos_item_name": mapping.pos_item_name,
            "recipe_id": mapping.recipe_id,
            "master_item_id": mapping.master_item_id,
            "portion_multiplier": float(mapping.portion_multiplier),
            "location_id": mapping.location_id,
            "is_active": mapping.is_active,
            "created_at": mapping.created_at,
            "updated_at": mapping.updated_at,
        }

        # Add recipe name if mapped to recipe
        if mapping.recipe_id and mapping.recipe:
            mapping_dict["recipe_name"] = mapping.recipe.name

        # Add master item name if mapped to item
        if mapping.master_item_id and mapping.master_item:
            mapping_dict["master_item_name"] = mapping.master_item.name

        # Get sales stats
        times_sold = db.query(func.count(POSSaleItem.id)).filter(
            POSSaleItem.pos_item_id == mapping.pos_item_id
        ).scalar() or 0
        mapping_dict["times_sold"] = times_sold

        results.append(mapping_dict)

    return results


@router.get("/unmapped-items", response_model=List[UnmappedPOSItem])
async def get_unmapped_items(
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get POS items that haven't been mapped to recipes or master items yet"""

    # Get all mapped item IDs
    mapped_items_query = db.query(distinct(POSItemMapping.pos_item_id))
    mapped_item_ids = {row[0] for row in mapped_items_query.all()}

    # Get all items from sales
    query = db.query(
        POSSaleItem.pos_item_id,
        POSSaleItem.item_name,
        POSSaleItem.category,
        func.count(POSSaleItem.id).label('times_sold'),
        func.sum(POSSaleItem.quantity).label('total_quantity'),
        func.sum(POSSaleItem.total_price).label('total_revenue'),
        func.min(POSSale.order_date).label('first_sold'),
        func.max(POSSale.order_date).label('last_sold')
    ).join(
        POSSale, POSSaleItem.sale_id == POSSale.id
    ).filter(
        POSSaleItem.pos_item_id.isnot(None)
    )

    if location_id:
        query = query.filter(POSSale.location_id == location_id)

    query = query.group_by(
        POSSaleItem.pos_item_id,
        POSSaleItem.item_name,
        POSSaleItem.category
    ).order_by(func.count(POSSaleItem.id).desc())

    items = query.all()

    # Filter out mapped items
    unmapped = []
    for item in items:
        if item.pos_item_id not in mapped_item_ids:
            unmapped.append({
                "pos_item_id": item.pos_item_id,
                "item_name": item.item_name,
                "category": item.category,
                "times_sold": item.times_sold,
                "total_quantity": float(item.total_quantity or 0),
                "total_revenue": float(item.total_revenue or 0),
                "first_sold": item.first_sold,
                "last_sold": item.last_sold
            })

    return unmapped


@router.post("/item-mappings", response_model=POSItemMappingResponse)
async def create_item_mapping(
    mapping: POSItemMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new POS item mapping"""

    # Validate that at least one mapping target is provided
    if not mapping.recipe_id and not mapping.master_item_id:
        raise HTTPException(
            status_code=400,
            detail="Must provide either recipe_id or master_item_id"
        )

    # Check if mapping already exists
    existing = db.query(POSItemMapping).filter(
        POSItemMapping.pos_item_id == mapping.pos_item_id,
        POSItemMapping.location_id == mapping.location_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Mapping already exists for this POS item and location"
        )

    # Create mapping
    db_mapping = POSItemMapping(**mapping.dict())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="create",
        entity_type="pos_item_mapping",
        entity_id=db_mapping.id
    )

    return db_mapping


@router.put("/item-mappings/{mapping_id}", response_model=POSItemMappingResponse)
async def update_item_mapping(
    mapping_id: int,
    mapping_update: POSItemMappingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update an existing POS item mapping"""

    db_mapping = db.query(POSItemMapping).filter(POSItemMapping.id == mapping_id).first()

    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Update fields
    update_data = mapping_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_mapping, field, value)

    db.commit()
    db.refresh(db_mapping)

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="update",
        entity_type="pos_item_mapping",
        entity_id=db_mapping.id
    )

    return db_mapping


@router.delete("/item-mappings/{mapping_id}")
async def delete_item_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a POS item mapping"""

    db_mapping = db.query(POSItemMapping).filter(POSItemMapping.id == mapping_id).first()

    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Audit log before deletion
    log_audit_event(
        db=db,
        user=current_user,
        action="delete",
        entity_type="pos_item_mapping",
        entity_id=db_mapping.id
    )

    db.delete(db_mapping)
    db.commit()

    return {"success": True, "message": "Mapping deleted successfully"}
