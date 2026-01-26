"""
Invoice API endpoints for external systems (Inventory, Accounting)

These endpoints expose Hub invoice data for consumption by other systems,
making Hub the source of truth for invoices.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel

from integration_hub.db.database import get_db
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices-api"])


# ============================================================================
# PYDANTIC SCHEMAS FOR API RESPONSES
# ============================================================================

class InvoiceItemResponse(BaseModel):
    """Invoice line item response schema"""
    id: int
    line_number: Optional[int] = None
    item_description: str
    item_code: Optional[str] = None
    quantity: float
    unit_of_measure: Optional[str] = None
    pack_size: Optional[int] = None
    unit_price: float
    line_total: float

    # Mapping info
    inventory_item_id: Optional[int] = None
    inventory_item_name: Optional[str] = None
    inventory_category: Optional[str] = None
    is_mapped: bool = False
    mapping_method: Optional[str] = None
    mapping_confidence: Optional[float] = None

    # GL accounts
    gl_asset_account: Optional[int] = None
    gl_cogs_account: Optional[int] = None
    gl_waste_account: Optional[int] = None

    class Config:
        from_attributes = True


class InvoiceSummaryResponse(BaseModel):
    """Invoice summary for list views"""
    id: int
    vendor_id: Optional[int] = None
    vendor_name: str
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    total_amount: float
    tax_amount: Optional[float] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    status: str
    is_statement: bool = False
    sent_to_inventory: bool = False
    sent_to_accounting: bool = False
    item_count: int = 0
    mapped_item_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailResponse(BaseModel):
    """Full invoice detail with items"""
    id: int
    vendor_id: Optional[int] = None
    vendor_name: str
    vendor_account_number: Optional[str] = None
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    total_amount: float
    tax_amount: Optional[float] = None
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    status: str
    is_statement: bool = False

    # Source info
    source: str
    source_email: Optional[str] = None
    pdf_path: Optional[str] = None

    # Sync status
    sent_to_inventory: bool = False
    sent_to_accounting: bool = False
    inventory_invoice_id: Optional[int] = None
    accounting_je_id: Optional[int] = None
    inventory_sync_at: Optional[datetime] = None
    accounting_sync_at: Optional[datetime] = None
    inventory_error: Optional[str] = None
    accounting_error: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Line items
    items: List[InvoiceItemResponse] = []

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response"""
    invoices: List[InvoiceSummaryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    vendor_name: Optional[str] = Query(None, description="Filter by vendor name"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    start_date: Optional[date] = Query(None, description="Filter by invoice date start"),
    end_date: Optional[date] = Query(None, description="Filter by invoice date end"),
    sent_to_inventory: Optional[bool] = Query(None, description="Filter by inventory sync status"),
    include_statements: bool = Query(False, description="Include statement invoices"),
    has_inventory_items: Optional[bool] = Query(None, description="Filter to invoices with inventory items only (excludes expense-only)"),
    db: Session = Depends(get_db)
):
    """
    Get paginated list of invoices with summary info.

    This endpoint is used by Inventory to fetch invoices for display.
    Returns invoice headers with item counts, not full line items.

    Use has_inventory_items=true to exclude expense-only invoices (Cozzini, utilities, etc.)
    """
    # Base query with item counts
    query = db.query(
        HubInvoice,
        func.count(HubInvoiceItem.id).label('item_count'),
        func.sum(func.cast(HubInvoiceItem.is_mapped, Integer)).label('mapped_count')
    ).outerjoin(HubInvoiceItem).group_by(HubInvoice.id)

    # Apply filters
    if not include_statements:
        query = query.filter(or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None))

    if status:
        query = query.filter(HubInvoice.status == status)

    if vendor_name:
        query = query.filter(HubInvoice.vendor_name.ilike(f"%{vendor_name}%"))

    if location_id:
        query = query.filter(HubInvoice.location_id == location_id)

    if start_date:
        query = query.filter(HubInvoice.invoice_date >= start_date)

    if end_date:
        query = query.filter(HubInvoice.invoice_date <= end_date)

    if sent_to_inventory is not None:
        query = query.filter(HubInvoice.sent_to_inventory == sent_to_inventory)

    # Filter to only invoices with inventory items (not expense-only)
    # An invoice has inventory items if at least one item has inventory_category set
    # and it's not 'Uncategorized' (which means expense-only mapping)
    if has_inventory_items is True:
        # Subquery to find invoices that have at least one inventory item
        from sqlalchemy import exists, and_
        has_inv_items_subquery = db.query(HubInvoiceItem.invoice_id).filter(
            HubInvoiceItem.inventory_category.isnot(None),
            HubInvoiceItem.inventory_category != 'Uncategorized',
            HubInvoiceItem.inventory_category != ''
        ).distinct().subquery()
        query = query.filter(HubInvoice.id.in_(db.query(has_inv_items_subquery)))
    elif has_inventory_items is False:
        # Show only expense-only invoices (no inventory items)
        from sqlalchemy import exists, and_
        has_inv_items_subquery = db.query(HubInvoiceItem.invoice_id).filter(
            HubInvoiceItem.inventory_category.isnot(None),
            HubInvoiceItem.inventory_category != 'Uncategorized',
            HubInvoiceItem.inventory_category != ''
        ).distinct().subquery()
        query = query.filter(~HubInvoice.id.in_(db.query(has_inv_items_subquery)))

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    results = query.order_by(desc(HubInvoice.invoice_date), desc(HubInvoice.id))\
        .offset(offset).limit(page_size).all()

    # Build response
    invoices = []
    for invoice, item_count, mapped_count in results:
        invoices.append(InvoiceSummaryResponse(
            id=invoice.id,
            vendor_id=invoice.vendor_id,
            vendor_name=invoice.vendor_name,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            total_amount=float(invoice.total_amount) if invoice.total_amount else 0,
            tax_amount=float(invoice.tax_amount) if invoice.tax_amount else None,
            location_id=invoice.location_id,
            location_name=invoice.location_name,
            status=invoice.status,
            is_statement=invoice.is_statement or False,
            sent_to_inventory=invoice.sent_to_inventory or False,
            sent_to_accounting=invoice.sent_to_accounting or False,
            item_count=item_count or 0,
            mapped_item_count=mapped_count or 0,
            created_at=invoice.created_at
        ))

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return InvoiceListResponse(
        invoices=invoices,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages
    )


