"""
Master Items CRUD endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional, Dict
import tempfile
import os

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.item import MasterItemCreate, MasterItemUpdate, MasterItemResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict
from restaurant_inventory.services.hub_client import get_vendor_item_price_for_master_item_sync, get_all_vendor_item_prices_sync

router = APIRouter()

@router.get("/_hub/sync")
def get_items_for_hub(
    skip: int = 0,
    limit: int = 5000,
    active_only: bool = Query(True, description="Show only active items"),
    db: Session = Depends(get_db)
):
    """
    Get all items for Integration Hub sync
    No authentication required - this is an internal API call from the hub
    IMPORTANT: This route must be defined BEFORE /{item_id} route
    Path starts with _ to avoid being matched by /{item_id} pattern
    """
    query = db.query(MasterItem)

    if active_only:
        query = query.filter(MasterItem.is_active == True)

    items = query.offset(skip).limit(limit).all()

    # Return simple dict format for hub
    item_list = []
    for item in items:
        item_list.append({
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "is_active": item.is_active
        })

    return item_list


@router.get("/", response_model=List[MasterItemResponse])
async def get_master_items(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in name or description"),
    active_only: bool = Query(True, description="Show only active items"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all master items with filtering"""
    query = db.query(MasterItem).options(
        joinedload(MasterItem.unit),
        joinedload(MasterItem.secondary_unit_rel),
        joinedload(MasterItem.count_unit_2),
        joinedload(MasterItem.count_unit_3)
    )

    if active_only:
        query = query.filter(MasterItem.is_active == True)

    if category:
        query = query.filter(MasterItem.category == category)

    if search:
        query = query.filter(
            (MasterItem.name.ilike(f"%{search}%")) |
            (MasterItem.description.ilike(f"%{search}%"))
        )

    items = query.offset(skip).limit(limit).all()

    # Batch fetch all vendor item prices from Hub in ONE call (not N+1 calls)
    # This is much more efficient than calling Hub for each of 500+ items
    prices_by_master_id = get_all_vendor_item_prices_sync()

    # Add unit names and pricing info to response
    result = []
    for item in items:
        item_dict = MasterItemResponse.from_orm(item).dict()
        # Populate unit_of_measure with the actual unit name from the relationship
        # This ensures backward compatibility with frontend that uses unit_of_measure field
        unit_name = item.unit.name if item.unit else item.unit_of_measure
        item_dict['unit_of_measure'] = unit_name
        item_dict['unit_name'] = unit_name
        item_dict['secondary_unit_name'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit
        item_dict['secondary_unit'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit

        # Additional count units for flexible inventory counting
        # Include conversion factors (contains_quantity) for unit conversion during counting
        item_dict['count_unit_2_name'] = item.count_unit_2.name if item.count_unit_2 else None
        item_dict['count_unit_2_factor'] = float(item.count_unit_2.contains_quantity) if item.count_unit_2 and item.count_unit_2.contains_quantity else None
        item_dict['count_unit_3_name'] = item.count_unit_3.name if item.count_unit_3 else None
        item_dict['count_unit_3_factor'] = float(item.count_unit_3.contains_quantity) if item.count_unit_3 and item.count_unit_3.contains_quantity else None

        # Look up price from batch-fetched data
        price_info = prices_by_master_id.get(item.id)
        if price_info:
            item_dict['last_price_paid'] = price_info.get('unit_price')
            item_dict['last_price_unit'] = price_info.get('vendor_product_name') or price_info.get('vendor_name')
        else:
            item_dict['last_price_paid'] = None
            item_dict['last_price_unit'] = None

        result.append(item_dict)

    return result

@router.get("/categories")
async def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique categories"""
    categories = db.query(MasterItem.category).distinct().all()
    return {"categories": [cat[0] for cat in categories if cat[0]]}


@router.get("/duplicates")
async def find_duplicate_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find potential duplicate master items.

    Returns items that are likely duplicates based on:
    1. Same category
    2. Same primary type (first part before comma)
    3. Very similar secondary attributes
    """
    from sqlalchemy import text

    # Find items with same primary type (text before first comma) in same category
    # This is much more accurate than just matching first word
    results = db.execute(text("""
        WITH item_parts AS (
            SELECT
                id,
                name,
                category,
                -- Get the primary type (everything before first comma, trimmed and lowercased)
                LOWER(TRIM(SPLIT_PART(name, ',', 1))) as primary_type,
                -- Get everything after the first comma (secondary attributes)
                LOWER(TRIM(SUBSTRING(name FROM POSITION(',' IN name) + 1))) as secondary_attrs
            FROM master_items
            WHERE is_active = true
        )
        SELECT
            i1.id as id1, i1.name as name1,
            i2.id as id2, i2.name as name2,
            i1.category,
            i1.primary_type,
            i1.secondary_attrs as attrs1,
            i2.secondary_attrs as attrs2
        FROM item_parts i1
        JOIN item_parts i2 ON
            i1.id < i2.id
            AND i1.category = i2.category
            AND i1.primary_type = i2.primary_type
            AND LENGTH(i1.primary_type) > 3
        WHERE
            -- Secondary attributes must be very similar (same or very close)
            (
                -- Exact match on secondary attributes
                i1.secondary_attrs = i2.secondary_attrs
                OR
                -- One is a substring of the other (one has more detail)
                i1.secondary_attrs LIKE '%' || i2.secondary_attrs || '%'
                OR
                i2.secondary_attrs LIKE '%' || i1.secondary_attrs || '%'
                OR
                -- Very similar length and same first few chars after comma
                (
                    ABS(LENGTH(i1.secondary_attrs) - LENGTH(i2.secondary_attrs)) < 10
                    AND LEFT(i1.secondary_attrs, 15) = LEFT(i2.secondary_attrs, 15)
                )
            )
            -- Exclude alcohol categories from loose matching (too many similar items)
            AND i1.primary_type NOT IN ('beer', 'wine', 'bourbon', 'vodka', 'gin', 'tequila',
                                        'rum', 'whiskey', 'scotch', 'cordial', 'liqueur')
        ORDER BY i1.category, i1.name
        LIMIT 50
    """)).fetchall()

    duplicates = []
    for row in results:
        duplicates.append({
            "item1": {"id": row[0], "name": row[1]},
            "item2": {"id": row[2], "name": row[3]},
            "category": row[4]
        })

    return {
        "potential_duplicates": duplicates,
        "count": len(duplicates)
    }


@router.post("/merge")
async def merge_master_items(
    source_id: int,
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Merge two master items into one.

    Moves all vendor_items, waste_records, invoice_items, inventory records,
    count_session_items, recipe_ingredients, and pos_mappings from source to target,
    then deletes the source item.

    Args:
        source_id: The ID of the item to merge FROM (will be deleted)
        target_id: The ID of the item to merge INTO (will be kept)

    Returns:
        Summary of merged records
    """
    from restaurant_inventory.models.inventory import Inventory
    from restaurant_inventory.models.pos_sale import POSItemMapping
    from restaurant_inventory.models.recipe import RecipeIngredient
    from restaurant_inventory.models.waste import WasteRecord
    from restaurant_inventory.models.count_session import CountSessionItem
    from restaurant_inventory.models.inventory_transaction import InventoryTransaction

    # Validate source and target exist
    source_item = db.query(MasterItem).filter(MasterItem.id == source_id).first()
    target_item = db.query(MasterItem).filter(MasterItem.id == target_id).first()

    if not source_item:
        raise HTTPException(status_code=404, detail=f"Source item {source_id} not found")
    if not target_item:
        raise HTTPException(status_code=404, detail=f"Target item {target_id} not found")
    if source_id == target_id:
        raise HTTPException(status_code=400, detail="Source and target cannot be the same item")

    merge_stats = {
        "waste_records": 0,
        "inventory_records": 0,
        "count_session_items": 0,
        "recipe_ingredients": 0,
        "pos_mappings": 0,
        "inventory_transactions": 0,
        "note": "Vendor items and invoice items are managed in Hub - merge them there"
    }

    try:
        # NOTE: vendor_items and invoice_items are now in Hub (source of truth)
        # They should be merged in Hub, not here

        # Move waste_records
        waste_moved = db.query(WasteRecord).filter(
            WasteRecord.master_item_id == source_id
        ).update({WasteRecord.master_item_id: target_id})
        merge_stats["waste_records"] = waste_moved

        # Move inventory records
        inventory_moved = db.query(Inventory).filter(
            Inventory.master_item_id == source_id
        ).update({Inventory.master_item_id: target_id})
        merge_stats["inventory_records"] = inventory_moved

        # Move count_session_items
        count_moved = db.query(CountSessionItem).filter(
            CountSessionItem.master_item_id == source_id
        ).update({CountSessionItem.master_item_id: target_id})
        merge_stats["count_session_items"] = count_moved

        # Move recipe_ingredients
        recipe_moved = db.query(RecipeIngredient).filter(
            RecipeIngredient.master_item_id == source_id
        ).update({RecipeIngredient.master_item_id: target_id})
        merge_stats["recipe_ingredients"] = recipe_moved

        # Move pos_mappings
        pos_moved = db.query(POSItemMapping).filter(
            POSItemMapping.master_item_id == source_id
        ).update({POSItemMapping.master_item_id: target_id})
        merge_stats["pos_mappings"] = pos_moved

        # Move inventory_transactions
        trans_moved = db.query(InventoryTransaction).filter(
            InventoryTransaction.master_item_id == source_id
        ).update({InventoryTransaction.master_item_id: target_id})
        merge_stats["inventory_transactions"] = trans_moved

        # Log audit event before deletion
        log_audit_event(
            db=db,
            action="MERGE",
            entity_type="item",
            entity_id=target_id,
            user=current_user,
            changes={
                "merged_from": {
                    "id": source_item.id,
                    "name": source_item.name,
                    "category": source_item.category
                },
                "merged_into": {
                    "id": target_item.id,
                    "name": target_item.name,
                    "category": target_item.category
                },
                "records_moved": merge_stats
            },
            request=request
        )

        # Delete source item
        source_name = source_item.name
        db.delete(source_item)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully merged '{source_name}' into '{target_item.name}'",
            "source_deleted": source_id,
            "target_id": target_id,
            "records_moved": merge_stats,
            "total_records_moved": sum(merge_stats.values())
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")


@router.get("/{item_id}", response_model=MasterItemResponse)
async def get_master_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific master item by ID"""
    item = db.query(MasterItem).options(
        joinedload(MasterItem.unit),
        joinedload(MasterItem.secondary_unit_rel),
        joinedload(MasterItem.count_unit_2),
        joinedload(MasterItem.count_unit_3)
    ).filter(MasterItem.id == item_id).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )

    # Build response with unit names
    item_dict = MasterItemResponse.from_orm(item).dict()
    item_dict['unit_of_measure'] = item.unit.name if item.unit else item.unit_of_measure
    item_dict['unit_name'] = item.unit.name if item.unit else item.unit_of_measure
    item_dict['secondary_unit_name'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit
    item_dict['count_unit_2_name'] = item.count_unit_2.name if item.count_unit_2 else None
    item_dict['count_unit_3_name'] = item.count_unit_3.name if item.count_unit_3 else None

    return item_dict

@router.get("/{item_id}/location-costs")
async def get_item_location_costs(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost comparison by location for a master item.

    DEPRECATED: Invoice data is now in Integration Hub.
    This endpoint returns a redirect message.
    """
    return {
        "message": "Invoice-based cost data has been moved to Integration Hub",
        "redirect": "/hub/dashboard",
        "reason": "Invoice data is now managed in the Integration Hub (source of truth)",
        "results": []
    }

@router.post("/", response_model=MasterItemResponse)
async def create_master_item(
    item_data: MasterItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create new master item (Manager/Admin only)"""

    # Check if item with same name already exists
    existing = db.query(MasterItem).filter(MasterItem.name == item_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item with this name already exists"
        )

    # Check if SKU already exists (if provided)
    if item_data.sku:
        existing_sku = db.query(MasterItem).filter(MasterItem.sku == item_data.sku).first()
        if existing_sku:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Item with this SKU already exists"
            )

    item = MasterItem(**item_data.dict())
    if item_data.current_cost:
        from datetime import datetime
        item.last_cost_update = datetime.utcnow()

    db.add(item)
    db.commit()
    db.refresh(item)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="item",
        entity_id=item.id,
        user=current_user,
        changes={"new": {
            "name": item.name,
            "category": item.category,
            "sku": item.sku,
            "unit_of_measure": item.unit_of_measure,
            "current_cost": float(item.current_cost) if item.current_cost else None
        }},
        request=request
    )

    return item

@router.put("/{item_id}", response_model=MasterItemResponse)
async def update_master_item(
    item_id: int,
    item_data: MasterItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update master item (Manager/Admin only)"""

    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )

    # Track old values
    old_data = {
        "name": item.name,
        "category": item.category,
        "current_cost": float(item.current_cost) if item.current_cost else None
    }

    # Update cost timestamp if cost is being updated
    update_data = item_data.dict(exclude_unset=True)
    if "current_cost" in update_data and update_data["current_cost"] is not None:
        from datetime import datetime
        update_data["last_cost_update"] = datetime.utcnow()

    # Update fields that were provided
    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    # Track new values
    new_data = {
        "name": item.name,
        "category": item.category,
        "current_cost": float(item.current_cost) if item.current_cost else None
    }

    # Log audit event
    changes = create_change_dict(old_data, new_data)
    if changes:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="item",
            entity_id=item.id,
            user=current_user,
            changes=changes,
            request=request
        )

    return item

@router.delete("/{item_id}")
async def delete_master_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete master item (Manager/Admin only)"""

    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )

    # Check if item is being used in other tables
    from restaurant_inventory.models.inventory import Inventory
    from restaurant_inventory.models.pos_sale import POSItemMapping
    from restaurant_inventory.models.recipe import RecipeIngredient
    from restaurant_inventory.models.waste import WasteRecord
    from restaurant_inventory.models.count_session import CountSessionItem
    from restaurant_inventory.models.inventory_transaction import InventoryTransaction

    blocking_items = []

    # Check inventory records
    inventory_count = db.query(Inventory).filter(Inventory.master_item_id == item_id).count()
    if inventory_count > 0:
        blocking_items.append(f"{inventory_count} inventory record(s)")

    # Check POS item mappings
    pos_mapping_count = db.query(POSItemMapping).filter(POSItemMapping.master_item_id == item_id).count()
    if pos_mapping_count > 0:
        blocking_items.append(f"{pos_mapping_count} POS item mapping(s)")

    # Check recipe ingredients
    recipe_count = db.query(RecipeIngredient).filter(RecipeIngredient.master_item_id == item_id).count()
    if recipe_count > 0:
        blocking_items.append(f"{recipe_count} recipe ingredient(s)")

    # Check waste records
    waste_count = db.query(WasteRecord).filter(WasteRecord.master_item_id == item_id).count()
    if waste_count > 0:
        blocking_items.append(f"{waste_count} waste record(s)")

    # Check count session items
    count_count = db.query(CountSessionItem).filter(CountSessionItem.master_item_id == item_id).count()
    if count_count > 0:
        blocking_items.append(f"{count_count} count session item(s)")

    # NOTE: Invoice items are now in Hub (source of truth)
    # Deletion blocking for invoice items should be checked via Hub API if needed

    # Check inventory transactions
    transaction_count = db.query(InventoryTransaction).filter(InventoryTransaction.master_item_id == item_id).count()
    if transaction_count > 0:
        blocking_items.append(f"{transaction_count} inventory transaction(s)")

    if blocking_items:
        detail = f"Cannot delete '{item.name}' because it is being used in: {', '.join(blocking_items)}. Please remove these references first."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    # Log before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="item",
        entity_id=item.id,
        user=current_user,
        changes={"old": {
            "name": item.name,
            "category": item.category,
            "sku": item.sku
        }},
        request=request
    )

    db.delete(item)
    db.commit()
    return {"message": "Master item deleted successfully"}


@router.post("/parse-vendor-upload")
async def parse_vendor_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Parse an uploaded vendor item list (CSV or Excel).

    DEPRECATED: Vendor items are now managed in Integration Hub.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Vendor items are now managed in Integration Hub. Please use the Hub interface."
    )


