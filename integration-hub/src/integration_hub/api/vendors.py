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
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    tax_id: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    send_to_inventory: Optional[bool] = None
    send_to_accounting: Optional[bool] = None


class VendorMergeRequest(BaseModel):
    """Request to merge multiple vendors into one"""
    primary_vendor_id: int  # The vendor to keep
    merge_vendor_ids: List[int]  # Vendors to merge into primary
    delete_from_systems: bool = True  # Whether to delete duplicates from Inventory/Accounting


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
        'city': vendor.city,
        'state': vendor.state,
        'zip_code': vendor.zip_code,
        'tax_id': vendor.tax_id,
        'payment_terms': vendor.payment_terms,
        'notes': vendor.notes,
        'is_active': vendor.is_active,
        'send_to_inventory': vendor.send_to_inventory,
        'send_to_accounting': vendor.send_to_accounting,
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
    if updates.city is not None:
        vendor.city = updates.city
    if updates.state is not None:
        vendor.state = updates.state
    if updates.zip_code is not None:
        vendor.zip_code = updates.zip_code
    if updates.tax_id is not None:
        vendor.tax_id = updates.tax_id
    if updates.payment_terms is not None:
        vendor.payment_terms = updates.payment_terms
    if updates.notes is not None:
        vendor.notes = updates.notes
    if updates.is_active is not None:
        vendor.is_active = updates.is_active
    if updates.send_to_inventory is not None:
        vendor.send_to_inventory = updates.send_to_inventory
    if updates.send_to_accounting is not None:
        vendor.send_to_accounting = updates.send_to_accounting

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


# ============================================================================
# MERGE ENDPOINTS
# ============================================================================

@router.post("/merge")
async def merge_vendors(request: VendorMergeRequest, db: Session = Depends(get_db)):
    """
    Merge multiple vendors into one primary vendor.

    - The primary vendor keeps its name and becomes the canonical record
    - Merged vendors' names become aliases of the primary vendor
    - Merged vendors' system IDs (inventory/accounting) are collected
    - Optionally deletes the duplicate records from Inventory and Accounting
    - All invoices linked to merged vendors get relinked to primary
    """
    from integration_hub.services.vendor_sync import get_vendor_sync_service
    from integration_hub.models.hub_invoice import HubInvoice
    import asyncio

    # Validate primary vendor exists
    primary_vendor = db.query(Vendor).filter(Vendor.id == request.primary_vendor_id).first()
    if not primary_vendor:
        raise HTTPException(status_code=404, detail="Primary vendor not found")

    # Validate merge vendors exist
    merge_vendors = db.query(Vendor).filter(Vendor.id.in_(request.merge_vendor_ids)).all()
    if len(merge_vendors) != len(request.merge_vendor_ids):
        raise HTTPException(status_code=404, detail="One or more merge vendors not found")

    # Make sure primary is not in merge list
    if request.primary_vendor_id in request.merge_vendor_ids:
        raise HTTPException(status_code=400, detail="Primary vendor cannot be in merge list")

    results = {
        'primary_vendor': primary_vendor.name,
        'merged_vendors': [],
        'aliases_created': [],
        'invoices_relinked': 0,
        'deleted_from_inventory': [],
        'deleted_from_accounting': [],
        'errors': []
    }

    sync_service = get_vendor_sync_service()

    for merge_vendor in merge_vendors:
        try:
            results['merged_vendors'].append(merge_vendor.name)

            # 1. Create alias from merged vendor name (if different from primary)
            if merge_vendor.name.lower() != primary_vendor.name.lower():
                existing_alias = db.query(VendorAlias).filter(
                    VendorAlias.alias_name == merge_vendor.name,
                    VendorAlias.is_active == True
                ).first()

                if not existing_alias:
                    new_alias = VendorAlias(
                        alias_name=merge_vendor.name,
                        alias_name_normalized=merge_vendor.name.lower().strip(),
                        vendor_id=primary_vendor.id,
                        source='merge',
                        is_active=True
                    )
                    db.add(new_alias)
                    results['aliases_created'].append(merge_vendor.name)

            # 2. Transfer any existing aliases from merged vendor to primary
            existing_aliases = db.query(VendorAlias).filter(
                VendorAlias.vendor_id == merge_vendor.id,
                VendorAlias.is_active == True
            ).all()
            for alias in existing_aliases:
                alias.vendor_id = primary_vendor.id

            # 3. Relink invoices from merged vendor to primary
            invoices_updated = db.query(HubInvoice).filter(
                HubInvoice.vendor_id == merge_vendor.id
            ).update({HubInvoice.vendor_id: primary_vendor.id})
            results['invoices_relinked'] += invoices_updated

            # 4. Collect system IDs (if primary doesn't have them)
            if merge_vendor.inventory_vendor_id and not primary_vendor.inventory_vendor_id:
                primary_vendor.inventory_vendor_id = merge_vendor.inventory_vendor_id

            if merge_vendor.accounting_vendor_id and not primary_vendor.accounting_vendor_id:
                primary_vendor.accounting_vendor_id = merge_vendor.accounting_vendor_id

            # 5. Delete from external systems if requested
            if request.delete_from_systems:
                # Delete from Inventory (if different ID than primary)
                if merge_vendor.inventory_vendor_id and merge_vendor.inventory_vendor_id != primary_vendor.inventory_vendor_id:
                    try:
                        delete_result = await sync_service.delete_vendor_from_inventory(merge_vendor.inventory_vendor_id)
                        if delete_result.get('success'):
                            results['deleted_from_inventory'].append({
                                'name': merge_vendor.name,
                                'id': merge_vendor.inventory_vendor_id
                            })
                    except Exception as e:
                        results['errors'].append(f"Failed to delete {merge_vendor.name} from Inventory: {str(e)}")

                # Delete from Accounting (if different ID than primary)
                if merge_vendor.accounting_vendor_id and merge_vendor.accounting_vendor_id != primary_vendor.accounting_vendor_id:
                    try:
                        delete_result = await sync_service.delete_vendor_from_accounting(merge_vendor.accounting_vendor_id)
                        if delete_result.get('success'):
                            results['deleted_from_accounting'].append({
                                'name': merge_vendor.name,
                                'id': merge_vendor.accounting_vendor_id
                            })
                    except Exception as e:
                        results['errors'].append(f"Failed to delete {merge_vendor.name} from Accounting: {str(e)}")

            # 6. Delete the merged vendor from Hub
            db.delete(merge_vendor)

        except Exception as e:
            results['errors'].append(f"Error merging {merge_vendor.name}: {str(e)}")

    db.commit()

    return results


