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
from restaurant_inventory.models.vendor_item import VendorItem
from restaurant_inventory.models.unit_of_measure import UnitOfMeasure
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.item import MasterItemCreate, MasterItemUpdate, MasterItemResponse
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

router = APIRouter()

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
        joinedload(MasterItem.secondary_unit_rel)
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

    # Add unit names and pricing info to response
    result = []
    for item in items:
        item_dict = MasterItemResponse.from_orm(item).dict()
        item_dict['unit_name'] = item.unit.name if item.unit else item.unit_of_measure
        item_dict['secondary_unit_name'] = item.secondary_unit_rel.name if item.secondary_unit_rel else item.secondary_unit

        # Get last price paid from preferred vendor item, or most recent vendor item
        preferred_vendor_item = db.query(VendorItem).filter(
            VendorItem.master_item_id == item.id,
            VendorItem.is_preferred == True,
            VendorItem.is_active == True
        ).first()

        if not preferred_vendor_item:
            # Get most recent vendor item with a price
            preferred_vendor_item = db.query(VendorItem).filter(
                VendorItem.master_item_id == item.id,
                VendorItem.is_active == True,
                VendorItem.unit_price.isnot(None)
            ).order_by(desc(VendorItem.updated_at)).first()

        if preferred_vendor_item and preferred_vendor_item.unit_price:
            item_dict['last_price_paid'] = float(preferred_vendor_item.unit_price)
            # Get the purchase unit name
            purchase_unit = db.query(UnitOfMeasure).filter(
                UnitOfMeasure.id == preferred_vendor_item.purchase_unit_id
            ).first()
            if purchase_unit:
                item_dict['last_price_unit'] = purchase_unit.name
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

@router.get("/{item_id}", response_model=MasterItemResponse)
async def get_master_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific master item by ID"""
    item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Master item not found"
        )
    return item

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

    # Check if item has inventory records
    from restaurant_inventory.models.inventory import Inventory
    inventory_count = db.query(Inventory).filter(Inventory.master_item_id == item_id).count()

    if inventory_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete item with {inventory_count} inventory records. Please remove inventory first."
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

        # Parse the file with mapping to get ALL items
        parser = VendorItemParser()
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse vendor file")
            )

        # Get all available units from the system
        units = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).all()
        unit_options = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation} for u in units]

        items_data = result.get("data", {}).get("items", [])

        # For each item, try to auto-match the unit
        for item in items_data:
            item_unit = item.get("unit", "").strip().lower()
            matched_unit = None

            # Try to match by name or abbreviation
            for unit in units:
                if (unit.name and unit.name.lower() == item_unit) or \
                   (unit.abbreviation and unit.abbreviation.lower() == item_unit):
                    matched_unit = unit.id
                    break

            item["matched_unit_id"] = matched_unit
            item["original_unit"] = item.get("unit", "")

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

        # Parse the file with mapping
        parser = VendorItemParser()
        result = parser.parse_file(temp_path, file_ext[1:], column_mapping_dict)

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse vendor file")
            )

        items_data = result.get("data", {}).get("items", [])

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for item_data in items_data:
            vendor_sku = item_data.get("vendor_item_code")
            vendor_product_name = item_data.get("name")

            # Convert vendor_sku to string (in case it's a number from Excel)
            if vendor_sku is not None:
                vendor_sku = str(vendor_sku)

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

            # Try to find or create Master Item by name
            # Use fuzzy matching - look for exact match first, then similar names
            master_item = db.query(MasterItem).filter(
                MasterItem.name.ilike(vendor_product_name.strip())
            ).first()

            if not master_item:
                # Create new Master Item for this product
                master_item = MasterItem(
                    name=vendor_product_name.strip(),
                    category=item_data.get("category") or "other",
                    unit_of_measure_id=purchase_unit_id,  # Default to purchase unit
                    is_active=True
                )
                db.add(master_item)
                db.flush()  # Get the ID without committing

            # Try to find existing Vendor Item for this vendor/master_item combination
            existing_vendor_item = db.query(VendorItem).filter(
                VendorItem.vendor_id == vendor_id_int,
                VendorItem.master_item_id == master_item.id
            ).first()

            # Also check if there's one with matching vendor_sku
            if not existing_vendor_item and vendor_sku:
                existing_vendor_item = db.query(VendorItem).filter(
                    VendorItem.vendor_id == vendor_id_int,
                    VendorItem.vendor_sku == vendor_sku
                ).first()

            if existing_vendor_item and update_existing_bool:
                # Update existing vendor item
                existing_vendor_item.vendor_product_name = vendor_product_name
                existing_vendor_item.vendor_sku = vendor_sku
                existing_vendor_item.purchase_unit_id = purchase_unit_id
                existing_vendor_item.pack_size = item_data.get("pack_size")

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
                    master_item_id=master_item.id,
                    vendor_sku=vendor_sku,
                    vendor_product_name=vendor_product_name,
                    purchase_unit_id=purchase_unit_id,
                    pack_size=item_data.get("pack_size"),
                    conversion_factor=1.0,  # Default to 1:1, user can update later
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