@router.post("/preview-vendor-items")
async def preview_vendor_items(
    file: UploadFile = File(...),
    column_mapping: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Preview all items from vendor file with column mapping.

    DEPRECATED: Vendor items are now managed in Integration Hub.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Vendor items are now managed in Integration Hub. Please use the Hub interface."
    )


@router.post("/import-vendor-items")
async def import_vendor_items(
    file: UploadFile = File(...),
    vendor_id: str = Form(...),
    column_mapping: str = Form(None),
    unit_mappings: str = Form(None),
    update_existing: str = Form("true"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
    request: Request = None
):
    """
    Import vendor items using specified column and unit mappings.

    DEPRECATED: Vendor items are now managed in Integration Hub.
    This endpoint is no longer functional.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Vendor items are now managed in Integration Hub. Please use the Hub interface to import vendor items."
    )


@router.post("/parse-master-upload")
async def parse_master_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Parse an uploaded master items list (CSV or Excel)"""
    from restaurant_inventory.core.master_item_parser import MasterItemParser

    # Validate file type
    allowed_extensions = {'.csv', '.xlsx', '.xls'}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )

    # Save uploaded file to temporary location
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Parse the file to get columns and sample data
        parser = MasterItemParser()
        result = parser.parse_file(temp_path, file_ext[1:])  # Remove the dot from extension

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse master items file")
            )

        # Get suggested column mapping
        columns = result.get("data", {}).get("columns", [])
        suggested_mapping = parser.get_suggested_mapping(columns)

        # Return columns, sample data, and suggested mapping
        return {
            "columns": columns,
            "sample_rows": result.get("data", {}).get("sample_rows", []),
            "total_rows": result.get("data", {}).get("total_rows", 0),
            "suggested_mapping": suggested_mapping
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"ERROR in parse_master_upload: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview-master-items")
async def preview_master_items(
    file: UploadFile = File(...),
    column_mapping: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Preview all items from master items file with column mapping"""
    from restaurant_inventory.core.master_item_parser import MasterItemParser
    import json

    # Validate file type
    allowed_extensions = {'.csv', '.xlsx', '.xls'}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )

    if not column_mapping:
        raise HTTPException(
            status_code=400,
            detail="Column mapping is required"
        )

    # Parse column_mapping from JSON string
    try:
        column_mapping_dict = json.loads(column_mapping)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid column mapping format"
        )

    # Save uploaded file to temporary location
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Parse file with column mapping
        parser = MasterItemParser()
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse master items file")
            )

        items = result.get("data", {}).get("items", [])

        # Validate items and get unit options
        units = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).all()
        unit_options = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation} for u in units]

        validated_items = []
        for item in items:
            # Validate item
            validation = parser.validate_item(item)

            # Try to match unit
            matched_unit_id = None
            if item.get('unit_of_measure'):
                unit_str = str(item['unit_of_measure']).lower().strip()
                for unit in units:
                    if (unit.name.lower() == unit_str or
                        unit.abbreviation.lower() == unit_str):
                        matched_unit_id = unit.id
                        break

            # Try to match secondary unit
            matched_secondary_unit_id = None
            if item.get('secondary_unit'):
                secondary_str = str(item['secondary_unit']).lower().strip()
                for unit in units:
                    if (unit.name.lower() == secondary_str or
                        unit.abbreviation.lower() == secondary_str):
                        matched_secondary_unit_id = unit.id
                        break

            validated_items.append({
                "name": item.get('name', ''),
                "item_code": item.get('item_code', ''),
                "description": item.get('description', ''),
                "category": item.get('category', ''),
                "unit_of_measure": item.get('unit_of_measure', ''),
                "matched_unit_id": matched_unit_id,
                "secondary_unit": item.get('secondary_unit', ''),
                "matched_secondary_unit_id": matched_secondary_unit_id,
                "conversion_factor": item.get('conversion_factor'),
                "par_level": item.get('par_level'),
                "row_number": item.get('_row_number', 0),
                "valid": validation['valid'],
                "errors": validation['errors']
            })

        return {
            "items": validated_items,
            "total": len(validated_items),
            "unit_options": unit_options
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"ERROR in preview_master_items: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-master-items")
async def import_master_items(
    file: UploadFile = File(...),
    column_mapping: str = Form(...),
    unit_mappings: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Import master items using specified column and unit mappings"""
    from restaurant_inventory.core.master_item_parser import MasterItemParser
    import json

    # Validate file type
    allowed_extensions = {'.csv', '.xlsx', '.xls'}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )

    # Parse inputs
    try:
        column_mapping_dict = json.loads(column_mapping)
        unit_mappings_dict = json.loads(unit_mappings)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format: {str(e)}"
        )

    # Save uploaded file to temporary location
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Parse file with column mapping
        parser = MasterItemParser()
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse master items file")
            )

        items = result.get("data", {}).get("items", [])

        # Import items
        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []

        for item_data in items:
            try:
                row_num = item_data.get('_row_number', 0)
                row_key = str(row_num)

                # Get mapped unit IDs (optional now)
                unit_id = unit_mappings_dict.get(f"{row_key}_unit")
                secondary_unit_id = unit_mappings_dict.get(f"{row_key}_secondary")

                # Check if item already exists by name
                existing_item = db.query(MasterItem).filter(
                    MasterItem.name == item_data.get('name')
                ).first()

                if existing_item:
                    # Update existing item
                    if item_data.get('description'):
                        existing_item.description = item_data.get('description')
                    if item_data.get('category'):
                        existing_item.category = item_data.get('category')
                    if unit_id:
                        existing_item.unit_of_measure_id = int(unit_id)
                    if secondary_unit_id:
                        existing_item.secondary_unit_id = int(secondary_unit_id)
                    if item_data.get('item_code'):
                        existing_item.sku = item_data.get('item_code')
                    if item_data.get('conversion_factor'):
                        existing_item.units_per_secondary = float(item_data['conversion_factor'])
                    if item_data.get('par_level'):
                        existing_item.par_level = float(item_data['par_level'])

                    updated_count += 1

                    # Log audit event
                    log_audit_event(
                        db=db,
                        user=current_user,
                        action="update_master_item",
                        entity_type="master_item",
                        entity_id=existing_item.id,
                        request=request
                    )

                else:
                    # Create new item (name is the only required field now)
                    new_item = MasterItem(
                        name=item_data.get('name'),
                        sku=item_data.get('item_code'),
                        description=item_data.get('description'),
                        category=item_data.get('category') or 'Uncategorized',  # Default if empty
                        unit_of_measure_id=int(unit_id) if unit_id else None,  # Optional
                        secondary_unit_id=int(secondary_unit_id) if secondary_unit_id else None,
                        units_per_secondary=float(item_data['conversion_factor']) if item_data.get('conversion_factor') else None,
                        par_level=float(item_data['par_level']) if item_data.get('par_level') else None
                    )
                    db.add(new_item)
                    db.flush()  # Get the ID

                    created_count += 1

                    # Log audit event
                    log_audit_event(
                        db=db,
                        user=current_user,
                        action="create_master_item",
                        entity_type="master_item",
                        entity_id=new_item.id,
                        request=request
                    )

            except Exception as e:
                error_count += 1
                row_num = item_data.get('_row_number', '?')
                item_name = item_data.get('name', 'Unknown')
                errors.append(f"Row {row_num} ({item_name}): {str(e)}")
                continue

        # Commit all changes
        db.commit()

        return {
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "errors": error_count,
            "error_details": errors
        }

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Item Unit Conversions API
# ============================================================================

