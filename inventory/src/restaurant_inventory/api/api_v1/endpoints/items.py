"""
Master Items CRUD endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File, Form, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, text
from typing import List, Optional, Dict
import tempfile
import os
import logging

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin, verify_hub_api_key
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.item import MasterItemCreate, MasterItemUpdate, MasterItemResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

logger = logging.getLogger(__name__)

# Hub database URL for fetching vendor items (source of truth)
HUB_DATABASE_URL = os.getenv("HUB_DATABASE_URL")

router = APIRouter()

@router.get("/_hub/sync")
def get_items_for_hub(
    skip: int = 0,
    limit: int = 5000,
    active_only: bool = Query(True, description="Show only active items"),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_hub_api_key)
):
    """
    Get all items for Integration Hub sync
    Requires X-Hub-API-Key header for authentication
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


@router.get("/")
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
        joinedload(MasterItem.count_unit_3),
        joinedload(MasterItem.count_units)  # New: eagerly load MasterItemCountUnit records
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

    # Fetch pricing data from Hub (source of truth for vendor items)
    # Get cost per unit for each master item from Hub's vendor items
    # Uses Backbar-style fields (case_cost / units_per_case) with fallback to deprecated fields
    # For weight items (lb, oz, kg, g), divides by size_quantity to get true per-unit cost
    hub_pricing = {}
    try:
        from sqlalchemy import create_engine
        hub_engine = create_engine(HUB_DATABASE_URL)
        with hub_engine.connect() as conn:
            # Get preferred vendor item price OR most recent price
            # Priority: case_cost/units_per_case (new), fallback to unit_price/conversion_factor (deprecated)
            # For weight items, also divide by size_quantity to get cost per unit weight (e.g., $/lb)
            pricing_query = text("""
                WITH vendor_item_prices AS (
                    SELECT
                        vi.inventory_master_item_id,
                        vi.is_preferred,
                        vi.updated_at,
                        -- New Backbar-style pricing (preferred)
                        vi.case_cost,
                        vi.units_per_case,
                        vi.size_quantity,
                        su.measure_type as size_unit_measure_type,
                        -- Deprecated pricing (fallback)
                        vi.unit_price,
                        vi.conversion_factor,
                        -- Calculate unit cost: divide by size_quantity for weight/count types only
                        -- Weight: 25 lb bag = cost per lb (divide by 25)
                        -- Count: 10 count bag = cost per each (divide by 10)
                        -- Volume: 750 ml bottle = cost per bottle (don't divide - 750ml is just size description)
                        CASE
                            WHEN vi.case_cost IS NOT NULL AND vi.units_per_case IS NOT NULL AND vi.units_per_case > 0
                                THEN CASE
                                    WHEN su.measure_type IN ('weight', 'count') AND vi.size_quantity IS NOT NULL AND vi.size_quantity > 1
                                        THEN vi.case_cost / (vi.units_per_case * vi.size_quantity)
                                    ELSE vi.case_cost / vi.units_per_case
                                END
                            WHEN vi.unit_price IS NOT NULL AND vi.unit_price > 0 AND vi.conversion_factor IS NOT NULL AND vi.conversion_factor > 0
                                THEN vi.unit_price / vi.conversion_factor
                            ELSE NULL
                        END as cost_per_unit
                    FROM hub_vendor_items vi
                    LEFT JOIN hub_size_units su ON vi.size_unit_id = su.id
                    WHERE vi.inventory_master_item_id IS NOT NULL
                      AND vi.is_active = true
                      AND (
                          (vi.case_cost IS NOT NULL AND vi.units_per_case IS NOT NULL AND vi.units_per_case > 0)
                          OR (vi.unit_price IS NOT NULL AND vi.unit_price > 0)
                      )
                ),
                preferred_prices AS (
                    SELECT DISTINCT ON (inventory_master_item_id)
                        inventory_master_item_id,
                        cost_per_unit
                    FROM vendor_item_prices
                    WHERE cost_per_unit IS NOT NULL
                    ORDER BY inventory_master_item_id, is_preferred DESC, updated_at DESC
                )
                SELECT
                    inventory_master_item_id,
                    cost_per_unit
                FROM preferred_prices
            """)
            results = conn.execute(pricing_query).fetchall()
            for row in results:
                hub_pricing[row[0]] = float(row[1]) if row[1] else None
    except Exception as e:
        logger.warning(f"Could not fetch pricing from Hub: {e}")

    # NOTE: Unit conversions for pricing are now handled via MasterItemCountUnit.conversion_to_primary
    # The item_unit_conversions table is deprecated. Count units include conversion factors
    # that express how the unit relates to the primary unit (e.g., 1 Case = 40 Pounds)

    # Add unit names and pricing info to response
    result = []
    for item in items:
        item_dict = MasterItemResponse.from_orm(item).model_dump()

        # Get count units from MasterItemCountUnit table (new architecture)
        # Sort by display_order — position 0 is the preferred counting unit
        try:
            count_units = sorted(item.count_units, key=lambda cu: (cu.display_order or 0))
        except Exception as e:
            logger.warning(f"Error sorting count_units for item {item.id}: {e}")
            count_units = []
        primary_count_unit = next((cu for cu in count_units if cu.is_primary), None)
        secondary_units = [cu for cu in count_units if cu != count_units[0]] if count_units else []

        # Use the PRIMARY count unit (is_primary=True) for unit_of_measure
        # This is the base unit for storage and pricing
        if primary_count_unit:
            unit_name = primary_count_unit.uom_name
        elif item.primary_uom_id:
            # Fallback to Hub UoM (cost tracking unit)
            unit_name = item.primary_uom_name or item.primary_uom_abbr
        else:
            # Fallback to deprecated Inventory UoM
            unit_name = item.unit.name if item.unit else item.unit_of_measure

        item_dict['unit_of_measure'] = unit_name
        item_dict['unit_name'] = unit_name
        item_dict['secondary_unit_name'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit

        item_dict['secondary_unit'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit

        # Also populate primary_count_unit fields for the API response
        if primary_count_unit:
            item_dict['primary_count_unit_id'] = primary_count_unit.uom_id
            item_dict['primary_count_unit_name'] = primary_count_unit.uom_name
            item_dict['primary_count_unit_abbr'] = primary_count_unit.uom_abbreviation

        # Count units ordered by display_order (user's preferred counting order)
        # CU1 = preferred default for counting, CU2/CU3 = alternatives
        if len(count_units) >= 1:
            cu1 = count_units[0]
            item_dict['count_unit_1_id'] = cu1.uom_id
            item_dict['count_unit_1_name'] = cu1.uom_name
            item_dict['count_unit_1_factor'] = float(cu1.conversion_to_primary) if cu1.conversion_to_primary else None
        else:
            item_dict['count_unit_1_id'] = None
            item_dict['count_unit_1_name'] = None
            item_dict['count_unit_1_factor'] = None

        if len(count_units) >= 2:
            cu2 = count_units[1]
            item_dict['count_unit_2_id'] = cu2.uom_id
            item_dict['count_unit_2_name'] = cu2.uom_name
            item_dict['count_unit_2_factor'] = float(cu2.conversion_to_primary) if cu2.conversion_to_primary else None
        else:
            item_dict['count_unit_2_id'] = None
            item_dict['count_unit_2_name'] = None
            item_dict['count_unit_2_factor'] = None

        if len(count_units) >= 3:
            cu3 = count_units[2]
            item_dict['count_unit_3_id'] = cu3.uom_id
            item_dict['count_unit_3_name'] = cu3.uom_name
            item_dict['count_unit_3_factor'] = float(cu3.conversion_to_primary) if cu3.conversion_to_primary else None
        else:
            item_dict['count_unit_3_id'] = None
            item_dict['count_unit_3_name'] = None
            item_dict['count_unit_3_factor'] = None

        # Get pricing from Hub vendor items (source of truth)
        # This is the cost per vendor's pricing unit
        base_price = hub_pricing.get(item.id)

        # Note: Price conversions now rely on MasterItemCountUnit.conversion_to_primary
        # The base_price from Hub is per the vendor's unit. If we need to convert to the
        # display/count unit, we use the count unit's conversion factor.
        # For now, we display the base price as-is - the conversion is applied during
        # recipe costing when the ingredient's unit is matched against count units.

        item_dict['last_price_paid'] = base_price
        item_dict['last_price_unit'] = unit_name if base_price else None

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
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion

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
        "unit_conversions": 0
    }
    # Note: vendor_items and invoice_items are now managed by Integration Hub

    try:
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

        # Delete unit_conversions for source item (don't move - they're item-specific)
        conversions_deleted = db.query(ItemUnitConversion).filter(
            ItemUnitConversion.master_item_id == source_id
        ).delete()
        merge_stats["unit_conversions"] = conversions_deleted

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
    from restaurant_inventory.models.master_item_count_unit import MasterItemCountUnit

    item = db.query(MasterItem).options(
        joinedload(MasterItem.unit),
        joinedload(MasterItem.secondary_unit_rel),
        joinedload(MasterItem.count_unit_2),
        joinedload(MasterItem.count_unit_3),
        joinedload(MasterItem.count_units)
    ).filter(MasterItem.id == item_id).first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )

    # Build response with unit names
    item_dict = MasterItemResponse.from_orm(item).model_dump()

    # Prioritize Hub UoM fields (primary_uom_*) over deprecated Inventory UoM fields
    # If primary_uom_id is set, use Hub UoM; otherwise fallback to deprecated fields
    if item.primary_uom_id:
        item_dict['unit_of_measure'] = item.primary_uom_name or item.primary_uom_abbr
        item_dict['unit_name'] = item.primary_uom_name or item.primary_uom_abbr
    else:
        # Fallback to deprecated Inventory UoM
        item_dict['unit_of_measure'] = item.unit.name if item.unit else item.unit_of_measure
        item_dict['unit_name'] = item.unit.name if item.unit else item.unit_of_measure

    item_dict['secondary_unit_name'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit

    # Get count units from MasterItemCountUnit table (new architecture)
    # Sort by display_order — position 0 is the preferred counting unit
    count_units = sorted(item.count_units, key=lambda cu: (cu.display_order or 0))

    # Primary count unit (is_primary=True) — used for pricing/costing
    primary_cu = next((cu for cu in count_units if cu.is_primary), None)
    if primary_cu:
        item_dict['primary_count_unit_id'] = primary_cu.uom_id
        item_dict['primary_count_unit_name'] = primary_cu.uom_name
        item_dict['primary_count_unit_abbr'] = primary_cu.uom_abbreviation

    # Count Unit 1 (preferred counting unit — display_order=0)
    if len(count_units) >= 1:
        cu1 = count_units[0]
        item_dict['count_unit_1_id'] = cu1.uom_id
        item_dict['count_unit_1_name'] = cu1.uom_name
        item_dict['count_unit_1_factor'] = float(cu1.conversion_to_primary) if cu1.conversion_to_primary else None
    else:
        item_dict['count_unit_1_id'] = None
        item_dict['count_unit_1_name'] = None
        item_dict['count_unit_1_factor'] = None

    # Count Unit 2 (second by display_order)
    if len(count_units) >= 2:
        cu2 = count_units[1]
        item_dict['count_unit_2_id'] = cu2.uom_id
        item_dict['count_unit_2_name'] = cu2.uom_name
        item_dict['count_unit_2_factor'] = float(cu2.conversion_to_primary) if cu2.conversion_to_primary else None
    else:
        item_dict['count_unit_2_id'] = None
        item_dict['count_unit_2_name'] = None
        item_dict['count_unit_2_factor'] = None

    # Count Unit 3 (third by display_order)
    if len(count_units) >= 3:
        cu3 = count_units[2]
        item_dict['count_unit_3_id'] = cu3.uom_id
        item_dict['count_unit_3_name'] = cu3.uom_name
        item_dict['count_unit_3_factor'] = float(cu3.conversion_to_primary) if cu3.conversion_to_primary else None
    else:
        item_dict['count_unit_3_id'] = None
        item_dict['count_unit_3_name'] = None
        item_dict['count_unit_3_factor'] = None

    # Include all count units for advanced UI
    item_dict['count_units'] = [
        {
            'id': cu.id,
            'uom_id': cu.uom_id,
            'uom_name': cu.uom_name,
            'uom_abbreviation': cu.uom_abbreviation,
            'is_primary': cu.is_primary,
            'conversion_to_primary': float(cu.conversion_to_primary) if cu.conversion_to_primary else 1.0,
            'display_order': cu.display_order or 0,
            'is_active': cu.is_active if cu.is_active is not None else True
        }
        for cu in count_units
    ]

    return item_dict

@router.get("/{item_id}/location-costs")
async def get_item_location_costs(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost comparison by location for a master item.

    Uses the MasterItemLocationCost table for weighted average costs.
    Invoice data is now managed by Integration Hub.
    """
    from sqlalchemy import func, desc
    from restaurant_inventory.models.location import Location
    from restaurant_inventory.models.master_item_location_cost import MasterItemLocationCost, MasterItemLocationCostHistory

    results = []

    # Get the master item's default cost (fallback when no location-specific data)
    from restaurant_inventory.models.item import MasterItem
    master_item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    default_cost = float(master_item.average_cost) if master_item and master_item.average_cost else None

    # Get data from MasterItemLocationCost table
    location_costs = db.query(
        MasterItemLocationCost,
        Location.name.label('location_name')
    ).join(
        Location, Location.id == MasterItemLocationCost.location_id
    ).filter(
        MasterItemLocationCost.master_item_id == item_id
    ).all()

    if location_costs:
        # Use data from MasterItemLocationCost - show ALL locations
        for cost_record, location_name in location_costs:
            # Determine if this location has actual invoice-based cost data
            has_invoice_data = (
                cost_record.last_purchase_cost is not None or
                cost_record.last_purchase_date is not None
            )

            # Use weighted avg cost if available (from invoices or seeded from vendor items)
            if cost_record.current_weighted_avg_cost:
                avg_price = float(cost_record.current_weighted_avg_cost)
                is_default_cost = not has_invoice_data
            else:
                avg_price = default_cost
                is_default_cost = True

            results.append({
                'location_id': cost_record.location_id,
                'location_name': location_name,
                'invoice_count': 0,  # Invoice data now in Integration Hub
                'last_price': float(cost_record.last_purchase_cost) if cost_record.last_purchase_cost else None,
                'avg_price': avg_price,
                'last_invoice_date': cost_record.last_purchase_date.isoformat() if cost_record.last_purchase_date else None,
                'qty_on_hand': float(cost_record.total_qty_on_hand) if cost_record.total_qty_on_hand else 0,
                'last_updated': cost_record.last_updated.isoformat() if cost_record.last_updated else None,
                'is_default_cost': is_default_cost
            })

    if not results:
        return []

    # Calculate overall average and variance for each location
    total_weighted = 0
    total_count = 0
    for result in results:
        if result['avg_price'] and result['invoice_count']:
            total_weighted += result['avg_price'] * result['invoice_count']
            total_count += result['invoice_count']

    if total_count > 0:
        overall_avg = total_weighted / total_count
        for result in results:
            if result['avg_price'] and overall_avg > 0:
                result['variance_pct'] = ((result['avg_price'] - overall_avg) / overall_avg) * 100
            else:
                result['variance_pct'] = None
    else:
        for result in results:
            result['variance_pct'] = None

    return results


@router.get("/{item_id}/cost-history")
async def get_item_cost_history(
    item_id: int,
    location_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost change history for a master item.

    Args:
        item_id: Master item ID
        location_id: Optional filter by location
        limit: Max number of records to return (default 50)

    Returns:
        List of cost history records
    """
    from sqlalchemy import desc
    from restaurant_inventory.models.location import Location
    from restaurant_inventory.models.master_item_location_cost import MasterItemLocationCostHistory

    query = db.query(
        MasterItemLocationCostHistory,
        Location.name.label('location_name')
    ).join(
        Location, Location.id == MasterItemLocationCostHistory.location_id
    ).filter(
        MasterItemLocationCostHistory.master_item_id == item_id
    )

    if location_id:
        query = query.filter(MasterItemLocationCostHistory.location_id == location_id)

    records = query.order_by(
        desc(MasterItemLocationCostHistory.created_at)
    ).limit(limit).all()

    return [
        {
            'id': record.id,
            'location_id': record.location_id,
            'location_name': location_name,
            'event_type': record.event_type,
            'old_cost': float(record.old_cost) if record.old_cost else None,
            'new_cost': float(record.new_cost) if record.new_cost else None,
            'change_qty': float(record.change_qty) if record.change_qty else None,
            'change_cost_per_unit': float(record.change_cost_per_unit) if record.change_cost_per_unit else None,
            'old_qty': float(record.old_qty) if record.old_qty else None,
            'new_qty': float(record.new_qty) if record.new_qty else None,
            'invoice_id': record.invoice_id,
            'notes': record.notes,
            'created_at': record.created_at.isoformat() if record.created_at else None
        }
        for record, location_name in records
    ]


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
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")
        def get_now(): return datetime.now(_ET)
        item.last_cost_update = get_now()

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

    # Explicitly convert to response schema to avoid ORM serialization issues
    return MasterItemResponse.from_orm(item)

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
        "primary_uom_id": item.primary_uom_id,
        "current_cost": float(item.current_cost) if item.current_cost else None
    }

    # Update cost timestamp if cost is being updated
    update_data = item_data.dict(exclude_unset=True)
    if "current_cost" in update_data and update_data["current_cost"] is not None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _ET = ZoneInfo("America/New_York")
        def get_now(): return datetime.now(_ET)
        update_data["last_cost_update"] = get_now()

    # If primary_uom_id is being set, fetch the UoM details from Hub to cache name/abbr
    if "primary_uom_id" in update_data and update_data["primary_uom_id"] is not None:
        hub_uom_id = update_data["primary_uom_id"]
        try:
            from sqlalchemy import create_engine, text
            hub_engine = create_engine(HUB_DATABASE_URL)
            with hub_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT id, name, abbreviation FROM units_of_measure WHERE id = :uom_id
                """), {"uom_id": hub_uom_id}).fetchone()
                if result:
                    update_data["primary_uom_name"] = result[1]
                    update_data["primary_uom_abbr"] = result[2]
                else:
                    logger.warning(f"Hub UoM {hub_uom_id} not found, using ID only")
        except Exception as e:
            logger.warning(f"Could not fetch Hub UoM details: {e}")

    # Update fields that were provided
    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    # Track new values
    new_data = {
        "name": item.name,
        "category": item.category,
        "primary_uom_id": item.primary_uom_id,
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

    # If name changed, sync to Hub's cached vendor item names
    if old_data["name"] != new_data["name"]:
        try:
            import httpx
            hub_api_url = os.getenv("HUB_API_URL", "http://integration-hub:8000")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{hub_api_url}/api/v1/vendor-items/sync-master-item-name/{item_id}",
                    params={"name": new_data["name"]}
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Synced master item name to Hub: {result.get('vendor_items_updated', 0)} vendor items updated")
                else:
                    logger.warning(f"Failed to sync master item name to Hub: {response.status_code}")
        except Exception as e:
            logger.warning(f"Could not sync master item name to Hub: {e}")

    # Explicitly convert to response schema to avoid ORM serialization issues
    return MasterItemResponse.from_orm(item)

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

    # Note: Invoice items are now managed by Integration Hub, not checked here

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

    # Explicitly delete location cost history and location costs first
    # (SQLAlchemy ORM can interfere with database-level cascades)
    from restaurant_inventory.models.master_item_location_cost import (
        MasterItemLocationCost, MasterItemLocationCostHistory
    )

    # Delete history records first (child of location_cost)
    db.query(MasterItemLocationCostHistory).filter(
        MasterItemLocationCostHistory.master_item_id == item_id
    ).delete(synchronize_session=False)

    # Delete location cost records
    db.query(MasterItemLocationCost).filter(
        MasterItemLocationCost.master_item_id == item_id
    ).delete(synchronize_session=False)

    db.delete(item)
    db.commit()
    return {"message": "Master item deleted successfully"}


@router.post("/parse-vendor-upload")
async def parse_vendor_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Parse an uploaded vendor item list (CSV or Excel)"""
    from restaurant_inventory.core.vendor_item_parser import VendorItemParser

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
        parser = VendorItemParser()
        result = parser.parse_file(temp_path, file_ext[1:])  # Remove the dot from extension

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse vendor file")
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
        print(f"ERROR in parse_vendor_upload: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview-vendor-items")
async def preview_vendor_items(
    file: UploadFile = File(...),
    column_mapping: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Preview all items from vendor file with column mapping"""
    from restaurant_inventory.core.vendor_item_parser import VendorItemParser
    from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
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

    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # First, read the file to get raw data and find combined unit size field
        parser = VendorItemParser()
        import pandas as pd
        if file_ext == '.csv':
            df = pd.read_csv(temp_path)
        else:
            df = pd.read_excel(temp_path)

        raw_result = parser.parse_file(temp_path, file_ext[1:], None)

        # Parse the file with mapping to get ALL items
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse vendor file")
            )

        items_data = result.get("data", {}).get("items", [])

        # Post-process: Extract units from combined "Unit size" field
        # The vendor has "Unit size" (e.g., "5.0 LB") separate from "Pack size" (e.g., 6)
        if raw_result.get("success") and items_data:
            raw_data = raw_result.get("data", {})
            raw_sample_rows = raw_data.get("sample_rows", [])
            raw_columns = raw_data.get("columns", [])

            # Find the vendor column that contains combined unit info
            unit_size_column = None
            for col in raw_columns:
                col_lower = col.lower().strip()
                # Look for "unit size" or similar
                if ("unit" in col_lower and "size" in col_lower) or col_lower == "unit size":
                    if raw_sample_rows and len(raw_sample_rows) > 0:
                        sample_value = str(raw_sample_rows[0].get(col, ""))
                        # Check if it contains combined format (number + space + letters)
                        if " " in sample_value and any(c.isalpha() for c in sample_value):
                            unit_size_column = col
                            break

            # If we found the unit size column, parse it for ALL rows
            if unit_size_column:
                # Extract both size and unit for each item from the DataFrame
                for i, item_data in enumerate(items_data):
                    if i < len(df):
                        raw_unit_value = df.iloc[i][unit_size_column]
                        size, unit = parser.parse_unit_size(str(raw_unit_value))
                        if unit:
                            item_data['unit'] = unit
                        if size:
                            # This is the weight/volume of each individual unit in the pack
                            # e.g., "5.0 LB" means each bag is 5 pounds
                            item_data['unit_size'] = size

        # Get all available units from the system
        units = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).all()
        unit_options = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation} for u in units]

        # For each item, try to auto-match the unit and clean up currency
        # Common vendor abbreviation mappings
        vendor_unit_mappings = {
            'co': 'ea',      # Count → Each
            'count': 'ea',   # Count → Each
            'foz': 'fl oz',  # Fluid Ounce
            'floz': 'fl oz', # Fluid Ounce
            'ct': 'ea',      # Count → Each
        }

        for item in items_data:
            item_unit = item.get("unit", "").strip().lower()
            matched_unit = None

            # Apply vendor mapping if needed
            mapped_unit = vendor_unit_mappings.get(item_unit, item_unit)

            # Try to match by name or abbreviation
            for unit in units:
                if (unit.name and unit.name.lower() == mapped_unit) or \
                   (unit.abbreviation and unit.abbreviation.lower() == mapped_unit):
                    matched_unit = unit.id
                    break

            item["matched_unit_id"] = matched_unit
            item["original_unit"] = item.get("unit", "")

            # Clean up unit_cost if it's a string with currency formatting
            if "unit_cost" in item:
                unit_cost_value = item.get("unit_cost")
                if isinstance(unit_cost_value, str):
                    # Remove $ sign, commas, and whitespace
                    cleaned_value = unit_cost_value.replace("$", "").replace(",", "").strip()
                    try:
                        item["unit_cost"] = float(cleaned_value)
                    except (ValueError, AttributeError):
                        item["unit_cost"] = None

        return {
            "success": True,
            "items": items_data,
            "total": len(items_data),
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
        print(f"ERROR in preview_vendor_items: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """Import vendor items using specified column and unit mappings"""
    from restaurant_inventory.core.vendor_item_parser import VendorItemParser
    from restaurant_inventory.models.vendor import Vendor
    import json

    # Validate vendor_id
    try:
        vendor_id_int = int(vendor_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid vendor ID"
        )

    # Verify vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id_int).first()
    if not vendor:
        raise HTTPException(
            status_code=404,
            detail="Vendor not found"
        )

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

    # Parse unit_mappings from JSON string (maps vendor_item_code -> unit_id)
    unit_mappings_dict = {}
    if unit_mappings:
        try:
            unit_mappings_dict = json.loads(unit_mappings)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid unit mappings format"
            )

    # Parse update_existing
    update_existing_bool = update_existing.lower() == "true"

    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # First, read the file to get raw data and find combined unit size field
        parser = VendorItemParser()
        import pandas as pd
        if file_ext == '.csv':
            df = pd.read_csv(temp_path)
        else:
            df = pd.read_excel(temp_path)

        raw_result = parser.parse_file(temp_path, file_ext[1:], None)

        # Parse the file with mapping
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse vendor file")
            )

        items_data = result.get("data", {}).get("items", [])

        # Post-process: Extract units from combined "Unit size" field
        if raw_result.get("success") and items_data:
            raw_data = raw_result.get("data", {})
            raw_sample_rows = raw_data.get("sample_rows", [])
            raw_columns = raw_data.get("columns", [])

            # Find the vendor column that contains combined unit info
            unit_size_column = None
            for col in raw_columns:
                col_lower = col.lower().strip()
                if ("unit" in col_lower and "size" in col_lower) or col_lower == "unit size":
                    if raw_sample_rows and len(raw_sample_rows) > 0:
                        sample_value = str(raw_sample_rows[0].get(col, ""))
                        if " " in sample_value and any(c.isalpha() for c in sample_value):
                            unit_size_column = col
                            break

            # If we found the unit size column, parse it for ALL rows
            if unit_size_column:
                for i, item_data in enumerate(items_data):
                    if i < len(df):
                        raw_unit_value = df.iloc[i][unit_size_column]
                        size, unit = parser.parse_unit_size(str(raw_unit_value))
                        if unit:
                            item_data['unit'] = unit
                        if size:
                            item_data['unit_size'] = size

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for item_data in items_data:
            vendor_sku = item_data.get("vendor_item_code")
            vendor_product_name = item_data.get("name")

            # Convert vendor_sku to string (in case it's a number from Excel)
            if vendor_sku is not None:
                vendor_sku = str(vendor_sku)

            # Clean up unit_cost if it's a string with currency formatting
            if "unit_cost" in item_data and item_data.get("unit_cost"):
                unit_cost_value = item_data.get("unit_cost")
                if isinstance(unit_cost_value, str):
                    # Remove $ sign, commas, and whitespace
                    cleaned_value = unit_cost_value.replace("$", "").replace(",", "").strip()
                    try:
                        item_data["unit_cost"] = float(cleaned_value)
                    except (ValueError, AttributeError):
                        item_data["unit_cost"] = None

            # Skip if no name
            if not vendor_product_name:
                skipped_count += 1
                continue

            # Get the mapped unit_id for this item (if provided)
            purchase_unit_id = unit_mappings_dict.get(vendor_sku) if vendor_sku else None

            if not purchase_unit_id:
                # If no unit mapping provided, skip this item
                skipped_count += 1
                continue

            # Try to find existing Master Item by name (exact match)
            # Do NOT auto-create master items - import vendor items as "Not Linked"
            master_item = db.query(MasterItem).filter(
                MasterItem.name.ilike(vendor_product_name.strip())
            ).first()

            # master_item can be None - vendor item will be imported as "Not Linked"
            master_item_id = master_item.id if master_item else None

            # Try to find existing Vendor Item
            existing_vendor_item = None
            if master_item_id:
                # Check by vendor and master item combination
                existing_vendor_item = db.query(VendorItem).filter(
                    VendorItem.vendor_id == vendor_id_int,
                    VendorItem.master_item_id == master_item_id
                ).first()

            # Also check if there's one with matching vendor_sku
            if not existing_vendor_item and vendor_sku:
                existing_vendor_item = db.query(VendorItem).filter(
                    VendorItem.vendor_id == vendor_id_int,
                    VendorItem.vendor_sku == vendor_sku
                ).first()

            # Calculate conversion factor if we have both pack_size and unit_size
            # conversion_factor = how many master item units are in one purchase unit (case)
            # Example: 6 bags × 5.0 LB per bag = 30 LB per case
            conversion_factor = 1.0  # Default
            if item_data.get("pack_size") and item_data.get("unit_size"):
                try:
                    pack_count = float(item_data.get("pack_size"))
                    size_per_unit = float(item_data.get("unit_size"))
                    conversion_factor = pack_count * size_per_unit
                except (ValueError, TypeError):
                    conversion_factor = 1.0

            if existing_vendor_item and update_existing_bool:
                # Update existing vendor item
                existing_vendor_item.vendor_product_name = vendor_product_name
                existing_vendor_item.vendor_sku = vendor_sku
                existing_vendor_item.purchase_unit_id = purchase_unit_id
                existing_vendor_item.pack_size = str(item_data.get("pack_size")) if item_data.get("pack_size") else None
                existing_vendor_item.conversion_factor = conversion_factor

                # Update price if provided
                if item_data.get("unit_cost"):
                    try:
                        new_price = float(item_data.get("unit_cost"))
                        existing_vendor_item.unit_price = new_price
                    except (ValueError, TypeError):
                        pass

                updated_count += 1

            elif not existing_vendor_item:
                # Create new Vendor Item
                unit_price = None
                if item_data.get("unit_cost"):
                    try:
                        unit_price = float(item_data.get("unit_cost"))
                    except (ValueError, TypeError):
                        pass

                new_vendor_item = VendorItem(
                    vendor_id=vendor_id_int,
                    master_item_id=master_item_id,  # Can be None - "Not Linked"
                    vendor_sku=vendor_sku,
                    vendor_product_name=vendor_product_name,
                    purchase_unit_id=purchase_unit_id,
                    pack_size=str(item_data.get("pack_size")) if item_data.get("pack_size") else None,
                    conversion_factor=conversion_factor,
                    unit_price=unit_price,
                    is_active=True
                )
                db.add(new_vendor_item)
                created_count += 1
            else:
                # Existing item but update_existing is False
                skipped_count += 1

        db.commit()

        # Log the import
        log_audit_event(
            db=db,
            user=current_user,
            action="import_vendor_items",
            entity_type="vendor_item",
            entity_id=vendor_id_int,
            changes={
                "vendor_id": vendor_id_int,
                "vendor_name": vendor.name,
                "filename": file.filename,
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count
            }
        )

        return {
            "success": True,
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "total": len(items_data)
        }

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


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
# Item Unit Conversions API (DEPRECATED - Use count-units instead)
# ============================================================================

@router.get("/{item_id}/unit-conversions", deprecated=True)
async def get_item_unit_conversions(
    response: Response,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    DEPRECATED: Use GET /{item_id}/count-units instead.

    Get all unit conversions for a master item.
    This endpoint is deprecated. Unit conversions are now managed through
    MasterItemCountUnit with conversion_to_primary field.

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
    # Add deprecation headers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-04-01"
    response.headers["Link"] = f'</{item_id}/count-units>; rel="successor-version"'
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion

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
        # Use cached Hub UoM names (stored on the conversion record)
        result.append({
            "id": conv.id,
            "from_unit": {
                "id": conv.from_unit_id,
                "name": conv.from_unit_name or f"UoM {conv.from_unit_id}",
                "abbreviation": conv.from_unit_abbr or "?"
            },
            "to_unit": {
                "id": conv.to_unit_id,
                "name": conv.to_unit_name or f"UoM {conv.to_unit_id}",
                "abbreviation": conv.to_unit_abbr or "?"
            },
            "conversion_factor": float(conv.conversion_factor),
            "individual_weight_oz": float(conv.individual_weight_oz) if conv.individual_weight_oz else None,
            "individual_volume_oz": float(conv.individual_volume_oz) if conv.individual_volume_oz else None,
            "notes": conv.notes
        })

    return result


@router.post("/{item_id}/unit-conversions", deprecated=True)
async def create_item_unit_conversion(
    response: Response,
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
    DEPRECATED: Use PUT /{item_id}/count-units instead.

    Create a new unit conversion for a master item.
    This endpoint is deprecated. Use count-units endpoints to add units
    with conversion_to_primary and individual specs.

    Example: For 2oz sausage patties:
    - from_unit_id: Hub UoM ID for Pound
    - to_unit_id: Hub UoM ID for Each
    - conversion_factor: 8 (8 patties per pound)
    - individual_weight_oz: 2 (each patty is 2oz)

    Note: Unit IDs are Hub UoM IDs (source of truth), not local Inventory UoM IDs.
    """
    # Add deprecation headers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-04-01"
    response.headers["Link"] = f'</{item_id}/count-units>; rel="successor-version"'
    from restaurant_inventory.models.item_unit_conversion import ItemUnitConversion
    from sqlalchemy import text, create_engine

    # Verify item exists
    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    # Fetch unit details from Hub (source of truth for UoMs)
    from_unit_name = None
    from_unit_abbr = None
    to_unit_name = None
    to_unit_abbr = None

    try:
        hub_engine = create_engine(HUB_DATABASE_URL)
        with hub_engine.connect() as conn:
            # Get from_unit details
            from_result = conn.execute(text("""
                SELECT id, name, abbreviation FROM units_of_measure WHERE id = :uom_id
            """), {"uom_id": from_unit_id}).fetchone()
            if from_result:
                from_unit_name = from_result[1]
                from_unit_abbr = from_result[2]
            else:
                raise HTTPException(status_code=400, detail=f"From unit {from_unit_id} not found")

            # Get to_unit details
            to_result = conn.execute(text("""
                SELECT id, name, abbreviation FROM units_of_measure WHERE id = :uom_id
            """), {"uom_id": to_unit_id}).fetchone()
            if to_result:
                to_unit_name = to_result[1]
                to_unit_abbr = to_result[2]
            else:
                raise HTTPException(status_code=400, detail=f"To unit {to_unit_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Hub UoM details: {e}")
        raise HTTPException(status_code=503, detail="Unable to fetch unit details from Hub")

    # Check for existing conversion (including soft-deleted ones)
    existing = db.query(ItemUnitConversion).filter(
        ItemUnitConversion.master_item_id == item_id,
        ItemUnitConversion.from_unit_id == from_unit_id,
        ItemUnitConversion.to_unit_id == to_unit_id
    ).first()

    if existing:
        if existing.is_active:
            raise HTTPException(status_code=400, detail="Conversion already exists for this unit pair")
        # Reactivate soft-deleted conversion with new values
        existing.conversion_factor = conversion_factor
        existing.individual_weight_oz = individual_weight_oz
        existing.individual_volume_oz = individual_volume_oz
        existing.notes = notes
        existing.is_active = True
        existing.from_unit_name = from_unit_name
        existing.from_unit_abbr = from_unit_abbr
        existing.to_unit_name = to_unit_name
        existing.to_unit_abbr = to_unit_abbr
        db.commit()
        db.refresh(existing)
        return {
            "id": existing.id,
            "from_unit": {"id": from_unit_id, "name": from_unit_name, "abbreviation": from_unit_abbr},
            "to_unit": {"id": to_unit_id, "name": to_unit_name, "abbreviation": to_unit_abbr},
            "conversion_factor": float(existing.conversion_factor),
            "individual_weight_oz": float(existing.individual_weight_oz) if existing.individual_weight_oz else None,
            "individual_volume_oz": float(existing.individual_volume_oz) if existing.individual_volume_oz else None,
            "notes": existing.notes,
            "is_active": existing.is_active
        }

    conversion = ItemUnitConversion(
        master_item_id=item_id,
        from_unit_id=from_unit_id,
        from_unit_name=from_unit_name,
        from_unit_abbr=from_unit_abbr,
        to_unit_id=to_unit_id,
        to_unit_name=to_unit_name,
        to_unit_abbr=to_unit_abbr,
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
            "id": from_unit_id,
            "name": from_unit_name,
            "abbreviation": from_unit_abbr
        },
        "to_unit": {
            "id": to_unit_id,
            "name": to_unit_name,
            "abbreviation": to_unit_abbr
        },
        "conversion_factor": float(conversion.conversion_factor),
        "individual_weight_oz": float(conversion.individual_weight_oz) if conversion.individual_weight_oz else None,
        "individual_volume_oz": float(conversion.individual_volume_oz) if conversion.individual_volume_oz else None,
        "notes": conversion.notes
    }


@router.put("/{item_id}/unit-conversions/{conversion_id}", deprecated=True)
async def update_item_unit_conversion(
    response: Response,
    item_id: int,
    conversion_id: int,
    conversion_factor: float = None,
    individual_weight_oz: float = None,
    individual_volume_oz: float = None,
    notes: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """DEPRECATED: Use PUT /{item_id}/count-units instead. Update an existing unit conversion."""
    # Add deprecation headers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-04-01"
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


@router.delete("/{item_id}/unit-conversions/{conversion_id}", deprecated=True)
async def delete_item_unit_conversion(
    response: Response,
    item_id: int,
    conversion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Delete (deactivate) a unit conversion.

    DEPRECATED: Use DELETE /{item_id}/count-units/{unit_id} instead.
    Unit conversions have been consolidated into count units.
    This endpoint will be removed after 2026-04-01.
    """
    # Add deprecation headers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-04-01"
    response.headers["Link"] = f'</{item_id}/count-units>; rel="successor-version"'

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


# ============================================================================
# Count Units API (Hub UOM Integration)
# ============================================================================

@router.get("/{item_id}/count-units")
async def get_item_count_units(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all count units for a master item.

    Returns the list of units this item can be counted in,
    with conversion factors to the primary unit.

    Example for Coca Cola:
    [
        {"uom_id": 1, "uom_name": "Each", "is_primary": true, "conversion_to_primary": 1.0},
        {"uom_id": 9, "uom_name": "Case", "is_primary": false, "conversion_to_primary": 24.0}
    ]
    """
    from restaurant_inventory.models.master_item_count_unit import MasterItemCountUnit

    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    count_units = db.query(MasterItemCountUnit).filter(
        MasterItemCountUnit.master_item_id == item_id,
        MasterItemCountUnit.is_active == True
    ).order_by(
        MasterItemCountUnit.is_primary.desc(),
        MasterItemCountUnit.display_order
    ).all()

    return [
        {
            "id": cu.id,
            "uom_id": cu.uom_id,
            "uom_name": cu.uom_name,
            "uom_abbreviation": cu.uom_abbreviation,
            "is_primary": cu.is_primary,
            "conversion_to_primary": float(cu.conversion_to_primary) if cu.conversion_to_primary else 1.0,
            "display_order": cu.display_order or 0,
            # New fields from UOM consolidation
            "individual_weight_oz": float(cu.individual_weight_oz) if cu.individual_weight_oz else None,
            "individual_volume_oz": float(cu.individual_volume_oz) if cu.individual_volume_oz else None,
            "notes": cu.notes,
            "is_active": cu.is_active if hasattr(cu, 'is_active') else True
        }
        for cu in count_units
    ]


@router.put("/{item_id}/count-units")
async def update_item_count_units(
    item_id: int,
    request: Request,
    primary_count_unit_id: Optional[int] = None,
    count_unit_2_id: Optional[int] = None,
    count_unit_2_factor: Optional[float] = None,
    count_unit_3_id: Optional[int] = None,
    count_unit_3_factor: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Update count units for a master item.

    Args:
        item_id: Master item ID
        primary_count_unit_id: Hub UOM ID for the primary count unit (e.g., Bottle)
        count_unit_2_id: Hub UOM ID for the second count unit (e.g., Case)
        count_unit_2_factor: Conversion factor (e.g., 24 means 1 Case = 24 primary units)
        count_unit_3_id: Hub UOM ID for the third count unit
        count_unit_3_factor: Conversion factor for third unit

    Example: Setting up Coca Cola to count by Case
        primary_count_unit_id: 7 (Bottle)
        count_unit_2_id: 9 (Case)
        count_unit_2_factor: 24 (1 Case = 24 bottles)
    """
    from restaurant_inventory.models.master_item_count_unit import MasterItemCountUnit

    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    # Get existing count units
    existing_units = db.query(MasterItemCountUnit).filter(
        MasterItemCountUnit.master_item_id == item_id
    ).all()

    # Separate primary from secondary
    primary_unit = next((cu for cu in existing_units if cu.is_primary), None)
    secondary_units = [cu for cu in existing_units if not cu.is_primary]

    # Look up UOM from Inventory's own units_of_measure table
    from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
    def get_uom_info(uom_id: int) -> dict:
        uom = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom_id).first()
        if uom:
            return {"name": uom.name, "abbreviation": uom.abbreviation}
        return None

    changes_made = []

    # Helper to find which count unit has this uom_id (if any)
    def find_unit_by_uom_id(uom_id: int):
        for cu in existing_units:
            if cu.uom_id == uom_id:
                return cu
        return None

    # Handle primary count unit update
    if primary_count_unit_id is not None and primary_count_unit_id != 0:
        # Check if this UOM is already used by another count unit for this item
        existing_with_uom = find_unit_by_uom_id(primary_count_unit_id)
        if existing_with_uom and existing_with_uom != primary_unit:
            # This unit is currently assigned as a secondary unit
            # User wants to make it primary - remove the secondary first
            logger.info(f"Removing secondary unit {existing_with_uom.uom_name} (id={existing_with_uom.id}) to make it primary")
            db.delete(existing_with_uom)
            db.flush()  # Flush delete before updating to avoid unique constraint violation
            # Also remove from our tracking list so subsequent checks don't see it
            existing_units = [cu for cu in existing_units if cu != existing_with_uom]
            secondary_units = [cu for cu in secondary_units if cu != existing_with_uom]
            changes_made.append(f"Promoted {existing_with_uom.uom_name} from secondary to primary")

        # Fetch UOM info from Hub
        uom_info = get_uom_info(primary_count_unit_id)
        if not uom_info:
            raise HTTPException(status_code=400, detail=f"UOM {primary_count_unit_id} not found")

        if primary_unit:
            # Update existing primary count unit
            primary_unit.uom_id = primary_count_unit_id
            primary_unit.uom_name = uom_info.get("name")
            primary_unit.uom_abbreviation = uom_info.get("abbreviation")
            changes_made.append(f"Updated primary count unit: {uom_info.get('name')}")
        else:
            # Create new primary count unit
            primary_unit = MasterItemCountUnit(
                master_item_id=item_id,
                uom_id=primary_count_unit_id,
                uom_name=uom_info.get("name"),
                uom_abbreviation=uom_info.get("abbreviation"),
                is_primary=True,
                conversion_to_primary=1.0,
                display_order=0
            )
            db.add(primary_unit)
            changes_made.append(f"Added primary count unit: {uom_info.get('name')}")

    # Handle count_unit_2
    if count_unit_2_id is not None:
        # Find or create count_unit_2
        cu2 = next((cu for cu in secondary_units if cu.display_order == 1), None)

        if count_unit_2_id == 0:
            # Remove count_unit_2
            if cu2:
                db.delete(cu2)
                changes_made.append("Removed count unit 2")
        else:
            # Check if this UOM is already used - if by cu3, swap them
            existing_with_uom = find_unit_by_uom_id(count_unit_2_id)
            if existing_with_uom and existing_with_uom != cu2:
                if existing_with_uom == primary_unit:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot use primary unit as secondary. Change primary unit first."
                    )
                # It's the other secondary (cu3) - remove it, we'll reassign this UOM to cu2
                logger.info(f"Reassigning {existing_with_uom.uom_name} from unit 3 to unit 2")
                db.delete(existing_with_uom)
                db.flush()  # Flush delete before updating to avoid unique constraint violation
                existing_units = [cu for cu in existing_units if cu != existing_with_uom]
                secondary_units = [cu for cu in secondary_units if cu != existing_with_uom]

            # Fetch UOM info from Hub
            uom_info = get_uom_info(count_unit_2_id)
            if not uom_info:
                raise HTTPException(status_code=400, detail=f"UOM {count_unit_2_id} not found")

            factor = count_unit_2_factor if count_unit_2_factor else 1.0

            if cu2:
                # Update existing
                cu2.uom_id = count_unit_2_id
                cu2.uom_name = uom_info.get("name")
                cu2.uom_abbreviation = uom_info.get("abbreviation")
                cu2.conversion_to_primary = factor
                changes_made.append(f"Updated count unit 2: {uom_info.get('name')} ({factor}x)")
            else:
                # Create new
                cu2 = MasterItemCountUnit(
                    master_item_id=item_id,
                    uom_id=count_unit_2_id,
                    uom_name=uom_info.get("name"),
                    uom_abbreviation=uom_info.get("abbreviation"),
                    is_primary=False,
                    conversion_to_primary=factor,
                    display_order=1
                )
                db.add(cu2)
                changes_made.append(f"Added count unit 2: {uom_info.get('name')} ({factor}x)")

    # Handle count_unit_3
    if count_unit_3_id is not None:
        cu3 = next((cu for cu in secondary_units if cu.display_order == 2), None)

        if count_unit_3_id == 0:
            # Remove count_unit_3
            if cu3:
                db.delete(cu3)
                changes_made.append("Removed count unit 3")
        else:
            # Check if this UOM is already used - if by cu2, swap them
            existing_with_uom = find_unit_by_uom_id(count_unit_3_id)
            if existing_with_uom and existing_with_uom != cu3:
                if existing_with_uom == primary_unit:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot use primary unit as secondary. Change primary unit first."
                    )
                # It's the other secondary (cu2) - remove it, we'll reassign this UOM to cu3
                logger.info(f"Reassigning {existing_with_uom.uom_name} from unit 2 to unit 3")
                db.delete(existing_with_uom)
                db.flush()  # Flush delete before updating to avoid unique constraint violation
                existing_units = [cu for cu in existing_units if cu != existing_with_uom]
                secondary_units = [cu for cu in secondary_units if cu != existing_with_uom]

            uom_info = get_uom_info(count_unit_3_id)
            if not uom_info:
                raise HTTPException(status_code=400, detail=f"UOM {count_unit_3_id} not found")

            factor = count_unit_3_factor if count_unit_3_factor else 1.0

            if cu3:
                cu3.uom_id = count_unit_3_id
                cu3.uom_name = uom_info.get("name")
                cu3.uom_abbreviation = uom_info.get("abbreviation")
                cu3.conversion_to_primary = factor
                changes_made.append(f"Updated count unit 3: {uom_info.get('name')} ({factor}x)")
            else:
                cu3 = MasterItemCountUnit(
                    master_item_id=item_id,
                    uom_id=count_unit_3_id,
                    uom_name=uom_info.get("name"),
                    uom_abbreviation=uom_info.get("abbreviation"),
                    is_primary=False,
                    conversion_to_primary=factor,
                    display_order=2
                )
                db.add(cu3)
                changes_made.append(f"Added count unit 3: {uom_info.get('name')} ({factor}x)")

    db.commit()

    # Log audit event
    if changes_made:
        log_audit_event(
            db=db,
            action="UPDATE_COUNT_UNITS",
            entity_type="item",
            entity_id=item_id,
            user=current_user,
            changes={"count_units": changes_made},
            request=request
        )

    # Return updated count units
    return await get_item_count_units(item_id, db, current_user)


@router.put("/{item_id}/count-unit-order")
async def update_count_unit_order(
    item_id: int,
    request: Request,
    count_unit_1_uom_id: int = None,
    count_unit_2_uom_id: Optional[int] = None,
    count_unit_3_uom_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Update the display order of count units for inventory counting.

    This only reorders existing count units — it does NOT create new ones
    or change conversion factors. Count units define which UOMs are available
    during inventory counts and their preferred order.

    Count Unit 1 is the default unit shown in inventory count sessions.
    """
    from restaurant_inventory.models.master_item_count_unit import MasterItemCountUnit

    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Master item not found")

    existing_units = db.query(MasterItemCountUnit).filter(
        MasterItemCountUnit.master_item_id == item_id
    ).all()

    if not existing_units:
        raise HTTPException(status_code=400, detail="No count units defined for this item. Add units in the Units of Measure section first.")

    # Build a lookup by uom_id
    unit_by_uom = {cu.uom_id: cu for cu in existing_units}

    # Validate all requested UOM IDs exist as count units for this item
    requested = [count_unit_1_uom_id]
    if count_unit_2_uom_id:
        requested.append(count_unit_2_uom_id)
    if count_unit_3_uom_id:
        requested.append(count_unit_3_uom_id)

    for uom_id in requested:
        if uom_id and uom_id not in unit_by_uom:
            raise HTTPException(
                status_code=400,
                detail=f"UOM ID {uom_id} is not a defined count unit for this item"
            )

    changes_made = []

    # Assign display_order based on the requested order
    # Units not in the requested list keep their current order but shifted after
    ordered_ids = [uid for uid in requested if uid]
    next_order = 0

    for uom_id in ordered_ids:
        cu = unit_by_uom[uom_id]
        if cu.display_order != next_order:
            changes_made.append(f"Reordered {cu.uom_name} to position {next_order + 1}")
            cu.display_order = next_order
        next_order += 1

    # Any remaining units not in the selection get pushed to the end
    for cu in existing_units:
        if cu.uom_id not in ordered_ids:
            if cu.display_order != next_order:
                cu.display_order = next_order
            next_order += 1

    db.commit()

    if changes_made:
        log_audit_event(
            db=db,
            action="REORDER_COUNT_UNITS",
            entity_type="item",
            entity_id=item_id,
            user=current_user,
            changes={"count_unit_order": changes_made},
            request=request
        )

    return await get_item_count_units(item_id, db, current_user)
