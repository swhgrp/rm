"""
Vendor management API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from accounting.db.database import get_db
from accounting.models.user import User
from accounting.models.vendor import Vendor
from accounting.schemas.vendor import VendorCreate, VendorUpdate, VendorResponse
from accounting.api.auth import require_auth

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


# ============================================================================
# UNAUTHENTICATED ENDPOINTS FOR INTEGRATION HUB - MUST BE FIRST!
# ============================================================================

@router.get("/_hub/sync")
def get_vendors_for_hub(db: Session = Depends(get_db)):
    """
    Get all vendors for Integration Hub sync
    No authentication required - this is an internal API call from the hub
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
def receive_vendor_from_hub(vendor_data: dict, db: Session = Depends(get_db)):
    """
    Receive vendor from Integration Hub
    No authentication required - this is an internal API call from the hub
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
