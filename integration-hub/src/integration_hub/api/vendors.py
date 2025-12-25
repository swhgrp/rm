"""
Vendor Management API Endpoints

Hub is the source of truth for vendors and vendor aliases.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from integration_hub.db.database import get_db
from integration_hub.models.vendor import Vendor
from integration_hub.models.vendor_alias import VendorAlias
from integration_hub.services.vendor_normalizer import VendorNormalizerService

router = APIRouter(prefix="/api/v1/vendors", tags=["vendors"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class VendorCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AliasCreate(BaseModel):
    alias_name: str
    vendor_id: int


class BulkAliasCreate(BaseModel):
    aliases: List[AliasCreate]


# ============================================================================
# VENDOR ENDPOINTS
# ============================================================================

@router.get("/")
async def list_vendors(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db)
):
    """List all vendors."""
    query = db.query(Vendor)
    if not include_inactive:
        query = query.filter(Vendor.is_active == True)

    vendors = query.order_by(Vendor.name).all()

    return [
        {
            'id': v.id,
            'name': v.name,
            'contact_name': v.contact_name,
            'email': v.email,
            'phone': v.phone,
            'address': v.address,
            'payment_terms': v.payment_terms,
            'notes': v.notes,
            'is_active': v.is_active,
            'inventory_vendor_id': v.inventory_vendor_id,
            'accounting_vendor_id': v.accounting_vendor_id
        }
        for v in vendors
    ]


@router.get("/summary")
async def get_vendor_summary(db: Session = Depends(get_db)):
    """
    Get vendor summary with invoice counts and aliases.
    Shows both linked and unlinked vendor names.
    """
    service = VendorNormalizerService(db)
    return service.get_vendor_summary()


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    """Get a single vendor by ID."""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Get aliases
    aliases = db.query(VendorAlias).filter(
        VendorAlias.vendor_id == vendor_id,
        VendorAlias.is_active == True
    ).all()

    return {
        'id': vendor.id,
        'name': vendor.name,
        'contact_name': vendor.contact_name,
        'email': vendor.email,
        'phone': vendor.phone,
        'address': vendor.address,
        'payment_terms': vendor.payment_terms,
        'notes': vendor.notes,
        'is_active': vendor.is_active,
        'inventory_vendor_id': vendor.inventory_vendor_id,
        'accounting_vendor_id': vendor.accounting_vendor_id,
        'aliases': [{'id': a.id, 'alias_name': a.alias_name, 'source': a.source} for a in aliases]
    }


@router.post("/")
async def create_vendor(vendor: VendorCreate, db: Session = Depends(get_db)):
    """Create a new vendor."""
    # Check for duplicate name
    existing = db.query(Vendor).filter(Vendor.name == vendor.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Vendor '{vendor.name}' already exists")

    new_vendor = Vendor(
        name=vendor.name,
        contact_name=vendor.contact_name,
        email=vendor.email,
        phone=vendor.phone,
        address=vendor.address,
        payment_terms=vendor.payment_terms,
        notes=vendor.notes,
        is_active=True
    )
    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)

    return {
        'id': new_vendor.id,
        'name': new_vendor.name,
        'message': 'Vendor created successfully'
    }


@router.put("/{vendor_id}")
async def update_vendor(
    vendor_id: int,
    updates: VendorUpdate,
    db: Session = Depends(get_db)
):
    """Update a vendor."""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    if updates.name is not None:
        vendor.name = updates.name
    if updates.contact_name is not None:
        vendor.contact_name = updates.contact_name
    if updates.email is not None:
        vendor.email = updates.email
    if updates.phone is not None:
        vendor.phone = updates.phone
    if updates.address is not None:
        vendor.address = updates.address
    if updates.payment_terms is not None:
        vendor.payment_terms = updates.payment_terms
    if updates.notes is not None:
        vendor.notes = updates.notes
    if updates.is_active is not None:
        vendor.is_active = updates.is_active

    db.commit()

    return {'message': 'Vendor updated successfully', 'id': vendor_id}


# ============================================================================
# ALIAS ENDPOINTS
# ============================================================================

@router.get("/aliases/all")
async def list_aliases(db: Session = Depends(get_db)):
    """List all vendor aliases."""
    service = VendorNormalizerService(db)
    return service.get_all_aliases()


@router.post("/aliases")
async def create_alias(alias: AliasCreate, db: Session = Depends(get_db)):
    """Create a vendor alias."""
    service = VendorNormalizerService(db)
    result = service.create_alias(alias.alias_name, alias.vendor_id, source='manual')

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])

    return result


@router.post("/aliases/bulk")
async def create_aliases_bulk(request: BulkAliasCreate, db: Session = Depends(get_db)):
    """Create multiple vendor aliases at once."""
    service = VendorNormalizerService(db)

    results = {'created': [], 'errors': []}
    for alias in request.aliases:
        result = service.create_alias(alias.alias_name, alias.vendor_id, source='manual')
        if 'error' in result:
            results['errors'].append({
                'alias_name': alias.alias_name,
                'error': result['error']
            })
        else:
            results['created'].append(result)

    return results


@router.delete("/aliases/{alias_id}")
async def delete_alias(alias_id: int, db: Session = Depends(get_db)):
    """Deactivate a vendor alias."""
    alias = db.query(VendorAlias).filter(VendorAlias.id == alias_id).first()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")

    alias.is_active = False
    db.commit()

    return {'message': 'Alias deactivated', 'id': alias_id}


# ============================================================================
# NORMALIZATION ENDPOINTS
# ============================================================================

@router.get("/normalization/preview")
async def preview_normalization(db: Session = Depends(get_db)):
    """
    Preview what vendor name normalization would change.
    Shows invoices that would be updated without making changes.
    """
    service = VendorNormalizerService(db)
    return service.normalize_invoice_vendors(dry_run=True)


@router.post("/normalization/apply")
async def apply_normalization(db: Session = Depends(get_db)):
    """
    Apply vendor name normalization to all linked invoices.
    Updates invoice vendor_name to match canonical vendor name.
    """
    service = VendorNormalizerService(db)
    return service.normalize_invoice_vendors(dry_run=False)


@router.get("/normalization/unlinked")
async def get_unlinked_vendors(db: Session = Depends(get_db)):
    """Get vendor names from invoices that are not linked to any Hub vendor."""
    service = VendorNormalizerService(db)
    return service.get_unlinked_vendors()


@router.get("/normalization/suggestions")
async def get_link_suggestions(db: Session = Depends(get_db)):
    """Get suggested vendor links for unlinked invoice vendor names."""
    service = VendorNormalizerService(db)
    return service.suggest_vendor_links()


@router.post("/normalization/auto-create-aliases")
async def auto_create_aliases(db: Session = Depends(get_db)):
    """
    Auto-create aliases from already-linked invoices.
    For invoices where vendor_name differs from canonical name,
    creates an alias so future invoices auto-link.
    """
    service = VendorNormalizerService(db)
    return service.auto_create_aliases_from_linked()


@router.post("/normalization/link-by-alias")
async def link_invoices_by_alias(db: Session = Depends(get_db)):
    """
    Link unlinked invoices using the alias table.
    Checks each unlinked invoice's vendor_name against aliases.
    """
    service = VendorNormalizerService(db)
    return service.link_invoices_by_alias()
