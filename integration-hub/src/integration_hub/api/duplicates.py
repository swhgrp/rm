"""
Duplicate Invoice Detection API Endpoints

Endpoints for finding and managing duplicate invoices.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from integration_hub.db.database import get_db
from integration_hub.services.duplicate_detection import DuplicateDetectionService

router = APIRouter(prefix="/api/v1/duplicates", tags=["duplicates"])


class MarkDuplicateRequest(BaseModel):
    duplicate_id: int
    original_id: int
    action: str = 'flag'  # 'delete' or 'flag'


class BulkMarkRequest(BaseModel):
    duplicates: list[MarkDuplicateRequest]


# ============================================================================
# DUPLICATE DETECTION ENDPOINTS
# ============================================================================

@router.get("/scan")
async def scan_duplicates(
    date_window: int = Query(7, description="Days to look for date-based matches"),
    amount_tolerance: float = Query(0.01, description="Percentage tolerance for amount matching"),
    min_confidence: float = Query(0.7, description="Minimum confidence threshold"),
    db: Session = Depends(get_db)
):
    """
    Scan all invoices for potential duplicates.

    Returns grouped potential duplicates with confidence scores.
    """
    service = DuplicateDetectionService(db)
    return service.scan_all_duplicates(
        date_window_days=date_window,
        amount_tolerance=amount_tolerance,
        min_confidence=min_confidence
    )


@router.get("/stats")
async def get_duplicate_stats(db: Session = Depends(get_db)):
    """Get statistics about potential duplicates in the system."""
    service = DuplicateDetectionService(db)
    return service.get_duplicate_stats()


@router.get("/invoice/{invoice_id}")
async def find_duplicates_for_invoice(
    invoice_id: int,
    date_window: int = Query(7),
    amount_tolerance: float = Query(0.01),
    db: Session = Depends(get_db)
):
    """
    Find potential duplicates for a specific invoice.

    Returns list of potential duplicates with match reasons.
    """
    service = DuplicateDetectionService(db)
    duplicates = service.find_duplicates_for_invoice(
        invoice_id,
        date_window_days=date_window,
        amount_tolerance=amount_tolerance
    )
    return {
        'invoice_id': invoice_id,
        'potential_duplicates': duplicates,
        'count': len(duplicates)
    }


@router.post("/mark")
async def mark_duplicate(
    request: MarkDuplicateRequest,
    db: Session = Depends(get_db)
):
    """
    Mark an invoice as a duplicate of another.

    Actions:
    - 'flag': Set status to 'duplicate'
    - 'delete': Delete the duplicate invoice
    """
    service = DuplicateDetectionService(db)
    result = service.mark_as_duplicate(
        duplicate_id=request.duplicate_id,
        original_id=request.original_id,
        action=request.action
    )

    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])

    return result


@router.post("/mark/bulk")
async def mark_duplicates_bulk(
    request: BulkMarkRequest,
    db: Session = Depends(get_db)
):
    """Mark multiple invoices as duplicates."""
    service = DuplicateDetectionService(db)

    results = {'success': [], 'errors': []}

    for dup in request.duplicates:
        result = service.mark_as_duplicate(
            duplicate_id=dup.duplicate_id,
            original_id=dup.original_id,
            action=dup.action
        )

        if 'error' in result:
            results['errors'].append({
                'duplicate_id': dup.duplicate_id,
                'error': result['error']
            })
        else:
            results['success'].append(result)

    return {
        'processed': len(request.duplicates),
        'success_count': len(results['success']),
        'error_count': len(results['errors']),
        'results': results
    }