@router.get("/{item_id}/unit-conversions")
async def get_item_unit_conversions(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all unit conversions for a master item.

    Example response for sausage patties:
    [
        {
            "id": 1,
            "from_unit": {"id": 5, "name": "Pound", "abbreviation": "LB"},
            "to_unit": {"id": 1, "name": "Each", "abbreviation": "EA"},
            "conversion_factor": 8.0,
            "individual_weight_oz": 2.0,
            "notes": "2oz patties, 8 per pound"
        }
    ]
    """
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion
    from restaurant_inventory.models.unit_of_measure import UnitOfMeasure

    # Verify item exists
    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    conversions = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.master_item_id == item_id,
        ItemUnitConversion.is_active == True
    ).all()

    result = []
    for conv in conversions:
        from_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == conv.from_unit_id).first()
        to_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == conv.to_unit_id).first()

        result.append({
            "id": conv.id,
            "from_unit": {
                "id": from_unit.id,
                "name": from_unit.name,
                "abbreviation": from_unit.abbreviation
            } if from_unit else None,
            "to_unit": {
                "id": to_unit.id,
                "name": to_unit.name,
                "abbreviation": to_unit.abbreviation
            } if to_unit else None,
            "conversion_factor": float(conv.conversion_factor),
            "individual_weight_oz": float(conv.individual_weight_oz) if conv.individual_weight_oz else None,
            "individual_volume_oz": float(conv.individual_volume_oz) if conv.individual_volume_oz else None,
            "notes": conv.notes
        })

    return result


@router.post("/{item_id}/unit-conversions")
async def create_item_unit_conversion(
    item_id: int,
    from_unit_id: int,
    to_unit_id: int,
    conversion_factor: float,
    individual_weight_oz: float = None,
    individual_volume_oz: float = None,
    notes: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Create a new unit conversion for a master item.

    Example: For 2oz sausage patties:
    - from_unit_id: Pound
    - to_unit_id: Each
    - conversion_factor: 8 (8 patties per pound)
    - individual_weight_oz: 2 (each patty is 2oz)
    """
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion
    from restaurant_inventory.models.unit_of_measure import UnitOfMeasure

    # Verify item exists
    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    # Verify units exist
    from_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == from_unit_id).first()
    to_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == to_unit_id).first()

    if not from_unit:
        raise HTTPException(status_code=400, detail="From unit not found")
    if not to_unit:
        raise HTTPException(status_code=400, detail="To unit not found")

    # Check for existing conversion
    existing = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.master_item_id == item_id,
        ItemUnitConversion.from_unit_id == from_unit_id,
        ItemUnitConversion.to_unit_id == to_unit_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Conversion already exists for this unit pair")

    conversion = ItemUnitConversion(
        master_item_id=item_id,
        from_unit_id=from_unit_id,
        to_unit_id=to_unit_id,
        conversion_factor=conversion_factor,
        individual_weight_oz=individual_weight_oz,
        individual_volume_oz=individual_volume_oz,
        notes=notes,
        is_active=True
    )

    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    return {
        "id": conversion.id,
        "from_unit": {
            "id": from_unit.id,
            "name": from_unit.name,
            "abbreviation": from_unit.abbreviation
        },
        "to_unit": {
            "id": to_unit.id,
            "name": to_unit.name,
            "abbreviation": to_unit.abbreviation
        },
        "conversion_factor": float(conversion.conversion_factor),
        "individual_weight_oz": float(conversion.individual_weight_oz) if conversion.individual_weight_oz else None,
        "individual_volume_oz": float(conversion.individual_volume_oz) if conversion.individual_volume_oz else None,
        "notes": conversion.notes
    }


