"""
Count Template CRUD endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.count_template import CountTemplate, CountTemplateItem
from restaurant_inventory.models.storage_area import StorageArea
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.count_template import (
    CountTemplateCreate,
    CountTemplateUpdate,
    CountTemplateResponse,
    CountTemplateItemResponse
)

router = APIRouter()

@router.get("/", response_model=List[CountTemplateResponse])
async def get_count_templates(
    storage_area_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all count templates, optionally filtered by storage area"""
    query = db.query(CountTemplate).options(
        joinedload(CountTemplate.storage_area),
        joinedload(CountTemplate.created_by_user),
        joinedload(CountTemplate.items).joinedload(CountTemplateItem.master_item)
    )

    if storage_area_id:
        query = query.filter(CountTemplate.storage_area_id == storage_area_id)

    templates = query.all()

    response_data = []
    for template in templates:
        template_data = {
            "id": template.id,
            "storage_area_id": template.storage_area_id,
            "name": template.name,
            "description": template.description,
            "created_by": template.created_by,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "storage_area_name": template.storage_area.name if template.storage_area else None,
            "location_name": template.storage_area.location.name if template.storage_area and template.storage_area.location else None,
            "created_by_name": template.created_by_user.username if template.created_by_user else None,
            "item_count": len(template.items),
            "items": [
                CountTemplateItemResponse(
                    id=item.id,
                    template_id=item.template_id,
                    master_item_id=item.master_item_id,
                    sort_order=item.sort_order,
                    item_name=item.master_item.name if item.master_item else None,
                    item_category=item.master_item.category if item.master_item else None,
                    item_unit=item.master_item.unit.name if item.master_item and item.master_item.unit else None
                )
                for item in sorted(template.items, key=lambda x: x.sort_order)
            ]
        }
        response_data.append(CountTemplateResponse(**template_data))

    return response_data

@router.get("/{template_id}", response_model=CountTemplateResponse)
async def get_count_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific count template"""
    template = db.query(CountTemplate).options(
        joinedload(CountTemplate.storage_area),
        joinedload(CountTemplate.created_by_user),
        joinedload(CountTemplate.items).joinedload(CountTemplateItem.master_item)
    ).filter(CountTemplate.id == template_id).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count template not found"
        )

    template_data = {
        "id": template.id,
        "storage_area_id": template.storage_area_id,
        "name": template.name,
        "description": template.description,
        "created_by": template.created_by,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
        "storage_area_name": template.storage_area.name if template.storage_area else None,
        "location_name": template.storage_area.location.name if template.storage_area and template.storage_area.location else None,
        "created_by_name": template.created_by_user.username if template.created_by_user else None,
        "item_count": len(template.items),
        "items": [
            CountTemplateItemResponse(
                id=item.id,
                template_id=item.template_id,
                master_item_id=item.master_item_id,
                sort_order=item.sort_order,
                item_name=item.master_item.name if item.master_item else None,
                item_category=item.master_item.category if item.master_item else None,
                item_unit=item.master_item.unit_of_measure if item.master_item else None
            )
            for item in sorted(template.items, key=lambda x: x.sort_order)
        ]
    }

    return CountTemplateResponse(**template_data)

@router.post("/", response_model=CountTemplateResponse)
async def create_count_template(
    template_data: CountTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create new count template (Manager/Admin only)"""

    # Verify storage area exists
    storage_area = db.query(StorageArea).filter(StorageArea.id == template_data.storage_area_id).first()
    if not storage_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage area not found"
        )

    # Create template
    template = CountTemplate(
        storage_area_id=template_data.storage_area_id,
        name=template_data.name,
        description=template_data.description,
        created_by=current_user.id
    )

    db.add(template)
    db.flush()  # Get the template ID

    # Add items
    for idx, item_id in enumerate(template_data.item_ids):
        # Verify item exists
        master_item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
        if not master_item:
            continue  # Skip invalid items

        template_item = CountTemplateItem(
            template_id=template.id,
            master_item_id=item_id,
            sort_order=idx
        )
        db.add(template_item)

    db.commit()
    db.refresh(template)

    return await get_count_template(template.id, db, current_user)

@router.put("/{template_id}", response_model=CountTemplateResponse)
async def update_count_template(
    template_id: int,
    template_data: CountTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update count template (Manager/Admin only)"""

    template = db.query(CountTemplate).filter(CountTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count template not found"
        )

    # Update basic fields
    if template_data.name is not None:
        template.name = template_data.name
    if template_data.description is not None:
        template.description = template_data.description

    # Update items if provided
    if template_data.item_ids is not None:
        # Delete existing items
        db.query(CountTemplateItem).filter(CountTemplateItem.template_id == template_id).delete()

        # Add new items
        for idx, item_id in enumerate(template_data.item_ids):
            master_item = db.query(MasterItem).filter(MasterItem.id == item_id).first()
            if not master_item:
                continue

            template_item = CountTemplateItem(
                template_id=template.id,
                master_item_id=item_id,
                sort_order=idx
            )
            db.add(template_item)

    db.commit()
    db.refresh(template)

    return await get_count_template(template.id, db, current_user)

@router.delete("/{template_id}")
async def delete_count_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete count template (Manager/Admin only)"""

    template = db.query(CountTemplate).filter(CountTemplate.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Count template not found"
        )

    db.delete(template)
    db.commit()

    return {"message": "Count template deleted successfully"}