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
from restaurant_inventory.models.vendor_alias import VendorAlias
from restaurant_inventory.models.vendor_item import VendorItem
from restaurant_inventory.models.invoice import Invoice
from restaurant_inventory.models.user import User
from restaurant_inventory.core.audit import log_audit_event, create_change_dict

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

    # Check for related invoices
    invoice_count = db.query(Invoice).filter(Invoice.vendor_id == vendor_id).count()
    if invoice_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete vendor '{vendor.name}': {invoice_count} invoice(s) are associated with this vendor. Please reassign or delete the invoices first."
        )

    # Check for related vendor items (informational - they will cascade delete)
    vendor_item_count = db.query(VendorItem).filter(VendorItem.vendor_id == vendor_id).count()

    # Count aliases that will be deleted
    alias_count = db.query(VendorAlias).filter(VendorAlias.vendor_id == vendor_id).count()

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
            "email": vendor.email,
            "vendor_items_deleted": vendor_item_count,
            "aliases_deleted": alias_count
        }},
        request=request
    )

    # Delete aliases first to avoid SQLAlchemy relationship issues
    db.query(VendorAlias).filter(VendorAlias.vendor_id == vendor_id).delete()

    db.delete(vendor)
    db.commit()

    return {"message": f"Vendor deleted successfully. {vendor_item_count} vendor item(s) were also removed."}


# ============================================================================
# VENDOR ALIAS ENDPOINTS
# ============================================================================

class AliasCreate(BaseModel):
    alias_name: str
    case_insensitive: bool = True


class AliasResponse(BaseModel):
    id: int
    alias_name: str
    vendor_id: int
    case_insensitive: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/aliases/all")
async def get_all_aliases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all vendor aliases system-wide"""
    aliases = db.query(VendorAlias).join(Vendor).order_by(Vendor.name, VendorAlias.alias_name).all()

    result = []
    for alias in aliases:
        result.append({
            "id": alias.id,
            "alias_name": alias.alias_name,
            "vendor_id": alias.vendor_id,
            "canonical_name": alias.vendor.name,
            "case_insensitive": alias.case_insensitive,
            "created_at": alias.created_at.isoformat() if alias.created_at else None
        })

    return result


@router.get("/{vendor_id}/aliases")
async def get_vendor_aliases(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all aliases for a specific vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    aliases = db.query(VendorAlias).filter(VendorAlias.vendor_id == vendor_id).order_by(VendorAlias.alias_name).all()

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "aliases": [
            {
                "id": a.id,
                "alias_name": a.alias_name,
                "case_insensitive": a.case_insensitive,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in aliases
        ]
    }


@router.post("/{vendor_id}/aliases")
async def add_vendor_alias(
    vendor_id: int,
    alias_data: AliasCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add an alias for a vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    # Check if alias already exists
    alias_name = alias_data.alias_name.strip()
    if not alias_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alias name cannot be empty"
        )

    existing = db.query(VendorAlias).filter(VendorAlias.alias_name == alias_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alias '{alias_name}' already exists for vendor ID {existing.vendor_id}"
        )

    # Create alias
    alias = VendorAlias(
        alias_name=alias_name,
        vendor_id=vendor_id,
        case_insensitive=alias_data.case_insensitive,
        created_by=current_user.id
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="vendor_alias",
        entity_id=alias.id,
        user=current_user,
        changes={"new": {"alias_name": alias_name, "vendor_id": vendor_id}},
        request=request
    )

    return {
        "success": True,
        "alias": {
            "id": alias.id,
            "alias_name": alias.alias_name,
            "vendor_id": alias.vendor_id,
            "case_insensitive": alias.case_insensitive
        }
    }


@router.delete("/{vendor_id}/aliases/{alias_id}")
async def delete_vendor_alias(
    vendor_id: int,
    alias_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a vendor alias"""
    alias = db.query(VendorAlias).filter(
        VendorAlias.id == alias_id,
        VendorAlias.vendor_id == vendor_id
    ).first()

    if not alias:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alias not found"
        )

    alias_name = alias.alias_name

    # Log before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="vendor_alias",
        entity_id=alias_id,
        user=current_user,
        changes={"old": {"alias_name": alias_name, "vendor_id": vendor_id}},
        request=request
    )

    db.delete(alias)
    db.commit()

    return {"success": True, "message": f"Alias '{alias_name}' deleted"}


@router.post("/resolve-name")
async def resolve_vendor_name(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    Resolve a vendor name to its canonical vendor.
    Used by Integration Hub for invoice processing.
    No authentication required - internal API.
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

    # Step 3: Exact match on alias
    alias = db.query(VendorAlias).filter(
        VendorAlias.alias_name == vendor_name
    ).first()
    if alias:
        vendor = db.query(Vendor).filter(
            Vendor.id == alias.vendor_id,
            Vendor.is_active == True
        ).first()
        if vendor:
            return {
                "found": True,
                "vendor_id": vendor.id,
                "canonical_name": vendor.name,
                "matched_via_alias": True
            }

    # Step 4: Case-insensitive match on alias (only if case_insensitive flag is True)
    alias = db.query(VendorAlias).filter(
        func.lower(VendorAlias.alias_name) == func.lower(vendor_name),
        VendorAlias.case_insensitive == True
    ).first()
    if alias:
        vendor = db.query(Vendor).filter(
            Vendor.id == alias.vendor_id,
            Vendor.is_active == True
        ).first()
        if vendor:
            return {
                "found": True,
                "vendor_id": vendor.id,
                "canonical_name": vendor.name,
                "matched_via_alias": True
            }

    return {"found": False, "vendor_id": None, "canonical_name": None}