@router.put("/{item_id}/unit-conversions/{conversion_id}")
async def update_item_unit_conversion(
    item_id: int,
    conversion_id: int,
    conversion_factor: float = None,
    individual_weight_oz: float = None,
    individual_volume_oz: float = None,
    notes: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update an existing unit conversion."""
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion

    conversion = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.id == conversion_id,
        ItemUnitConversion.master_item_id == item_id
    ).first()

    if not conversion:
        raise HTTPException(status_code=404, detail="Conversion not found")

    if conversion_factor is not None:
        conversion.conversion_factor = conversion_factor
    if individual_weight_oz is not None:
        conversion.individual_weight_oz = individual_weight_oz
    if individual_volume_oz is not None:
        conversion.individual_volume_oz = individual_volume_oz
    if notes is not None:
        conversion.notes = notes

    db.commit()
    db.refresh(conversion)

    return {"success": True, "id": conversion.id}


@router.delete("/{item_id}/unit-conversions/{conversion_id}")
async def delete_item_unit_conversion(
    item_id: int,
    conversion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete (deactivate) a unit conversion."""
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion

    conversion = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.id == conversion_id,
        ItemUnitConversion.master_item_id == item_id
    ).first()

    if not conversion:
        raise HTTPException(status_code=404, detail="Conversion not found")

    conversion.is_active = False
    db.commit()

    return {"success": True}