class COGSSummaryResponse(BaseModel):
    """COGS summary response for dashboard"""
    total_cogs: float
    invoice_count: int
    daily_cogs: dict  # date string -> amount
    recent_invoices: List[InvoiceSummaryResponse]


@router.get("/cogs-summary", response_model=COGSSummaryResponse)
async def get_cogs_summary(
    start_date: Optional[date] = Query(None, description="Start date for COGS calculation"),
    end_date: Optional[date] = Query(None, description="End date for COGS calculation"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    db: Session = Depends(get_db)
):
    """
    Get COGS summary from approved invoices for dashboard display.

    Returns total COGS, daily breakdown, and recent invoices for the date range.
    Used by Inventory dashboard to display COGS data without requiring Hub access.
    """
    from datetime import timedelta
    from sqlalchemy import Integer

    # Default to last 7 days if no dates provided
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=7)

    # Base query for approved/sent invoices (not statements)
    query = db.query(HubInvoice).filter(
        HubInvoice.invoice_date >= start_date,
        HubInvoice.invoice_date <= end_date,
        or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
    )

    if location_id:
        query = query.filter(HubInvoice.location_id == location_id)

    invoices = query.order_by(desc(HubInvoice.invoice_date), desc(HubInvoice.id)).all()

    # Calculate total COGS and daily breakdown
    total_cogs = 0.0
    daily_cogs = {}

    for invoice in invoices:
        amount = float(invoice.total_amount) if invoice.total_amount else 0.0
        total_cogs += amount

        # Add to daily breakdown
        date_str = invoice.invoice_date.isoformat() if invoice.invoice_date else None
        if date_str:
            daily_cogs[date_str] = daily_cogs.get(date_str, 0.0) + amount

    # Get recent invoices (last 5) with item counts
    # Only include invoices with inventory items (not expense-only like Cozzini, utilities)
    recent_query = db.query(
        HubInvoice,
        func.count(HubInvoiceItem.id).label('item_count'),
        func.sum(func.cast(HubInvoiceItem.is_mapped, Integer)).label('mapped_count')
    ).outerjoin(HubInvoiceItem).group_by(HubInvoice.id).filter(
        or_(HubInvoice.is_statement == False, HubInvoice.is_statement == None)
    )

    if location_id:
        recent_query = recent_query.filter(HubInvoice.location_id == location_id)

    # Filter to only invoices with inventory items (exclude expense-only)
    has_inv_items_subquery = db.query(HubInvoiceItem.invoice_id).filter(
        HubInvoiceItem.inventory_category.isnot(None),
        HubInvoiceItem.inventory_category != 'Uncategorized',
        HubInvoiceItem.inventory_category != ''
    ).distinct().subquery()
    recent_query = recent_query.filter(HubInvoice.id.in_(db.query(has_inv_items_subquery)))

    recent_results = recent_query.order_by(
        desc(HubInvoice.invoice_date), desc(HubInvoice.id)
    ).limit(5).all()

    recent_invoices = []
    for invoice, item_count, mapped_count in recent_results:
        recent_invoices.append(InvoiceSummaryResponse(
            id=invoice.id,
            vendor_id=invoice.vendor_id,
            vendor_name=invoice.vendor_name,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            total_amount=float(invoice.total_amount) if invoice.total_amount else 0,
            tax_amount=float(invoice.tax_amount) if invoice.tax_amount else None,
            location_id=invoice.location_id,
            location_name=invoice.location_name,
            status=invoice.status,
            is_statement=invoice.is_statement or False,
            sent_to_inventory=invoice.sent_to_inventory or False,
            sent_to_accounting=invoice.sent_to_accounting or False,
            item_count=item_count or 0,
            mapped_item_count=mapped_count or 0,
            created_at=invoice.created_at
        ))

    return COGSSummaryResponse(
        total_cogs=total_cogs,
        invoice_count=len(invoices),
        daily_cogs=daily_cogs,
        recent_invoices=recent_invoices
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """
    Get full invoice details including all line items.

    This endpoint is used by Inventory to display invoice detail view.
    Includes all mapping information for each line item.
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get items
    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice_id
    ).order_by(HubInvoiceItem.line_number, HubInvoiceItem.id).all()

    # Build item responses
    item_responses = []
    for item in items:
        item_responses.append(InvoiceItemResponse(
            id=item.id,
            line_number=item.line_number,
            item_description=item.item_description,
            item_code=item.item_code,
            quantity=float(item.quantity),
            unit_of_measure=item.unit_of_measure,
            pack_size=item.pack_size,
            unit_price=float(item.unit_price),
            line_total=float(item.total_amount),
            inventory_item_id=item.inventory_item_id,
            inventory_item_name=item.inventory_item_name,
            inventory_category=item.inventory_category,
            is_mapped=item.is_mapped or False,
            mapping_method=item.mapping_method,
            mapping_confidence=float(item.mapping_confidence) if item.mapping_confidence else None,
            gl_asset_account=item.gl_asset_account,
            gl_cogs_account=item.gl_cogs_account,
            gl_waste_account=item.gl_waste_account
        ))

    return InvoiceDetailResponse(
        id=invoice.id,
        vendor_id=invoice.vendor_id,
        vendor_name=invoice.vendor_name,
        vendor_account_number=invoice.vendor_account_number,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        total_amount=float(invoice.total_amount) if invoice.total_amount else 0,
        tax_amount=float(invoice.tax_amount) if invoice.tax_amount else None,
        location_id=invoice.location_id,
        location_name=invoice.location_name,
        status=invoice.status,
        is_statement=invoice.is_statement or False,
        source=invoice.source,
        source_email=invoice.source_email,
        pdf_path=invoice.pdf_path,
        sent_to_inventory=invoice.sent_to_inventory or False,
        sent_to_accounting=invoice.sent_to_accounting or False,
        inventory_invoice_id=invoice.inventory_invoice_id,
        accounting_je_id=invoice.accounting_je_id,
        inventory_sync_at=invoice.inventory_sync_at,
        accounting_sync_at=invoice.accounting_sync_at,
        inventory_error=invoice.inventory_error,
        accounting_error=invoice.accounting_error,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        items=item_responses
    )


@router.get("/by-number/{invoice_number}")
async def get_invoice_by_number(
    invoice_number: str,
    vendor_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Look up invoice by invoice number (optionally filtered by vendor).

    Used for duplicate detection and cross-referencing.
    """
    query = db.query(HubInvoice).filter(HubInvoice.invoice_number == invoice_number)

    if vendor_name:
        query = query.filter(HubInvoice.vendor_name.ilike(f"%{vendor_name}%"))

    invoice = query.order_by(desc(HubInvoice.id)).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "vendor_name": invoice.vendor_name,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "total_amount": float(invoice.total_amount) if invoice.total_amount else 0,
        "status": invoice.status,
        "sent_to_inventory": invoice.sent_to_inventory or False,
        "inventory_invoice_id": invoice.inventory_invoice_id
    }


