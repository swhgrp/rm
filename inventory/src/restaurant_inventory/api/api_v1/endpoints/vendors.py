"""
Vendor management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from sqlalchemy import func

from restaurant_inventory.core.deps import get_db, get_current_user
from restaurant_inventory.models.vendor import Vendor
from restaurant_inventory.models.user import User
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

# REMOVED (Dec 25, 2025): VendorItem, VendorAlias, Invoice - Hub is source of truth
# Vendor aliases are now managed in Hub

router = APIRouter()


# ============================================================================
# UNAUTHENTICATED ENDPOINTS FOR INTEGRATION HUB - MUST BE FIRST!
# ============================================================================

@router.get("/_hub/sync")
def get_vendors_for_hub(db: Session = Depends(get_db)):
    """
    Get all vendors for Integration Hub sync
    No authentication required - this is an internal API call from the hub
    IMPORTANT: This route must be defined BEFORE /{vendor_id} route
    Path starts with _ to avoid being matched by /{vendor_id} pattern
    """
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()
    vendor_list = []
    for v in vendors:
        vendor_list.append({
            "id": v.id,
            "name": v.name,
            "contact_name": v.contact_name,
            "email": v.email,
            "phone": v.phone,
            "address": v.address,
            "is_active": v.is_active
        })
    return vendor_list


@router.post("/_hub/receive")
def receive_vendor_from_hub(vendor_data: dict, db: Session = Depends(get_db)):
    """
    Receive vendor from Integration Hub
    No authentication required - this is an internal API call from the hub
    """
    # Check if vendor already exists by name
    existing_vendor = db.query(Vendor).filter(Vendor.name == vendor_data.get("name")).first()

    if existing_vendor:
        # Update existing vendor
        existing_vendor.contact_name = vendor_data.get("contact_name") or existing_vendor.contact_name
        existing_vendor.email = vendor_data.get("email") or existing_vendor.email
        existing_vendor.phone = vendor_data.get("phone") or existing_vendor.phone
        existing_vendor.address = vendor_data.get("address") or existing_vendor.address
        existing_vendor.is_active = vendor_data.get("is_active", existing_vendor.is_active)

        db.commit()
        db.refresh(existing_vendor)

        return {
            "success": True,
            "vendor_id": existing_vendor.id,
            "message": "Vendor updated"
        }
    else:
        # Create new vendor
        new_vendor = Vendor(
            name=vendor_data.get("name"),
            contact_name=vendor_data.get("contact_name", ""),
            email=vendor_data.get("email", ""),
            phone=vendor_data.get("phone", ""),
            address=vendor_data.get("address", ""),
            is_active=vendor_data.get("is_active", True)
        )

        db.add(new_vendor)
        db.commit()
        db.refresh(new_vendor)

        return {
            "success": True,
            "vendor_id": new_vendor.id,
            "message": "Vendor created"
        }


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

# Pydantic schemas
class VendorBase(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VendorResponse(VendorBase):
    id: int

    class Config:
        from_attributes = True


@router.get("/", response_model=List[VendorResponse])
async def list_vendors(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all vendors"""
    query = db.query(Vendor)

    if active_only:
        query = query.filter(Vendor.is_active == True)

    vendors = query.order_by(Vendor.name).all()

    # Clean up empty email strings to None for validation
    for vendor in vendors:
        if vendor.email == '':
            vendor.email = None

    return vendors


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    return vendor


@router.post("/", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    vendor_data: VendorCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new vendor"""

    # Check if vendor name already exists
    existing = db.query(Vendor).filter(Vendor.name == vendor_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor with this name already exists"
        )

    # Create vendor
    vendor = Vendor(**vendor_data.model_dump())
    db.add(vendor)
    db.commit()
    db.refresh(vendor)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="vendor",
        entity_id=vendor.id,
        user=current_user,
        changes={"new": vendor_data.model_dump()},
        request=request
    )

    return vendor


@router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: int,
    vendor_data: VendorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update vendor"""

    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    # Track changes
    old_data = {
        "name": vendor.name,
        "contact_name": vendor.contact_name,
        "email": vendor.email,
        "phone": vendor.phone,
        "address": vendor.address,
        "notes": vendor.notes,
        "is_active": vendor.is_active
    }

    # Update fields
    update_data = vendor_data.model_dump(exclude_unset=True)

    # Check if name is being changed and if it conflicts
    if 'name' in update_data and update_data['name'] != vendor.name:
        existing = db.query(Vendor).filter(
            Vendor.name == update_data['name'],
            Vendor.id != vendor_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another vendor with this name already exists"
            )

    for key, value in update_data.items():
        setattr(vendor, key, value)

    db.commit()
    db.refresh(vendor)

    # Track new values
    new_data = {
        "name": vendor.name,
        "contact_name": vendor.contact_name,
        "email": vendor.email,
        "phone": vendor.phone,
        "address": vendor.address,
        "notes": vendor.notes,
        "is_active": vendor.is_active
    }

    # Log audit event
    changes = create_change_dict(old_data, new_data)
    if changes:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="vendor",
            entity_id=vendor.id,
            user=current_user,
            changes=changes,
            request=request
        )

    return vendor