@router.post("/{item_id}/convert")
async def convert_units(
    item_id: int,
    quantity: float,
    from_unit_id: int,
    to_unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Convert a quantity from one unit to another for a specific item.

    Example: Convert 12 LB of sausage patties to Each
    - quantity: 12
    - from_unit_id: Pound ID
    - to_unit_id: Each ID
    - Result: 96 (patties)
    """
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion

    # Find the conversion
    conversion = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.master_item_id == item_id,
        ItemUnitConversion.is_active == True,
        (
            (ItemUnitConversion.from_unit_id == from_unit_id) &
            (ItemUnitConversion.to_unit_id == to_unit_id)
        ) | (
            (ItemUnitConversion.from_unit_id == to_unit_id) &
            (ItemUnitConversion.to_unit_id == from_unit_id)
        )
    ).first()

    if not conversion:
        raise HTTPException(
            status_code=400,
            detail="No conversion defined between these units for this item"
        )

    # Calculate conversion
    if conversion.from_unit_id == from_unit_id:
        # Converting from -> to (multiply)
        result = quantity * float(conversion.conversion_factor)
    else:
        # Converting to -> from (divide)
        result = quantity / float(conversion.conversion_factor)

    return {
        "original_quantity": quantity,
        "original_unit_id": from_unit_id,
        "converted_quantity": round(result, 4),
        "converted_unit_id": to_unit_id,
        "conversion_factor": float(conversion.conversion_factor)
    }
