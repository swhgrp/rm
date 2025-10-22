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

        if preferred_vendor_item and preferred_vendor_item.unit_price and preferred_vendor_item.conversion_factor:
            # Calculate cost per master unit (unit_price / conversion_factor)
            cost_per_master_unit = float(preferred_vendor_item.unit_price) / float(preferred_vendor_item.conversion_factor)
            item_dict['last_price_paid'] = cost_per_master_unit
            # Use the master item's unit of measure, not the vendor's purchase unit
            if item.unit_of_measure:
                item_dict['last_price_unit'] = item.unit_of_measure
            else:
                item_dict['last_price_unit'] = None
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
