"""
Order Sheet Template CRUD endpoints

Templates reference hub vendor items (cross-database). Vendor item data
(name, sku, vendor, category, uom) is stored denormalized on the template
items and passed from the frontend during create/update.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from restaurant_inventory.core.deps import (
    get_db, get_current_user, require_manager_or_admin,
    filter_by_user_locations, get_user_location_ids
)
from restaurant_inventory.models.order_sheet_template import OrderSheetTemplate, OrderSheetTemplateItem
from restaurant_inventory.models.order_sheet import OrderSheet, OrderSheetStatus
from restaurant_inventory.models.location import Location
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.order_sheet_template import (
    OrderSheetTemplateCreate,
    OrderSheetTemplateUpdate,
    OrderSheetTemplateResponse,
    OrderSheetTemplateItemResponse
)

router = APIRouter()


def _build_template_response(template):
    """Build response dict from an OrderSheetTemplate with loaded relationships."""
    return OrderSheetTemplateResponse(
        id=template.id,
        location_id=template.location_id,
        name=template.name,
        description=template.description,
        is_active=template.is_active,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
        location_name=template.location.name if template.location else None,
        created_by_name=template.created_by_user.full_name if template.created_by_user else None,
        item_count=len(template.items),
        items=[
            OrderSheetTemplateItemResponse(
                id=item.id,
                template_id=item.template_id,
                hub_vendor_item_id=item.hub_vendor_item_id,
                par_level=item.par_level,
                sort_order=item.sort_order,
                item_name=item.item_name,
                vendor_sku=item.vendor_sku,
                vendor_name=item.vendor_name,
                category=item.category,
                unit_abbr=item.unit_abbr
            )
            for item in sorted(template.items, key=lambda x: x.sort_order)
        ]
    )


def _load_template(db: Session, template_id: int):
    """Load a template with all relationships eagerly loaded."""
    return db.query(OrderSheetTemplate).options(
        joinedload(OrderSheetTemplate.location),
        joinedload(OrderSheetTemplate.created_by_user),
        joinedload(OrderSheetTemplate.items)
    ).filter(OrderSheetTemplate.id == template_id).first()


@router.get("/", response_model=List[OrderSheetTemplateResponse])
async def get_order_sheet_templates(
    location_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all order sheet templates, filtered by user's locations"""
    query = db.query(OrderSheetTemplate).options(
        joinedload(OrderSheetTemplate.location),
        joinedload(OrderSheetTemplate.created_by_user),
        joinedload(OrderSheetTemplate.items)
    )

    # Filter by user's accessible locations
    query = filter_by_user_locations(query, OrderSheetTemplate.location_id, current_user)

    if location_id:
        query = query.filter(OrderSheetTemplate.location_id == location_id)

    if active_only:
        query = query.filter(OrderSheetTemplate.is_active == True)

    query = query.order_by(OrderSheetTemplate.location_id, OrderSheetTemplate.name)
    templates = query.all()

    return [_build_template_response(t) for t in templates]


@router.get("/{template_id}", response_model=OrderSheetTemplateResponse)
async def get_order_sheet_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific order sheet template"""
    template = _load_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Order sheet template not found")

    # Verify user has access to this location
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and template.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    return _build_template_response(template)


@router.post("/", response_model=OrderSheetTemplateResponse)
async def create_order_sheet_template(
    data: OrderSheetTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new order sheet template (Manager/Admin only)"""

    # Verify location exists
    location = db.query(Location).filter(Location.id == data.location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Verify user has access to this location
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and data.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Check for duplicate name at this location
    existing = db.query(OrderSheetTemplate).filter(
        OrderSheetTemplate.location_id == data.location_id,
        OrderSheetTemplate.name == data.name
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A template with this name already exists at this location")

    # Create template
    template = OrderSheetTemplate(
        location_id=data.location_id,
        name=data.name,
        description=data.description,
        is_active=data.is_active,
        created_by=current_user.id
    )
    db.add(template)
    db.flush()

    # Add items with denormalized vendor item snapshots
    for idx, item_data in enumerate(data.items):
        template_item = OrderSheetTemplateItem(
            template_id=template.id,
            hub_vendor_item_id=item_data.hub_vendor_item_id,
            par_level=item_data.par_level,
            sort_order=item_data.sort_order if item_data.sort_order else idx,
            item_name=item_data.item_name,
            vendor_sku=item_data.vendor_sku,
            vendor_name=item_data.vendor_name,
            category=item_data.category,
            unit_abbr=item_data.unit_abbr
        )
        db.add(template_item)

    db.commit()

    # Reload with relationships
    template = _load_template(db, template.id)
    return _build_template_response(template)


@router.put("/{template_id}", response_model=OrderSheetTemplateResponse)
async def update_order_sheet_template(
    template_id: int,
    data: OrderSheetTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update an order sheet template (Manager/Admin only)"""

    template = db.query(OrderSheetTemplate).filter(OrderSheetTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Order sheet template not found")

    # Verify user has access to this location
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and template.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Update basic fields
    if data.name is not None:
        # Check for duplicate name
        existing = db.query(OrderSheetTemplate).filter(
            OrderSheetTemplate.location_id == template.location_id,
            OrderSheetTemplate.name == data.name,
            OrderSheetTemplate.id != template_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="A template with this name already exists at this location")
        template.name = data.name

    if data.description is not None:
        template.description = data.description
    if data.is_active is not None:
        template.is_active = data.is_active

    # Replace items if provided (delete-and-recreate pattern)
    if data.items is not None:
        db.query(OrderSheetTemplateItem).filter(
            OrderSheetTemplateItem.template_id == template_id
        ).delete()

        for idx, item_data in enumerate(data.items):
            template_item = OrderSheetTemplateItem(
                template_id=template.id,
                hub_vendor_item_id=item_data.hub_vendor_item_id,
                par_level=item_data.par_level,
                sort_order=item_data.sort_order if item_data.sort_order else idx,
                item_name=item_data.item_name,
                vendor_sku=item_data.vendor_sku,
                vendor_name=item_data.vendor_name,
                category=item_data.category,
                unit_abbr=item_data.unit_abbr
            )
            db.add(template_item)

    db.commit()

    template = _load_template(db, template.id)
    return _build_template_response(template)


@router.delete("/{template_id}")
async def delete_order_sheet_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete an order sheet template (Manager/Admin only)"""

    template = db.query(OrderSheetTemplate).filter(OrderSheetTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Order sheet template not found")

    # Verify user has access
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and template.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Check for active draft order sheets using this template
    active_sheets = db.query(OrderSheet).filter(
        OrderSheet.template_id == template_id,
        OrderSheet.status == OrderSheetStatus.DRAFT
    ).count()
    if active_sheets > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: {active_sheets} draft order sheet(s) are using this template"
        )

    db.delete(template)
    db.commit()

    return {"message": "Order sheet template deleted successfully"}