@router.delete("/{vendor_id}")
async def delete_vendor(
    vendor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete vendor"""

    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    # NOTE: Invoices, vendor items, and aliases are now in Hub (source of truth)
    # Deleting a vendor here only removes the local vendor record
    # The Hub should be notified separately if vendor data needs cleanup there

    # Log before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="vendor",
        entity_id=vendor.id,
        user=current_user,
        changes={"old": {
            "name": vendor.name,
            "contact_name": vendor.contact_name,
            "email": vendor.email
        }},
        request=request
    )

    db.delete(vendor)
    db.commit()

    return {"message": f"Vendor '{vendor.name}' deleted successfully. Note: Related data in Integration Hub should be cleaned up separately."}


# ============================================================================
# VENDOR ALIAS ENDPOINTS - DEPRECATED
# Vendor aliases are now managed in Integration Hub (source of truth)
# These endpoints remain for backward compatibility but redirect to Hub
# ============================================================================

@router.get("/aliases/all")
async def get_all_aliases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all vendor aliases system-wide.
    DEPRECATED: Vendor aliases are now managed in Integration Hub.
    """
    return {
        "message": "Vendor aliases have been moved to Integration Hub",
        "redirect": "/hub/vendors",
        "aliases": []
    }


@router.get("/{vendor_id}/aliases")
async def get_vendor_aliases(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all aliases for a specific vendor.
    DEPRECATED: Vendor aliases are now managed in Integration Hub.
    """
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "message": "Vendor aliases have been moved to Integration Hub",
        "redirect": "/hub/vendors",
        "aliases": []
    }


@router.post("/{vendor_id}/aliases")
async def add_vendor_alias(
    vendor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add an alias for a vendor.
    DEPRECATED: Vendor aliases are now managed in Integration Hub.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Vendor aliases are now managed in Integration Hub. Please use the Hub interface."
    )


@router.delete("/{vendor_id}/aliases/{alias_id}")
async def delete_vendor_alias(
    vendor_id: int,
    alias_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a vendor alias.
    DEPRECATED: Vendor aliases are now managed in Integration Hub.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Vendor aliases are now managed in Integration Hub. Please use the Hub interface."
    )


@router.post("/resolve-name")
async def resolve_vendor_name(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Resolve a vendor name to its canonical vendor.
    Used by Integration Hub for invoice processing.
    No authentication required - internal API.

    NOTE: This endpoint still works for basic vendor name matching.
    Alias matching is now done in Hub.
    """
    vendor_name = data.get("vendor_name", "").strip()
    if not vendor_name:
        return {"found": False, "vendor_id": None, "canonical_name": None}

    # Step 1: Exact match on vendor name
    vendor = db.query(Vendor).filter(
        Vendor.name == vendor_name,
        Vendor.is_active == True
    ).first()
    if vendor:
        return {
            "found": True,
            "vendor_id": vendor.id,
            "canonical_name": vendor.name,
            "matched_via_alias": False
        }

    # Step 2: Case-insensitive match on vendor name
    vendor = db.query(Vendor).filter(
        func.lower(Vendor.name) == func.lower(vendor_name),
        Vendor.is_active == True
    ).first()
    if vendor:
        return {
            "found": True,
            "vendor_id": vendor.id,
            "canonical_name": vendor.name,
            "matched_via_alias": False
        }

    # NOTE: Alias matching removed - now handled by Hub
    return {"found": False, "vendor_id": None, "canonical_name": None}