@router.get("/{invoice_id}/items", response_model=List[InvoiceItemResponse])
async def get_invoice_items(
    invoice_id: int,
    mapped_only: bool = Query(False, description="Return only mapped items"),
    db: Session = Depends(get_db)
):
    """
    Get line items for a specific invoice.

    Used when Inventory needs just the items without full invoice details.
    """
    # Verify invoice exists
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    query = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id)

    if mapped_only:
        query = query.filter(HubInvoiceItem.is_mapped == True)

    items = query.order_by(HubInvoiceItem.line_number, HubInvoiceItem.id).all()

    return [
        InvoiceItemResponse(
            id=item.id,
            line_number=item.line_number,
            item_description=item.item_description,
            item_code=item.item_code,
            quantity=float(item.quantity),
            unit_of_measure=item.unit_of_measure,
            pack_size=item.pack_size,
            unit_price=float(item.unit_price),
            line_total=float(item.total_amount),
            inventory_item_id=item.inventory_item_id,
            inventory_item_name=item.inventory_item_name,
            inventory_category=item.inventory_category,
            is_mapped=item.is_mapped or False,
            mapping_method=item.mapping_method,
            mapping_confidence=float(item.mapping_confidence) if item.mapping_confidence else None,
            gl_asset_account=item.gl_asset_account,
            gl_cogs_account=item.gl_cogs_account,
            gl_waste_account=item.gl_waste_account
        )
        for item in items
    ]


