"""
Batch Operations API Endpoints

Provides bulk operation endpoints for invoices.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from integration_hub.db.database import get_db
from integration_hub.services.batch_operations import BatchOperationsService

router = APIRouter(prefix="/api/v1/batch", tags=["batch-operations"])


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class BatchInvoiceIdsRequest(BaseModel):
    """Request with list of invoice IDs"""
    invoice_ids: List[int]


class BatchApproveRequest(BaseModel):
    """Request for batch approval"""
    invoice_ids: List[int]
    approved_by: Optional[int] = None


class BatchStatusRequest(BaseModel):
    """Request for batch status update"""
    invoice_ids: List[int]
    status: str


class BatchSendRequest(BaseModel):
    """Request for batch send/mark sent"""
    invoice_ids: List[int]
    target: str = "both"  # 'inventory', 'accounting', or 'both'


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class BatchResultResponse(BaseModel):
    """Generic batch operation result"""
    success: bool
    total: int
    processed: int
    failed: int
    errors: List[dict] = []
    details: Optional[dict] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/approve", response_model=BatchResultResponse)
async def batch_approve_invoices(
    request: BatchApproveRequest,
    db: Session = Depends(get_db)
):
    """
    Approve multiple invoices at once.

    Marks invoices as approved and updates their status to 'ready' if pending.
    """
    service = BatchOperationsService(db)
    result = service.batch_approve(request.invoice_ids, request.approved_by)

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['approved'] + result['already_approved'],
        failed=result['failed'],
        errors=result.get('errors', []),
        details={
            'newly_approved': result['approved'],
            'already_approved': result['already_approved']
        }
    )


@router.post("/auto-map", response_model=BatchResultResponse)
async def batch_auto_map_invoices(
    request: BatchInvoiceIdsRequest,
    db: Session = Depends(get_db)
):
    """
    Run auto-mapping on multiple invoices.

    Attempts to automatically map invoice items to vendor items using
    SKU matching, fuzzy name matching, and expense mapping.
    """
    service = BatchOperationsService(db)
    result = service.batch_auto_map(request.invoice_ids)

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['processed'],
        failed=result['failed'],
        errors=result.get('errors', []),
        details={
            'total_items': result.get('total_items', 0),
            'total_mapped': result.get('total_mapped', 0),
            'per_invoice': result.get('per_invoice', [])
        }
    )


@router.post("/status", response_model=BatchResultResponse)
async def batch_update_status(
    request: BatchStatusRequest,
    db: Session = Depends(get_db)
):
    """
    Update status for multiple invoices.

    Valid statuses: pending, mapping, ready, sent, error, partial
    """
    service = BatchOperationsService(db)
    result = service.batch_update_status(request.invoice_ids, request.status)

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['updated'],
        failed=result['failed'],
        errors=result.get('errors', [])
    )


@router.post("/mark-sent", response_model=BatchResultResponse)
async def batch_mark_sent(
    request: BatchSendRequest,
    db: Session = Depends(get_db)
):
    """
    Mark invoices as sent to inventory and/or accounting.

    Target can be 'inventory', 'accounting', or 'both'.
    This is for manually marking invoices as sent when the actual
    sending happens outside of Hub.
    """
    service = BatchOperationsService(db)
    result = service.batch_mark_sent(request.invoice_ids, request.target)

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['updated'],
        failed=result['failed'],
        errors=result.get('errors', [])
    )


@router.post("/reset-sync", response_model=BatchResultResponse)
async def batch_reset_sync(
    request: BatchSendRequest,
    db: Session = Depends(get_db)
):
    """
    Reset sync status for invoices (allows re-sending).

    Clears the sent flags and sync timestamps so invoices can be
    sent again. Target can be 'inventory', 'accounting', or 'both'.
    """
    service = BatchOperationsService(db)
    result = service.batch_reset_sync(request.invoice_ids, request.target)

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['reset'],
        failed=result['failed'],
        errors=result.get('errors', [])
    )


@router.post("/delete", response_model=BatchResultResponse)
async def batch_delete_invoices(
    request: BatchInvoiceIdsRequest,
    db: Session = Depends(get_db)
):
    """
    Delete multiple invoices.

    Only invoices that have NOT been sent to inventory or accounting
    can be deleted. Sent invoices must be reset first.
    """
    service = BatchOperationsService(db)
    result = service.batch_delete(request.invoice_ids)

    return BatchResultResponse(
        success=result['failed'] == 0,
        total=result['total'],
        processed=result['deleted'],
        failed=result['failed'],
        errors=result.get('errors', [])
    )


@router.post("/summary")
async def get_batch_summary(
    request: BatchInvoiceIdsRequest,
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for a set of invoices.

    Useful for previewing a batch before performing operations.
    """
    service = BatchOperationsService(db)
    return service.get_batch_summary(request.invoice_ids)


@router.get("/pending")
async def get_pending_invoices(
    limit: int = Query(100, le=500),
    vendor_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get list of pending invoice IDs ready for batch operations.

    Returns invoices that are not yet sent to inventory.
    """
    from integration_hub.models.hub_invoice import HubInvoice
    from sqlalchemy import or_

    query = db.query(HubInvoice.id, HubInvoice.invoice_number, HubInvoice.vendor_name).filter(
        or_(HubInvoice.sent_to_inventory == False, HubInvoice.sent_to_inventory == None)
    )

    if vendor_name:
        query = query.filter(HubInvoice.vendor_name.ilike(f"%{vendor_name}%"))

    invoices = query.order_by(HubInvoice.created_at.desc()).limit(limit).all()

    return {
        'count': len(invoices),
        'invoices': [
            {
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'vendor_name': inv.vendor_name
            }
            for inv in invoices
        ]
    }


@router.get("/unmapped")
async def get_unmapped_invoices(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    """
    Get list of invoices with unmapped items.

    Returns invoices that have at least one unmapped item.
    """
    from integration_hub.models.hub_invoice import HubInvoice
    from integration_hub.models.hub_invoice_item import HubInvoiceItem
    from sqlalchemy import func, or_

    # Subquery to find invoices with unmapped items
    subquery = db.query(HubInvoiceItem.invoice_id).filter(
        or_(HubInvoiceItem.is_mapped == False, HubInvoiceItem.is_mapped == None)
    ).distinct().subquery()

    query = db.query(
        HubInvoice.id,
        HubInvoice.invoice_number,
        HubInvoice.vendor_name,
        func.count(HubInvoiceItem.id).label('unmapped_count')
    ).join(
        HubInvoiceItem
    ).filter(
        HubInvoice.id.in_(subquery),
        or_(HubInvoiceItem.is_mapped == False, HubInvoiceItem.is_mapped == None)
    ).group_by(
        HubInvoice.id, HubInvoice.invoice_number, HubInvoice.vendor_name
    ).order_by(
        func.count(HubInvoiceItem.id).desc()
    ).limit(limit)

    results = query.all()

    return {
        'count': len(results),
        'invoices': [
            {
                'id': r.id,
                'invoice_number': r.invoice_number,
                'vendor_name': r.vendor_name,
                'unmapped_items': r.unmapped_count
            }
            for r in results
        ]
    }