@router.get("/merge/preview")
async def preview_merge(
    primary_id: int,
    merge_ids: str,  # Comma-separated list of IDs
    db: Session = Depends(get_db)
):
    """
    Preview what a merge would do without making changes.
    """
    from integration_hub.models.hub_invoice import HubInvoice

    merge_id_list = [int(x.strip()) for x in merge_ids.split(',') if x.strip()]

    primary_vendor = db.query(Vendor).filter(Vendor.id == primary_id).first()
    if not primary_vendor:
        raise HTTPException(status_code=404, detail="Primary vendor not found")

    merge_vendors = db.query(Vendor).filter(Vendor.id.in_(merge_id_list)).all()

    preview = {
        'primary_vendor': {
            'id': primary_vendor.id,
            'name': primary_vendor.name,
            'inventory_id': primary_vendor.inventory_vendor_id,
            'accounting_id': primary_vendor.accounting_vendor_id
        },
        'vendors_to_merge': [],
        'total_invoices_to_relink': 0,
        'aliases_to_create': []
    }

    for v in merge_vendors:
        invoice_count = db.query(HubInvoice).filter(HubInvoice.vendor_id == v.id).count()
        preview['vendors_to_merge'].append({
            'id': v.id,
            'name': v.name,
            'inventory_id': v.inventory_vendor_id,
            'accounting_id': v.accounting_vendor_id,
            'invoices': invoice_count
        })
        preview['total_invoices_to_relink'] += invoice_count

        if v.name.lower() != primary_vendor.name.lower():
            preview['aliases_to_create'].append(v.name)

    return preview


# ============================================================================
# PUSH TO SYSTEMS ENDPOINTS
# ============================================================================

@router.post("/push-to-systems")
async def push_to_systems(db: Session = Depends(get_db)):
    """
    Push Hub's vendor alias state to Inventory and Accounting systems.

    For each alias in Hub:
    - Find vendors in external systems with matching names
    - Reassign their bills/references to the canonical vendor
    - Deactivate the duplicate vendors

    This ensures external systems reflect Hub's merged vendor state.
    """
    from integration_hub.services.vendor_sync import get_vendor_sync_service

    sync_service = get_vendor_sync_service()
    result = await sync_service.push_aliases_to_systems(db)

    return result


@router.get("/push-to-systems/preview")
async def preview_push_to_systems(db: Session = Depends(get_db)):
    """
    Preview what push-to-systems would do without making changes.
    Shows which vendors in external systems match aliases and would be merged.
    """
    from integration_hub.services.vendor_sync import get_vendor_sync_service
    from integration_hub.models.vendor_alias import VendorAlias

    sync_service = get_vendor_sync_service()

    # Fetch current state from both systems
    inventory_vendors = await sync_service.fetch_inventory_vendors()
    accounting_vendors = await sync_service.fetch_accounting_vendors()

    # Get all active aliases
    aliases = db.query(VendorAlias).filter(VendorAlias.is_active == True).all()

    preview = {
        "aliases_count": len(aliases),
        "inventory_matches": [],
        "accounting_matches": [],
        "no_action_needed": []
    }

    for alias in aliases:
        canonical_vendor = db.query(Vendor).filter(Vendor.id == alias.vendor_id).first()
        if not canonical_vendor:
            continue

        alias_info = {
            "alias_name": alias.alias_name,
            "canonical_vendor": canonical_vendor.name,
            "canonical_vendor_id": canonical_vendor.id
        }

        found_in_inventory = False
        found_in_accounting = False

        # Check Inventory
        for inv_vendor in inventory_vendors:
            if inv_vendor.get("name", "").lower() == alias.alias_name.lower():
                inv_id = inv_vendor.get("id")
                target_id = canonical_vendor.inventory_vendor_id
                if inv_id and target_id and inv_id != target_id and inv_vendor.get("is_active", True):
                    preview["inventory_matches"].append({
                        **alias_info,
                        "source_vendor_id": inv_id,
                        "target_vendor_id": target_id,
                        "source_name": inv_vendor.get("name")
                    })
                    found_in_inventory = True
                break

        # Check Accounting
        for acc_vendor in accounting_vendors:
            if acc_vendor.get("name", "").lower() == alias.alias_name.lower():
                acc_id = acc_vendor.get("id")
                target_id = canonical_vendor.accounting_vendor_id
                if acc_id and target_id and acc_id != target_id and acc_vendor.get("is_active", True):
                    preview["accounting_matches"].append({
                        **alias_info,
                        "source_vendor_id": acc_id,
                        "target_vendor_id": target_id,
                        "source_name": acc_vendor.get("name")
                    })
                    found_in_accounting = True
                break

        if not found_in_inventory and not found_in_accounting:
            preview["no_action_needed"].append(alias.alias_name)

    return preview
