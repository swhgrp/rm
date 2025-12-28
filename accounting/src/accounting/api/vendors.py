"""
Vendor management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.vendor import Vendor
from accounting.models.vendor_alias import VendorAlias
from accounting.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse
from accounting.api.auth import require_auth, verify_hub_api_key
from accounting.services.vendor_service import VendorService

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


# ============================================================================
# AUTHENTICATED ENDPOINTS FOR INTEGRATION HUB - MUST BE FIRST!
# ============================================================================

@router.get("/_hub/sync")
def get_vendors_for_hub(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_hub_api_key)
):
    """
    Get all vendors for Integration Hub sync
    Requires X-Hub-API-Key header for authentication
    Returns vendor data in a format compatible with the hub (using 'name' instead of 'vendor_name')
    IMPORTANT: This route must be defined BEFORE /{vendor_id} route
    """
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.vendor_name).all()

    # Convert to dict format with 'name' field for hub compatibility
    vendor_list = []
    for v in vendors:
        vendor_list.append({
            "id": v.id,
            "name": v.vendor_name,  # Map vendor_name to name
            "contact_name": v.contact_name,
            "email": v.email,
            "phone": v.phone,
            "address": v.address_line1,
            "city": v.city,
            "state": v.state,
            "zip_code": v.zip_code,
            "tax_id": v.tax_id,
            "payment_terms": v.payment_terms,
            "is_active": v.is_active
        })

    return vendor_list


@router.post("/_hub/receive")
def receive_vendor_from_hub(
    vendor_data: dict,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_hub_api_key)
):
    """
    Receive vendor from Integration Hub
    Requires X-Hub-API-Key header for authentication
    """
    # Check if vendor already exists by name (using vendor_name field)
    vendor_name = vendor_data.get("name")
    existing_vendor = db.query(Vendor).filter(Vendor.vendor_name == vendor_name).first()

    if existing_vendor:
        # Update existing vendor
        existing_vendor.contact_name = vendor_data.get("contact_name") or existing_vendor.contact_name
        existing_vendor.email = vendor_data.get("email") or existing_vendor.email
        existing_vendor.phone = vendor_data.get("phone") or existing_vendor.phone
        existing_vendor.address_line1 = vendor_data.get("address") or existing_vendor.address_line1
        existing_vendor.city = vendor_data.get("city") or existing_vendor.city
        existing_vendor.state = vendor_data.get("state") or existing_vendor.state
        existing_vendor.zip_code = vendor_data.get("zip_code") or existing_vendor.zip_code
        existing_vendor.tax_id = vendor_data.get("tax_id") or existing_vendor.tax_id
        existing_vendor.payment_terms = vendor_data.get("payment_terms") or existing_vendor.payment_terms
        existing_vendor.is_active = vendor_data.get("is_active", existing_vendor.is_active)

        db.commit()
        db.refresh(existing_vendor)

        return {
            "success": True,
            "vendor_id": existing_vendor.id,
            "message": "Vendor updated"
        }
    else:
        # Create new vendor (mapping 'name' to 'vendor_name')
        new_vendor = Vendor(
            vendor_name=vendor_name,
            contact_name=vendor_data.get("contact_name", ""),
            email=vendor_data.get("email", ""),
            phone=vendor_data.get("phone", ""),
            address_line1=vendor_data.get("address", ""),
            city=vendor_data.get("city", ""),
            state=vendor_data.get("state", ""),
            zip_code=vendor_data.get("zip_code", ""),
            tax_id=vendor_data.get("tax_id", ""),
            payment_terms=vendor_data.get("payment_terms", "Net 30"),
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

@router.get("/", response_model=List[VendorResponse])
def list_vendors(
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    search: Optional[str] = Query(None, description="Search by vendor name or code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all vendors - available to all authenticated users"""
    query = db.query(Vendor)

    if not include_inactive:
        query = query.filter(Vendor.is_active == True)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Vendor.vendor_name.ilike(search_pattern)) |
            (Vendor.vendor_code.ilike(search_pattern))
        )

    vendors = query.order_by(Vendor.vendor_name).offset(skip).limit(limit).all()
    return vendors