# Need Integer for the SQL cast
from sqlalchemy import Integer


# ============================================================================
# RE-PARSE WITH VENDOR RULES
# ============================================================================

@router.post("/{invoice_id}/reparse-with-vendor-rules")
async def reparse_invoice_with_vendor_rules(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """
    Re-parse an invoice using vendor-specific parsing rules.

    This endpoint:
    1. Looks up the vendor-specific parsing rules for the invoice's vendor
    2. Re-parses the invoice PDF with vendor-specific AI instructions
    3. Updates the invoice items with the newly parsed data

    The invoice must already have a matched vendor with parsing rules configured.

    Returns the result of the re-parse operation.
    """
    from integration_hub.services.invoice_parser import get_invoice_parser

    parser = get_invoice_parser()
    result = parser.reparse_with_vendor_rules(invoice_id, db)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/{invoice_id}/vendor-rules-status")
async def get_invoice_vendor_rules_status(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """
    Check if an invoice's vendor has parsing rules available.

    Returns:
        - has_rules: Whether the vendor has parsing rules
        - vendor_id: The vendor ID (if matched)
        - vendor_name: The vendor name
        - rule_summary: Brief summary of the rules if available
    """
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule

    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    result = {
        "invoice_id": invoice_id,
        "vendor_id": invoice.vendor_id,
        "vendor_name": invoice.vendor_name,
        "has_rules": False,
        "rule_summary": None
    }

    if invoice.vendor_id:
        rule = db.query(VendorParsingRule).filter(
            VendorParsingRule.vendor_id == invoice.vendor_id,
            VendorParsingRule.is_active == True
        ).first()

        if rule:
            result["has_rules"] = True
            summary_parts = []
            if rule.quantity_column:
                summary_parts.append(f"Qty: {rule.quantity_column}")
            if rule.item_code_column:
                summary_parts.append(f"SKU: {rule.item_code_column}")
            if rule.ai_instructions:
                summary_parts.append("Custom AI instructions")
            result["rule_summary"] = ", ".join(summary_parts) if summary_parts else "Rules configured"

    return result