@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific vendor by ID"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )
    return vendor


@router.post("/", response_model=VendorResponse)
def create_vendor(
    vendor_data: VendorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new vendor"""
    # Check if vendor name already exists
    existing_name = db.query(Vendor).filter(Vendor.vendor_name == vendor_data.vendor_name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor name already exists"
        )

    # Check if vendor code already exists (if provided)
    if vendor_data.vendor_code:
        existing_code = db.query(Vendor).filter(Vendor.vendor_code == vendor_data.vendor_code).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendor code already exists"
            )

    # Create new vendor
    new_vendor = Vendor(
        vendor_name=vendor_data.vendor_name,
        vendor_code=vendor_data.vendor_code,
        contact_name=vendor_data.contact_name,
        email=vendor_data.email,
        phone=vendor_data.phone,
        fax=vendor_data.fax,
        website=vendor_data.website,
        address_line1=vendor_data.address_line1,
        address_line2=vendor_data.address_line2,
        city=vendor_data.city,
        state=vendor_data.state,
        zip_code=vendor_data.zip_code,
        country=vendor_data.country,
        tax_id=vendor_data.tax_id,
        is_1099_vendor=vendor_data.is_1099_vendor,
        payment_terms=vendor_data.payment_terms,
        credit_limit=vendor_data.credit_limit,
        account_number=vendor_data.account_number,
        notes=vendor_data.notes
    )

    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)

    return new_vendor


@router.put("/{vendor_id}", response_model=VendorResponse)
def update_vendor(
    vendor_id: int,
    vendor_data: VendorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    # Update fields if provided
    if vendor_data.vendor_name is not None:
        # Check if name already exists for another vendor
        existing_name = db.query(Vendor).filter(
            Vendor.vendor_name == vendor_data.vendor_name,
            Vendor.id != vendor_id
        ).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendor name already exists"
            )
        vendor.vendor_name = vendor_data.vendor_name

    if vendor_data.vendor_code is not None:
        # Check if code already exists for another vendor
        existing_code = db.query(Vendor).filter(
            Vendor.vendor_code == vendor_data.vendor_code,
            Vendor.id != vendor_id
        ).first()
        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendor code already exists"
            )
        vendor.vendor_code = vendor_data.vendor_code

    # Update contact information
    if vendor_data.contact_name is not None:
        vendor.contact_name = vendor_data.contact_name
    if vendor_data.email is not None:
        vendor.email = vendor_data.email
    if vendor_data.phone is not None:
        vendor.phone = vendor_data.phone
    if vendor_data.fax is not None:
        vendor.fax = vendor_data.fax
    if vendor_data.website is not None:
        vendor.website = vendor_data.website

    # Update address
    if vendor_data.address_line1 is not None:
        vendor.address_line1 = vendor_data.address_line1
    if vendor_data.address_line2 is not None:
        vendor.address_line2 = vendor_data.address_line2
    if vendor_data.city is not None:
        vendor.city = vendor_data.city
    if vendor_data.state is not None:
        vendor.state = vendor_data.state
    if vendor_data.zip_code is not None:
        vendor.zip_code = vendor_data.zip_code
    if vendor_data.country is not None:
        vendor.country = vendor_data.country

    # Update tax information
    if vendor_data.tax_id is not None:
        vendor.tax_id = vendor_data.tax_id
    if vendor_data.is_1099_vendor is not None:
        vendor.is_1099_vendor = vendor_data.is_1099_vendor

    # Update payment terms
    if vendor_data.payment_terms is not None:
        vendor.payment_terms = vendor_data.payment_terms
    if vendor_data.credit_limit is not None:
        vendor.credit_limit = vendor_data.credit_limit

    # Update account number
    if vendor_data.account_number is not None:
        vendor.account_number = vendor_data.account_number

    # Update notes and status
    if vendor_data.notes is not None:
        vendor.notes = vendor_data.notes
    if vendor_data.is_active is not None:
        vendor.is_active = vendor_data.is_active

    db.commit()
    db.refresh(vendor)

    return vendor


@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete a vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    # TODO: Check if vendor has any bills before deleting
    # For now, we'll allow deletion

    db.delete(vendor)
    db.commit()

    return {"message": "Vendor deleted successfully"}


# ============================================================================
# VENDOR ALIAS ENDPOINTS
# ============================================================================

@router.get("/{vendor_id}/aliases")
def get_vendor_aliases(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all aliases for a vendor"""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    aliases = db.query(VendorAlias).filter(VendorAlias.vendor_id == vendor_id).all()

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.vendor_name,
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
def add_vendor_alias(
    vendor_id: int,
    alias_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Add an alias for a vendor

    Request body:
    {
        "alias_name": "Gordon Food Service Inc.",
        "case_insensitive": true  // optional, defaults to true
    }
    """
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found"
        )

    alias_name = alias_data.get("alias_name", "").strip()
    if not alias_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="alias_name is required"
        )

    # Check if alias already exists
    existing = db.query(VendorAlias).filter(VendorAlias.alias_name == alias_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alias '{alias_name}' already exists (maps to vendor_id={existing.vendor_id})"
        )

    vendor_service = VendorService(db)
    alias = vendor_service.add_alias(
        alias_name=alias_name,
        vendor_id=vendor_id,
        case_insensitive=alias_data.get("case_insensitive", True),
        created_by=current_user.id
    )
    db.commit()

    return {
        "success": True,
        "alias_id": alias.id,
        "message": f"Alias '{alias_name}' added for vendor '{vendor.vendor_name}'"
    }


@router.delete("/{vendor_id}/aliases/{alias_id}")
def delete_vendor_alias(
    vendor_id: int,
    alias_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
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
    db.delete(alias)
    db.commit()

    return {
        "success": True,
        "message": f"Alias '{alias_name}' deleted"
    }


@router.get("/aliases/all")
def get_all_aliases(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all vendor aliases with their canonical vendor names"""
    aliases = db.query(
        VendorAlias.id,
        VendorAlias.alias_name,
        VendorAlias.vendor_id,
        VendorAlias.case_insensitive,
        VendorAlias.created_at,
        Vendor.vendor_name.label("canonical_name")
    ).join(
        Vendor, VendorAlias.vendor_id == Vendor.id
    ).order_by(
        Vendor.vendor_name, VendorAlias.alias_name
    ).all()

    return [
        {
            "id": a.id,
            "alias_name": a.alias_name,
            "vendor_id": a.vendor_id,
            "canonical_name": a.canonical_name,
            "case_insensitive": a.case_insensitive,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in aliases
    ]


@router.post("/resolve-name")
def resolve_vendor_name(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Resolve a vendor name to its canonical form

    Request body:
    {
        "vendor_name": "Gordon Food Service Inc."
    }

    Returns the canonical vendor if found, or None
    """
    vendor_name = request.get("vendor_name", "").strip()
    if not vendor_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vendor_name is required"
        )

    vendor_service = VendorService(db)
    vendor, was_alias = vendor_service.resolve_vendor_name(vendor_name)

    if vendor:
        return {
            "found": True,
            "vendor_id": vendor.id,
            "canonical_name": vendor.vendor_name,
            "matched_via_alias": was_alias,
            "payment_terms": vendor.payment_terms
        }
    else:
        return {
            "found": False,
            "vendor_id": None,
            "canonical_name": None,
            "matched_via_alias": False,
            "message": f"No vendor found for '{vendor_name}'"
        }
