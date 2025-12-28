"""
Integration Hub - FastAPI Application

Central hub for receiving invoices and routing to Inventory and Accounting systems.
Provides mapping UI and auto-send functionality while keeping systems independent.
"""

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from integration_hub.db.database import get_db, engine, Base
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.item_gl_mapping import ItemGLMapping, CategoryGLMapping
from integration_hub.models.vendor import Vendor
from integration_hub.models.hub_vendor_item import HubVendorItem
from integration_hub.models.price_history import PriceHistory
from integration_hub.models.vendor_alias import VendorAlias
from integration_hub.schemas.vendor import VendorCreate, VendorResponse, VendorSyncStatus
from integration_hub.services.inventory_sender import get_inventory_sender
from integration_hub.services.accounting_sender import get_accounting_sender
from integration_hub.services.auto_send import get_auto_send_service
from integration_hub.services.vendor_sync import get_vendor_sync_service
from integration_hub.services.email_scheduler import get_email_scheduler
from integration_hub.api import auth as auth_router
from integration_hub.api import settings as settings_router
from integration_hub.api import invoices as invoices_router
from integration_hub.api import vendor_items as vendor_items_router
from integration_hub.api import batch_operations as batch_operations_router
from integration_hub.api import reporting as reporting_router
from integration_hub.api import vendors as vendors_router
from integration_hub.api import duplicates as duplicates_router
from integration_hub.api import similarity as similarity_router
from integration_hub.api import size_settings as size_settings_router

# Create database tables
Base.metadata.create_all(bind=engine)

# Get environment variables for API URLs
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000/api")
ACCOUNTING_API_URL = os.getenv("ACCOUNTING_API_URL", "http://accounting-app:8000/api")

# Initialize FastAPI app
app = FastAPI(
    title="Integration Hub",
    description="Central hub for invoice processing and system integration",
    version="1.0.0",
    root_path="/hub"
)

# Setup templates and static files
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# Configure Jinja2 environment for template caching control
templates.env.auto_reload = True
templates.env.cache_size = 0  # Disable template caching

# Create static directory if it doesn't exist
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(auth_router.router)
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(invoices_router.router)  # External API for Inventory/Accounting systems
app.include_router(vendor_items_router.router)  # Vendor items API (proxies to Inventory for now)
app.include_router(batch_operations_router.router)  # Batch operations for invoices
app.include_router(reporting_router.router)  # Reporting and analytics
app.include_router(vendors_router.router)  # Vendor management and aliases
app.include_router(duplicates_router.router)  # Duplicate invoice detection
app.include_router(similarity_router.router)  # AI-powered similarity search
app.include_router(size_settings_router.router)  # Size units and containers management


# ============================================================================
# STARTUP AND SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup"""
    import logging
    logger = logging.getLogger(__name__)

    # Start email scheduler (checks every 15 minutes by default)
    try:
        check_interval = int(os.getenv("EMAIL_CHECK_INTERVAL_MINUTES", "15"))
        scheduler = get_email_scheduler(check_interval_minutes=check_interval)
        scheduler.start()
        logger.info(f"Email scheduler started - checking every {check_interval} minutes")
    except Exception as e:
        logger.error(f"Failed to start email scheduler: {str(e)}", exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up services on application shutdown"""
    import logging
    logger = logging.getLogger(__name__)

    # Stop email scheduler
    try:
        scheduler = get_email_scheduler()
        if scheduler.is_running:
            scheduler.stop()
            logger.info("Email scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping email scheduler: {str(e)}", exc_info=True)

# Custom exception handler for authentication redirects
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 401 to Portal login for HTML requests"""
    if exc.status_code == 401:  # HTTP_401_UNAUTHORIZED
        # Check if this is an HTML request (not API)
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "/hub/" in request.url.path:
            # Redirect to Portal login instead of local login
            return RedirectResponse(url="/portal/login?redirect=/hub/", status_code=302)
    # For API requests or other errors, return JSON response
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "integration-hub",
        "version": "1.0.0"
    }


# ============================================================================
# HOME / DASHBOARD
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard showing invoice status and unmapped items"""

    # Get invoice statistics
    total_invoices = db.query(HubInvoice).count()
    pending_mapping = db.query(HubInvoice).filter(HubInvoice.status == 'mapping').count()
    ready_to_send = db.query(HubInvoice).filter(HubInvoice.status == 'ready').count()
    sent_invoices = db.query(HubInvoice).filter(HubInvoice.status == 'sent').count()
    error_invoices = db.query(HubInvoice).filter(HubInvoice.status == 'error').count()
    parse_failed = db.query(HubInvoice).filter(HubInvoice.status == 'parse_failed').count()
    pending_parse = db.query(HubInvoice).filter(HubInvoice.status == 'pending').count()
    # Awaiting retry = pending invoices that have been attempted at least once
    awaiting_retry = db.query(HubInvoice).filter(
        HubInvoice.status == 'pending',
        HubInvoice.parse_attempts > 0
    ).count()

    # Get unmapped items count (unique item descriptions, not total line items)
    from sqlalchemy import func
    unmapped_items = db.query(
        func.count(func.distinct(
            func.concat(HubInvoiceItem.item_description, '|', HubInvoiceItem.item_code)
        ))
    ).filter(HubInvoiceItem.is_mapped == False).scalar() or 0

    # Get recent invoices
    recent_invoices = db.query(HubInvoice).order_by(HubInvoice.created_at.desc()).limit(10).all()

    # Get vendors for dropdown
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_invoices": total_invoices,
        "pending_mapping": pending_mapping,
        "ready_to_send": ready_to_send,
        "sent_invoices": sent_invoices,
        "error_invoices": error_invoices,
        "parse_failed": parse_failed,
        "pending_parse": pending_parse,
        "awaiting_retry": awaiting_retry,
        "unmapped_items": unmapped_items,
        "recent_invoices": recent_invoices,
        "vendors": vendors
    })


# ============================================================================
# INVOICE MANAGEMENT
# ============================================================================

@app.get("/invoices", response_class=HTMLResponse)
async def list_invoices(
    request: Request,
    limit: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List all invoices with optional pagination"""
    query = db.query(HubInvoice).order_by(HubInvoice.invoice_date.desc())

    # Get total count
    total_count = query.count()

    # Apply limit if provided (for pagination)
    if limit:
        invoices = query.limit(limit).all()
    else:
        # Default: load all for client-side filtering, but show only 50 in "All" tab
        invoices = query.all()

    # Get vendors for dropdown
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    return templates.TemplateResponse("invoices.html", {
        "request": request,
        "invoices": invoices,
        "vendors": vendors,
        "total_count": total_count,
        "loaded_count": len(invoices)
    })


@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
async def view_invoice(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    """View invoice details and map items"""
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get invoice items
    items = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).all()

    # Get locations from inventory database for location dropdown
    from sqlalchemy import create_engine, text
    inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')
    locations = []
    try:
        engine = create_engine(inventory_db_url)
        with engine.connect() as conn:
            results = conn.execute(
                text("SELECT id, name FROM locations WHERE is_active = true ORDER BY name")
            ).fetchall()
            locations = [{"id": row[0], "name": row[1]} for row in results]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching locations: {str(e)}")

    # Get vendors from hub database for vendor dropdown
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    # Build GL account name lookup from category_gl_mapping
    gl_names = {}
    try:
        from sqlalchemy import text as sql_text
        gl_mappings = db.execute(sql_text("""
            SELECT DISTINCT gl_asset_account, asset_account_name, gl_cogs_account, cogs_account_name
            FROM category_gl_mapping
            WHERE gl_asset_account IS NOT NULL OR gl_cogs_account IS NOT NULL
        """)).fetchall()
        for row in gl_mappings:
            if row[0] and row[1]:  # asset account
                gl_names[str(row[0])] = row[1]
            if row[2] and row[3]:  # cogs account
                gl_names[str(row[2])] = row[3]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching GL names: {str(e)}")

    # Fetch vendor item pack_size and purchase_unit from Inventory for mapped items
    vendor_item_info = {}
    try:
        # Get all inventory_item_ids (which are vendor_item_ids) for mapped items
        vendor_item_ids = [item.inventory_item_id for item in items if item.inventory_item_id]
        if vendor_item_ids:
            engine = create_engine(inventory_db_url)
            with engine.connect() as conn:
                # Query vendor_items with units_of_measure join
                results = conn.execute(
                    text("""
                        SELECT vi.id, vi.pack_size, vi.conversion_factor, uom.name as purchase_unit, uom.abbreviation as purchase_unit_abbr
                        FROM vendor_items vi
                        LEFT JOIN units_of_measure uom ON vi.purchase_unit_id = uom.id
                        WHERE vi.id = ANY(:ids)
                    """),
                    {"ids": vendor_item_ids}
                ).fetchall()
                for row in results:
                    vendor_item_info[row[0]] = {
                        "pack_size": row[1],  # This is the pack_size string like "6x750ml"
                        "conversion_factor": float(row[2]) if row[2] else None,  # Quantity per case
                        "purchase_unit": row[3],  # Unit name like "Bottle 750ml"
                        "purchase_unit_abbr": row[4]  # Abbreviation like "btl750ml"
                    }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching vendor item info: {str(e)}")

    return templates.TemplateResponse("invoice_detail.html", {
        "request": request,
        "invoice": invoice,
        "items": items,
        "locations": locations,
        "vendors": vendors,
        "gl_names": gl_names,
        "vendor_item_info": vendor_item_info
    })


@app.post("/invoices/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    vendor_name: str = Form(...),
    invoice_number: str = Form(...),
    invoice_date: str = Form(...),
    total_amount: float = Form(...),
    db: Session = Depends(get_db)
):
    """Upload an invoice PDF and create hub invoice record"""

    # Save PDF file
    pdf_dir = Path("/opt/restaurant-system/integration-hub/uploads")
    pdf_dir.mkdir(exist_ok=True)

    file_path = pdf_dir / f"{invoice_number}_{file.filename}"
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    # Create invoice record
    invoice = HubInvoice(
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        total_amount=total_amount,
        source='upload',
        pdf_path=str(file_path),
        status='pending'
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return RedirectResponse(url=f"/invoices/{invoice.id}", status_code=303)


def _parse_invoice_background(invoice_id: int):
    """
    Background task to parse invoice without blocking the API response
    """
    from integration_hub.services.invoice_parser import get_invoice_parser
    from integration_hub.db.database import SessionLocal
    import logging

    logger = logging.getLogger(__name__)
    db = SessionLocal()

    try:
        parser = get_invoice_parser()
        result = parser.parse_and_save(invoice_id, db)
        logger.info(f"Invoice {invoice_id} parsed successfully in background: {result.get('message', 'No message')}")
    except ValueError as e:
        logger.error(f"Configuration error parsing invoice {invoice_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error parsing invoice {invoice_id}: {str(e)}", exc_info=True)
    finally:
        db.close()


@app.post("/api/invoices/{invoice_id}/parse")
async def parse_invoice(invoice_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Parse an invoice PDF using OpenAI to extract invoice data and line items.
    Returns immediately and processes in background to avoid blocking the UI.
    """
    # Verify invoice exists
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        return {
            "success": False,
            "message": "Invoice not found"
        }

    # Add parsing task to background
    background_tasks.add_task(_parse_invoice_background, invoice_id)

    return {
        "success": True,
        "message": "Invoice parsing started in background. This may take 30-60 seconds. Refresh the page to see results.",
        "invoice_id": invoice_id,
        "processing": True
    }


@app.get("/api/invoice-lookup")
async def lookup_invoice_by_number(
    invoice_number: str = Query(..., description="Invoice number to look up"),
    db: Session = Depends(get_db)
):
    """
    Look up an invoice by invoice number. Returns PDF info if available.
    Used by accounting system to link journal entries back to source PDFs.
    """
    invoice = db.query(HubInvoice).filter(
        HubInvoice.invoice_number == invoice_number
    ).order_by(HubInvoice.id.desc()).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "vendor_name": invoice.vendor_name,
        "has_pdf": bool(invoice.pdf_path),
        "pdf_url": f"/hub/api/invoices/{invoice.id}/pdf" if invoice.pdf_path else None,
        "invoice_url": f"/hub/invoices/{invoice.id}"
    }


@app.get("/api/invoices/{invoice_id}")
async def get_invoice_status(invoice_id: int, db: Session = Depends(get_db)):
    """
    Get invoice status and item count (for polling during background parsing)
    """
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get item count
    items = db.query(HubInvoiceItem).filter(HubInvoiceItem.invoice_id == invoice_id).all()

    return {
        "id": invoice.id,
        "status": invoice.status,
        "is_statement": invoice.is_statement,
        "items": [{"id": item.id} for item in items]  # Just IDs for lightweight response
    }


@app.patch("/api/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update invoice header information (vendor, invoice number, dates, amounts, location)
    """
    import logging
    from datetime import datetime
    logger = logging.getLogger(__name__)

    # Get invoice
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Parse request body
    data = await request.json()

    try:
        # Handle vendor update - either select existing or create new
        if "vendor_id" in data and data["vendor_id"]:
            # Selected existing vendor
            vendor = db.query(Vendor).filter(Vendor.id == int(data["vendor_id"])).first()
            if vendor:
                invoice.vendor_id = vendor.id
                invoice.vendor_name = vendor.name
            else:
                raise HTTPException(status_code=404, detail="Vendor not found")
        elif "new_vendor_name" in data and data["new_vendor_name"]:
            # Create new vendor
            new_vendor = Vendor(
                name=data["new_vendor_name"].strip(),
                is_active=True
            )
            db.add(new_vendor)
            db.flush()  # Get the new vendor ID
            invoice.vendor_id = new_vendor.id
            invoice.vendor_name = new_vendor.name
            logger.info(f"Created new vendor: {new_vendor.name} (ID: {new_vendor.id})")

        # Update fields if provided
        if "vendor_name" in data:
            invoice.vendor_name = data["vendor_name"]

        if "invoice_number" in data:
            invoice.invoice_number = data["invoice_number"]

        if "invoice_date" in data and data["invoice_date"]:
            invoice.invoice_date = datetime.strptime(data["invoice_date"], '%Y-%m-%d').date()

        if "due_date" in data:
            if data["due_date"]:
                invoice.due_date = datetime.strptime(data["due_date"], '%Y-%m-%d').date()
            else:
                invoice.due_date = None

        if "total_amount" in data and data["total_amount"] is not None:
            invoice.total_amount = float(data["total_amount"])

        if "tax_amount" in data and data["tax_amount"] is not None:
            invoice.tax_amount = float(data["tax_amount"])

        if "location_id" in data:
            if data["location_id"]:
                invoice.location_id = int(data["location_id"])
                # Look up location name from inventory database if not provided
                if "location_name" not in data or not data["location_name"]:
                    inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                                 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')
                    try:
                        from sqlalchemy import create_engine, text as sql_text
                        engine = create_engine(inventory_db_url)
                        with engine.connect() as conn:
                            result = conn.execute(
                                sql_text("SELECT name FROM locations WHERE id = :loc_id"),
                                {"loc_id": invoice.location_id}
                            ).fetchone()
                            if result:
                                invoice.location_name = result[0]
                    except Exception as loc_error:
                        logger.warning(f"Could not look up location name: {str(loc_error)}")
            else:
                invoice.location_id = None
                invoice.location_name = None

        if "location_name" in data and data["location_name"]:
            invoice.location_name = data["location_name"]

        db.commit()
        db.refresh(invoice)

        return {
            "success": True,
            "message": "Invoice updated successfully",
            "invoice": {
                "id": invoice.id,
                "vendor_name": invoice.vendor_name,
                "invoice_number": invoice.invoice_number,
                "invoice_date": str(invoice.invoice_date) if invoice.invoice_date else None,
                "due_date": str(invoice.due_date) if invoice.due_date else None,
                "total_amount": float(invoice.total_amount),
                "tax_amount": float(invoice.tax_amount) if invoice.tax_amount else None,
                "location_id": invoice.location_id,
                "location_name": invoice.location_name
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating invoice {invoice_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating invoice: {str(e)}")


@app.get("/api/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: int,
    download: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Serve the PDF file for an invoice
    If download=1 parameter is provided, force download instead of preview
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get invoice
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.pdf_path:
        raise HTTPException(status_code=404, detail="Invoice has no PDF file")

    # Check if file exists
    pdf_path = Path(invoice.pdf_path)
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {invoice.pdf_path}")
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    # Determine filename for download
    filename = f"invoice_{invoice.invoice_number}_{invoice.vendor_name}.pdf".replace(" ", "_").replace("/", "-")

    # Serve file
    if download:
        # Force download
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # Preview in browser
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )


@app.delete("/api/invoices/{invoice_id}")
async def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an invoice and all associated items
    """
    import logging
    import os
    logger = logging.getLogger(__name__)

    # Get invoice
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        # Delete associated invoice items first (due to foreign key constraint)
        items_deleted = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id
        ).delete()

        # Delete PDF file if it exists
        if invoice.pdf_path:
            pdf_path = Path(invoice.pdf_path)
            if pdf_path.exists():
                try:
                    os.remove(pdf_path)
                    logger.info(f"Deleted PDF file: {pdf_path}")
                except Exception as e:
                    logger.warning(f"Could not delete PDF file {pdf_path}: {str(e)}")

        # Delete invoice record
        db.delete(invoice)
        db.commit()

        logger.info(f"Deleted invoice {invoice_id} ({invoice.invoice_number}) with {items_deleted} items")

        return {
            "success": True,
            "message": f"Invoice {invoice.invoice_number} deleted successfully",
            "items_deleted": items_deleted
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting invoice {invoice_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting invoice: {str(e)}")


@app.patch("/api/invoices/{invoice_id}/items/bulk-update")
async def bulk_update_invoice_items(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Bulk update invoice line items.
    Used for inline editing of item_code, description, pack_size, unit_of_measure, quantity, unit_price.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get the request body
    body = await request.json()
    items_data = body.get('items', [])

    if not items_data:
        raise HTTPException(status_code=400, detail="No items provided")

    # Get invoice
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        updated_count = 0
        for item_data in items_data:
            item_id = item_data.get('id')
            if not item_id:
                continue

            item = db.query(HubInvoiceItem).filter(
                HubInvoiceItem.id == item_id,
                HubInvoiceItem.invoice_id == invoice_id
            ).first()

            if not item:
                logger.warning(f"Item {item_id} not found for invoice {invoice_id}")
                continue

            # Update allowed fields
            if 'item_code' in item_data:
                item.item_code = item_data['item_code']
            if 'item_description' in item_data:
                item.item_description = item_data['item_description']
            if 'pack_size' in item_data:
                item.pack_size = item_data['pack_size']
            if 'unit_of_measure' in item_data:
                item.unit_of_measure = item_data['unit_of_measure']
            if 'quantity' in item_data:
                item.quantity = item_data['quantity']
            if 'unit_price' in item_data:
                item.unit_price = item_data['unit_price']
                # Recalculate total
                item.total_amount = float(item.quantity) * float(item.unit_price)

            updated_count += 1

        db.commit()
        logger.info(f"Updated {updated_count} items for invoice {invoice_id}")

        return {
            "success": True,
            "message": f"Updated {updated_count} items",
            "updated_count": updated_count
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating items for invoice {invoice_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating items: {str(e)}")


@app.post("/api/invoices/{invoice_id}/mark-statement")
async def mark_invoice_as_statement(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Mark or unmark an invoice as a statement.
    Statements are not sent to inventory or accounting systems.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get the request body
    body = await request.json()
    is_statement = body.get('is_statement', True)

    # Get invoice
    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        invoice.is_statement = is_statement

        # If marking as statement, update status to 'statement' or similar
        if is_statement:
            invoice.status = 'statement'
        else:
            # Reset to pending if unmarking
            invoice.status = 'pending'

        db.commit()

        action = "marked as statement" if is_statement else "unmarked as statement"
        logger.info(f"Invoice {invoice_id} ({invoice.invoice_number}) {action}")

        return {
            "success": True,
            "message": f"Invoice {action} successfully",
            "is_statement": invoice.is_statement,
            "status": invoice.status
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error marking invoice {invoice_id} as statement: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating invoice: {str(e)}")


# ============================================================================
# UNMAPPED ITEMS REVIEW
# ============================================================================

@app.get("/unmapped-items", response_class=HTMLResponse)
async def unmapped_items(request: Request, db: Session = Depends(get_db)):
    """Review all unmapped invoice items - showing unique item descriptions only"""
    from sqlalchemy import func, distinct
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    # Get unique item descriptions with aggregated data
    # Query returns: (item_description, item_code, count, list of invoice numbers, list of vendors, list of invoice ids, inventory_item_id)
    unique_items_query = db.query(
        HubInvoiceItem.item_description,
        HubInvoiceItem.item_code,
        func.count(HubInvoiceItem.id).label('occurrence_count'),
        func.array_agg(distinct(HubInvoice.invoice_number)).label('invoice_numbers'),
        func.array_agg(distinct(HubInvoice.vendor_name)).label('vendor_names'),
        func.array_agg(distinct(HubInvoice.id)).label('invoice_ids'),
        func.max(HubInvoiceItem.inventory_item_id).label('inventory_item_id')  # Track if SKU matched in inventory
    ).join(HubInvoice).filter(
        HubInvoiceItem.is_mapped == False
    ).group_by(
        HubInvoiceItem.item_description,
        HubInvoiceItem.item_code
    ).order_by(
        func.count(HubInvoiceItem.id).desc()  # Show most frequent items first
    ).all()

    # Get item code info from item_code_mapping for suspicious code detection
    from sqlalchemy import text as sql_text
    item_code_info = {}
    try:
        code_info_results = db.execute(sql_text("""
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE item_code IS NOT NULL
        """)).fetchall()
        for code, canonical_desc, occ_count, is_verified in code_info_results:
            item_code_info[code] = {
                'canonical_description': canonical_desc,
                'total_occurrences': occ_count or 0,
                'is_verified': is_verified or False
            }
    except Exception as e:
        logger.warning(f"Failed to fetch item code info: {str(e)}")

    # Get list of vendor SKUs from inventory for checking if code exists there
    inventory_skus = set()
    try:
        sku_results = db.execute(sql_text("""
            SELECT vendor_sku FROM dblink(
                'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                'SELECT vendor_sku FROM vendor_items WHERE vendor_sku IS NOT NULL'
            ) AS t(vendor_sku VARCHAR)
        """)).fetchall()
        inventory_skus = {row[0] for row in sku_results}
    except Exception as e:
        logger.warning(f"Failed to fetch inventory SKUs: {str(e)}")

    # Format results for template with suspicious code detection
    unique_items = []
    for desc, item_code, count, invoice_nums, vendors, invoice_ids, inv_item_id in unique_items_query:
        # Determine if code is suspicious
        code_status = 'none'  # no code
        is_suspicious = False
        suspicious_reasons = []

        if item_code:
            code_info = item_code_info.get(item_code, {})
            is_verified = code_info.get('is_verified', False)
            total_occurrences = code_info.get('total_occurrences', count)
            in_inventory = item_code in inventory_skus

            if is_verified and in_inventory:
                code_status = 'verified'
            elif is_verified:
                code_status = 'verified_no_inventory'
            elif in_inventory:
                code_status = 'in_inventory'
            else:
                code_status = 'unknown'

            # Check if suspicious
            if not is_verified and not in_inventory:
                is_suspicious = True
                if total_occurrences == 1:
                    suspicious_reasons.append('Single occurrence (possible OCR error)')
                else:
                    suspicious_reasons.append('Not verified, not in inventory')

        # Pair invoice numbers with IDs for linking to PDFs
        invoice_list = []
        if invoice_nums and invoice_ids:
            for inv_num, inv_id in zip(invoice_nums, invoice_ids):
                invoice_list.append({'number': inv_num, 'id': inv_id})

        # Determine if this is a partial match (SKU found but no category in inventory)
        has_partial_match = inv_item_id is not None

        unique_items.append({
            'item_description': desc,
            'item_code': item_code,
            'occurrence_count': count,
            'invoice_numbers': invoice_nums if invoice_nums else [],
            'invoice_list': invoice_list,
            'vendor_names': vendors if vendors else [],
            'code_status': code_status,
            'is_suspicious': is_suspicious,
            'suspicious_reasons': suspicious_reasons,
            'has_partial_match': has_partial_match,
            'inventory_item_id': inv_item_id
        })

    # Fetch GL accounts from Accounting API
    gl_accounts = []
    try:
        async with httpx.AsyncClient() as client:
            # ACCOUNTING_API_URL already includes /api, so just append /accounts/
            response = await client.get(f"{ACCOUNTING_API_URL}/accounts/", params={"is_active": True, "limit": 1000})
            if response.status_code == 200:
                gl_accounts = response.json()
            else:
                logger.warning(f"Failed to fetch GL accounts: status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch GL accounts from Accounting API: {str(e)}")

    # Fetch vendor items from Hub's local table (Hub is source of truth)
    inventory_items = []
    try:
        from integration_hub.models.hub_vendor_item import HubVendorItem
        from integration_hub.models.vendor import Vendor as HubVendor
        from sqlalchemy.orm import joinedload

        hub_vendor_items = db.query(HubVendorItem).options(
            joinedload(HubVendorItem.vendor)
        ).filter(HubVendorItem.is_active == True).order_by(
            HubVendorItem.vendor_product_name
        ).all()

        for vi in hub_vendor_items:
            inventory_items.append({
                'id': vi.id,  # Hub vendor item ID
                'vendor_id': vi.vendor_id,
                'vendor_name': vi.vendor.name if vi.vendor else 'Unknown Vendor',
                'vendor_product_name': vi.vendor_product_name,
                'vendor_sku': vi.vendor_sku,
                'pack_size': vi.pack_size,
                'master_item_id': vi.inventory_master_item_id,
                'master_item_name': vi.inventory_master_item_name,
                'master_item_category': vi.category,
                'purchase_unit_id': vi.purchase_unit_id,
                'purchase_unit_name': vi.purchase_unit_name,
                'conversion_factor': float(vi.conversion_factor) if vi.conversion_factor else 1.0
            })

        logger.info(f"Loaded {len(inventory_items)} vendor items from Hub database")
    except Exception as e:
        logger.error(f"Failed to fetch vendor items from Hub: {str(e)}")

    # Also fetch verified item codes from item_code_mapping that don't have vendor items yet
    # This allows mapping by item code even when vendor item isn't in inventory system
    from sqlalchemy import text as sql_text
    try:
        verified_codes = db.execute(sql_text("""
            SELECT icm.item_code, icm.canonical_description
            FROM item_code_mapping icm
            WHERE icm.is_verified = true
            AND icm.item_code NOT IN (
                SELECT vendor_sku FROM dblink(
                    'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                    'SELECT vendor_sku FROM vendor_items WHERE vendor_sku IS NOT NULL'
                ) AS t(vendor_sku VARCHAR)
            )
            ORDER BY icm.canonical_description
        """)).fetchall()

        # Add verified item codes as special entries that can be mapped
        for code, description in verified_codes:
            inventory_items.append({
                "id": None,  # No inventory ID yet
                "vendor_id": None,
                "vendor_name": "[Item Code]",
                "vendor_sku": code,
                "vendor_product_name": description,
                "vendor_description": f"Item Code: {code}",
                "master_item_id": None,
                "master_item_name": None,
                "pack_size": None,
                "unit_price": None,
                "is_active": True,
                "is_preferred": False,
                "is_item_code": True  # Flag to identify these
            })
    except Exception as e:
        logger.warning(f"Failed to fetch verified item codes: {str(e)}")

    # Get active category mappings for the dropdown
    category_mappings = db.query(CategoryGLMapping).filter(
        CategoryGLMapping.is_active == True
    ).order_by(CategoryGLMapping.inventory_category).all()

    # Get vendors for the "Create New" vendor item form
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    response = templates.TemplateResponse("unmapped_items.html", {
        "request": request,
        "unique_items": unique_items,
        "gl_accounts": gl_accounts,
        "inventory_items": inventory_items,
        "category_mappings": category_mappings,
        "vendors": vendors
    })
    # Prevent browser caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/mapped-items", response_class=HTMLResponse)
async def mapped_items(request: Request, db: Session = Depends(get_db)):
    """Review all mapped invoice items - showing unique item descriptions with their mappings"""
    from sqlalchemy import func, distinct
    import httpx
    import logging

    logger = logging.getLogger(__name__)

    # Get unique mapped item descriptions with aggregated data
    unique_items_query = db.query(
        HubInvoiceItem.item_description,
        func.count(HubInvoiceItem.id).label('occurrence_count'),
        func.array_agg(distinct(HubInvoice.invoice_number)).label('invoice_numbers'),
        func.array_agg(distinct(HubInvoice.vendor_name)).label('vendor_names'),
        # Get the mapping from one of the items (they should all be the same for the same description)
        func.max(HubInvoiceItem.inventory_item_id).label('inventory_item_id'),
        func.max(HubInvoiceItem.inventory_category).label('inventory_category'),
        func.max(HubInvoiceItem.item_code).label('item_code'),  # Add item code
        func.max(HubInvoiceItem.gl_asset_account).label('gl_asset_account'),
        func.max(HubInvoiceItem.gl_cogs_account).label('gl_cogs_account'),
        func.max(HubInvoiceItem.gl_waste_account).label('gl_waste_account')
    ).join(HubInvoice).filter(
        HubInvoiceItem.is_mapped == True
    ).group_by(
        HubInvoiceItem.item_description
    ).order_by(
        func.count(HubInvoiceItem.id).desc()
    ).all()

    # Fetch GL accounts from Accounting API
    gl_accounts = []
    gl_accounts_map = {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ACCOUNTING_API_URL}/accounts/", params={"is_active": True, "limit": 1000})
            if response.status_code == 200:
                gl_accounts = response.json()
                # Create a map of account number to account name for quick lookup
                # Store both string and int keys since API returns strings but DB stores ints
                for account in gl_accounts:
                    account_num = account['account_number']
                    account_name = account['account_name']
                    gl_accounts_map[account_num] = account_name  # string key
                    gl_accounts_map[int(account_num)] = account_name  # int key
            else:
                logger.warning(f"Failed to fetch GL accounts: status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch GL accounts from Accounting API: {str(e)}")

    # Fetch vendor items from Hub's local table (Hub is source of truth)
    inventory_items = []
    inventory_items_map = {}
    try:
        from integration_hub.models.hub_vendor_item import HubVendorItem
        from integration_hub.models.vendor import Vendor as HubVendor
        from sqlalchemy.orm import joinedload

        hub_vendor_items = db.query(HubVendorItem).options(
            joinedload(HubVendorItem.vendor)
        ).filter(HubVendorItem.is_active == True).order_by(
            HubVendorItem.vendor_product_name
        ).all()

        for vi in hub_vendor_items:
            item_data = {
                'id': vi.id,  # Hub vendor item ID
                'vendor_id': vi.vendor_id,
                'vendor_name': vi.vendor.name if vi.vendor else 'Unknown Vendor',
                'vendor_product_name': vi.vendor_product_name,
                'vendor_sku': vi.vendor_sku,
                'pack_size': vi.pack_size,
                'master_item_id': vi.inventory_master_item_id,
                'master_item_name': vi.inventory_master_item_name,
                'master_item_category': vi.category,
                'purchase_unit_id': vi.purchase_unit_id,
                'purchase_unit_name': vi.purchase_unit_name,
                'conversion_factor': float(vi.conversion_factor) if vi.conversion_factor else 1.0
            }
            inventory_items.append(item_data)
            inventory_items_map[vi.id] = item_data

        logger.info(f"Loaded {len(inventory_items)} vendor items from Hub database for mapped items page")
    except Exception as e:
        logger.error(f"Failed to fetch vendor items from Hub: {str(e)}")

    # Format results for template with vendor item details
    unique_items = []
    for desc, count, invoice_nums, vendors, inv_item_id, category, item_code, asset_acct, cogs_acct, waste_acct in unique_items_query:
        vendor_item_details = None
        if inv_item_id and inv_item_id in inventory_items_map:
            item = inventory_items_map[inv_item_id]
            vendor_item_details = f"{item['vendor_name']}: {item['vendor_product_name']}"
            if item.get('vendor_sku'):
                vendor_item_details += f" [{item['vendor_sku']}]"
            if item.get('pack_size'):
                vendor_item_details += f" - {item['pack_size']}"

        unique_items.append({
            'item_description': desc,
            'occurrence_count': count,
            'invoice_numbers': invoice_nums if invoice_nums else [],
            'vendor_names': vendors if vendors else [],
            'inventory_item_id': inv_item_id,
            'inventory_category': category,
            'item_code': item_code,
            'vendor_item_details': vendor_item_details,
            'gl_asset_account': asset_acct,
            'gl_cogs_account': cogs_acct,
            'gl_waste_account': waste_acct,
            'gl_asset_account_name': gl_accounts_map.get(asset_acct) if asset_acct else None,
            'gl_cogs_account_name': gl_accounts_map.get(cogs_acct) if cogs_acct else None,
            'gl_waste_account_name': gl_accounts_map.get(waste_acct) if waste_acct else None
        })

    # Get active category mappings for the dropdown
    category_mappings = db.query(CategoryGLMapping).filter(
        CategoryGLMapping.is_active == True
    ).order_by(CategoryGLMapping.inventory_category).all()

    return templates.TemplateResponse("mapped_items.html", {
        "request": request,
        "unique_items": unique_items,
        "gl_accounts": gl_accounts,
        "inventory_items": inventory_items,
        "category_mappings": category_mappings
    })


# ============================================================================
# ITEM MAPPING APIs
# ============================================================================

@app.post("/api/invoices/{invoice_id}/auto-map")
async def auto_map_invoice_items(invoice_id: int, db: Session = Depends(get_db)):
    """
    Auto-map invoice items using intelligent matching

    Uses vendor codes, fuzzy description matching, and category mappings
    to automatically assign inventory items and GL accounts.
    """
    from integration_hub.services.auto_mapper import get_auto_mapper

    try:
        # Check if invoice exists
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        if not invoice:
            return {
                "success": False,
                "message": f"Invoice {invoice_id} not found"
            }

        # Run auto-mapper
        mapper = get_auto_mapper(db)
        stats = mapper.map_invoice_items(invoice_id)

        if stats.get('error'):
            return {
                "success": False,
                "message": stats['error']
            }

        return {
            "success": True,
            "message": f"Auto-mapped {stats['mapped_count']} of {stats['total_items']} items",
            "stats": stats
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error auto-mapping invoice {invoice_id}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Error auto-mapping: {str(e)}"
        }

@app.post("/api/items/{item_id}/map")
async def map_item(
    item_id: int,
    inventory_item_id: Optional[int] = None,
    inventory_category: Optional[str] = None,
    gl_asset_account: Optional[int] = None,
    gl_cogs_account: Optional[int] = None,
    gl_waste_account: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Manually map an invoice item to inventory item and GL accounts"""

    item = db.query(HubInvoiceItem).filter(HubInvoiceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Update mapping
    item.inventory_item_id = inventory_item_id
    item.inventory_category = inventory_category
    item.gl_asset_account = gl_asset_account
    item.gl_cogs_account = gl_cogs_account
    item.gl_waste_account = gl_waste_account
    item.is_mapped = True
    item.mapping_method = 'manual'

    db.commit()

    # Check if invoice is now fully mapped
    invoice = db.query(HubInvoice).filter(HubInvoice.id == item.invoice_id).first()
    unmapped_count = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.invoice_id == invoice.id,
        HubInvoiceItem.is_mapped == False
    ).count()

    invoice_ready = unmapped_count == 0

    if invoice_ready:
        invoice.status = 'ready'
        db.commit()

        # Trigger auto-send
        try:
            inventory_sender = get_inventory_sender(INVENTORY_API_URL)
            accounting_sender = get_accounting_sender(ACCOUNTING_API_URL)
            auto_send = get_auto_send_service(inventory_sender, accounting_sender)

            # Send in background (non-blocking)
            import asyncio
            asyncio.create_task(auto_send.send_invoice(invoice.id, db))
        except Exception as e:
            # Log but don't fail the mapping operation
            print(f"Auto-send trigger failed: {str(e)}")

    return {"success": True, "item_id": item_id, "invoice_ready": invoice_ready}


@app.post("/api/items/map-by-description")
async def map_items_by_description(
    item_description: str = Form(...),
    inventory_item_id: Optional[int] = Form(None),
    inventory_category: Optional[str] = Form(None),
    gl_asset_account: Optional[str] = Form(None),  # Account number as string
    gl_cogs_account: str = Form(...),  # Required - account number as string
    gl_waste_account: Optional[str] = Form(None),  # Account number as string
    db: Session = Depends(get_db)
):
    """
    Map ALL unmapped items with a specific description to inventory item and GL accounts

    Note: Only gl_cogs_account is required. Category is optional (for non-inventory items like linen, propane, etc.)
    Account numbers are passed as strings but stored as integers (extracting numeric part only).
    """

    # Convert account number strings to integers (strip non-numeric characters)
    def parse_account_number(account_str: Optional[str]) -> Optional[int]:
        if not account_str:
            return None
        # Extract just the numeric part (account number before the dash/space)
        import re
        match = re.match(r'(\d+)', account_str.strip())
        return int(match.group(1)) if match else None

    gl_asset_account_int = parse_account_number(gl_asset_account)
    gl_cogs_account_int = parse_account_number(gl_cogs_account)
    gl_waste_account_int = parse_account_number(gl_waste_account)

    if not gl_cogs_account_int:
        raise HTTPException(status_code=400, detail="Invalid COGS/Expense account number")

    # Find all items with this description (both mapped and unmapped)
    # This allows editing of already-mapped items from the mapped items page
    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.item_description == item_description
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail=f"No items found with description: {item_description}")

    # Update all matching items
    items_mapped = 0
    invoices_affected = set()

    for item in items:
        item.inventory_item_id = inventory_item_id
        item.inventory_category = inventory_category
        item.gl_asset_account = gl_asset_account_int
        item.gl_cogs_account = gl_cogs_account_int
        item.gl_waste_account = gl_waste_account_int
        item.is_mapped = True
        item.mapping_method = 'manual_bulk'
        items_mapped += 1
        invoices_affected.add(item.invoice_id)

    # Save this mapping for future auto-mapping of same item descriptions
    # Uses invoice_item_mapping table (separate from inventory item GL mappings)
    if items:
        from sqlalchemy import text as sql_text
        # Check if a mapping already exists for this exact description
        existing = db.execute(
            sql_text("SELECT id FROM invoice_item_mapping WHERE item_description = :desc"),
            {"desc": item_description}
        ).fetchone()

        if existing:
            # Update existing mapping
            db.execute(
                sql_text("""
                    UPDATE invoice_item_mapping
                    SET inventory_item_id = :inv_id,
                        inventory_item_name = :inv_name,
                        inventory_category = :category,
                        gl_asset_account = :asset,
                        gl_cogs_account = :cogs,
                        gl_waste_account = :waste,
                        is_active = true,
                        updated_at = NOW()
                    WHERE item_description = :desc
                """),
                {
                    "inv_id": inventory_item_id,
                    "inv_name": items[0].inventory_item_name if items else None,
                    "category": inventory_category,
                    "asset": gl_asset_account_int,
                    "cogs": gl_cogs_account_int,
                    "waste": gl_waste_account_int,
                    "desc": item_description
                }
            )
        else:
            # Create new mapping entry for future auto-mapping
            db.execute(
                sql_text("""
                    INSERT INTO invoice_item_mapping
                    (item_description, inventory_item_id, inventory_item_name, inventory_category,
                     gl_asset_account, gl_cogs_account, gl_waste_account, is_active, notes)
                    VALUES (:desc, :inv_id, :inv_name, :category, :asset, :cogs, :waste, true, :notes)
                """),
                {
                    "desc": item_description,
                    "inv_id": inventory_item_id,
                    "inv_name": items[0].inventory_item_name if items else None,
                    "category": inventory_category or "Uncategorized",
                    "asset": gl_asset_account_int or gl_cogs_account_int,
                    "cogs": gl_cogs_account_int,
                    "waste": gl_waste_account_int,
                    "notes": f"Auto-created from bulk mapping"
                }
            )

    # Auto-verify item codes when user maps items
    # This confirms the item code is correct since user is mapping it
    item_codes_to_verify = set()
    for item in items:
        if item.item_code:
            item_codes_to_verify.add(item.item_code)

    if item_codes_to_verify:
        for code in item_codes_to_verify:
            # Check if item code already exists in mapping
            existing_code = db.execute(
                sql_text("SELECT id, is_verified FROM item_code_mapping WHERE item_code = :code"),
                {"code": code}
            ).fetchone()

            if existing_code:
                # Mark as verified if not already
                if not existing_code[1]:  # is_verified
                    db.execute(
                        sql_text("""
                            UPDATE item_code_mapping
                            SET is_verified = true, updated_at = NOW()
                            WHERE item_code = :code
                        """),
                        {"code": code}
                    )
            else:
                # Create new verified item code mapping
                db.execute(
                    sql_text("""
                        INSERT INTO item_code_mapping
                        (item_code, canonical_description, occurrence_count, is_verified, created_at)
                        VALUES (:code, :desc, :count, true, NOW())
                    """),
                    {"code": code, "desc": item_description, "count": len(items)}
                )

    db.commit()

    # Check each affected invoice to see if it's now fully mapped
    invoices_ready = []
    for invoice_id in invoices_affected:
        invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
        unmapped_count = db.query(HubInvoiceItem).filter(
            HubInvoiceItem.invoice_id == invoice_id,
            HubInvoiceItem.is_mapped == False
        ).count()

        if unmapped_count == 0:
            invoice.status = 'ready'
            invoices_ready.append(invoice.invoice_number)

            # Trigger auto-send
            try:
                inventory_sender = get_inventory_sender(INVENTORY_API_URL)
                accounting_sender = get_accounting_sender(ACCOUNTING_API_URL)
                auto_send = get_auto_send_service(inventory_sender, accounting_sender)

                # Send in background (non-blocking)
                import asyncio
                asyncio.create_task(auto_send.send_invoice(invoice_id, db))
            except Exception as e:
                # Log but don't fail the mapping operation
                print(f"Auto-send trigger failed for invoice {invoice_id}: {str(e)}")

    db.commit()

    return {
        "success": True,
        "items_mapped": items_mapped,
        "invoices_affected": len(invoices_affected),
        "invoices_ready": invoices_ready
    }


@app.get("/api/items/{item_id}/suggestions")
async def get_mapping_suggestions(item_id: int, db: Session = Depends(get_db)):
    """Get mapping suggestions for an invoice item using fuzzy matching"""

    item = db.query(HubInvoiceItem).filter(HubInvoiceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # TODO: Implement fuzzy matching against inventory items
    # For now, return empty suggestions
    return {
        "item_id": item_id,
        "description": item.item_description,
        "suggestions": []
    }


# ============================================================================
# CATEGORY MAPPING MANAGEMENT
# ============================================================================

@app.get("/category-mappings", response_class=HTMLResponse)
async def list_category_mappings(request: Request, db: Session = Depends(get_db)):
    """Manage category to GL account mappings"""
    import httpx
    import logging
    logger = logging.getLogger(__name__)

    mappings = db.query(CategoryGLMapping).order_by(CategoryGLMapping.inventory_category).all()

    # Fetch GL accounts from Accounting API
    gl_accounts = []
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ACCOUNTING_API_URL}/accounts/", params={"is_active": True, "limit": 1000})
            if response.status_code == 200:
                gl_accounts = response.json()
            else:
                logger.warning(f"Failed to fetch GL accounts: status {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching GL accounts: {str(e)}")

    # Create a lookup dictionary for account names
    account_lookup = {str(acc['account_number']): acc['account_name'] for acc in gl_accounts}

    # Enrich mappings with account names
    enriched_mappings = []
    for mapping in mappings:
        mapping_dict = {
            'id': mapping.id,
            'inventory_category': mapping.inventory_category,
            'gl_asset_account': mapping.gl_asset_account,
            'gl_cogs_account': mapping.gl_cogs_account,
            'gl_waste_account': mapping.gl_waste_account,
            'asset_account_name': mapping.asset_account_name,
            'is_active': mapping.is_active,
            # Add account names from lookup
            'asset_account_full': account_lookup.get(str(mapping.gl_asset_account), 'Unknown'),
            'cogs_account_full': account_lookup.get(str(mapping.gl_cogs_account), 'Unknown'),
            'waste_account_full': account_lookup.get(str(mapping.gl_waste_account), 'Unknown') if mapping.gl_waste_account else None
        }
        enriched_mappings.append(mapping_dict)

    # Get categories from Inventory system for the dropdown
    inventory_categories = []
    inventory_categories_count = 0
    try:
        from sqlalchemy import text as sql_text
        inv_result = db.execute(sql_text("""
            SELECT name, parent_name
            FROM dblink(
                'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                'SELECT c.name, p.name as parent_name
                 FROM categories c
                 LEFT JOIN categories p ON c.parent_id = p.id
                 WHERE c.is_active = true OR c.is_active IS NULL
                 ORDER BY COALESCE(p.name, c.name), c.name'
            ) AS t(name VARCHAR, parent_name VARCHAR)
        """)).fetchall()

        for cat in inv_result:
            cat_name = cat[0]
            parent_name = cat[1]
            if parent_name:
                standardized_name = f"{parent_name} - {cat_name}"
            else:
                standardized_name = cat_name
            inventory_categories.append(standardized_name)

        inventory_categories_count = len(inventory_categories)
    except Exception:
        pass  # Inventory unavailable, keep as empty

    return templates.TemplateResponse("category_mappings.html", {
        "request": request,
        "mappings": enriched_mappings,
        "gl_accounts": gl_accounts,
        "inventory_categories": inventory_categories,
        "inventory_categories_count": inventory_categories_count
    })


@app.get("/api/category-mappings/{category:path}")
async def get_category_mapping(category: str, db: Session = Depends(get_db)):
    """Get GL account mapping for a specific category"""

    mapping = db.query(CategoryGLMapping).filter(
        CategoryGLMapping.inventory_category == category,
        CategoryGLMapping.is_active == True
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail=f"No mapping found for category: {category}")

    return {
        "inventory_category": mapping.inventory_category,
        "gl_asset_account": mapping.gl_asset_account,
        "gl_cogs_account": mapping.gl_cogs_account,
        "gl_waste_account": mapping.gl_waste_account,
        "asset_account_name": mapping.asset_account_name,
        "cogs_account_name": mapping.cogs_account_name,
        "waste_account_name": mapping.waste_account_name
    }


@app.post("/api/category-mappings")
async def create_category_mapping(
    inventory_category: str = Form(...),
    asset_account_name: Optional[str] = Form(None),
    cogs_account_name: Optional[str] = Form(None),
    waste_account_name: Optional[str] = Form(None),
    gl_asset_account: int = Form(...),
    gl_cogs_account: int = Form(...),
    gl_waste_account: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Create or update category mapping"""

    # Check if exists
    mapping = db.query(CategoryGLMapping).filter(
        CategoryGLMapping.inventory_category == inventory_category
    ).first()

    if mapping:
        # Update existing
        mapping.asset_account_name = asset_account_name
        mapping.cogs_account_name = cogs_account_name
        mapping.waste_account_name = waste_account_name
        mapping.gl_asset_account = gl_asset_account
        mapping.gl_cogs_account = gl_cogs_account
        mapping.gl_waste_account = gl_waste_account
        mapping.is_active = True
    else:
        # Create new
        mapping = CategoryGLMapping(
            inventory_category=inventory_category,
            asset_account_name=asset_account_name,
            cogs_account_name=cogs_account_name,
            waste_account_name=waste_account_name,
            gl_asset_account=gl_asset_account,
            gl_cogs_account=gl_cogs_account,
            gl_waste_account=gl_waste_account,
            is_active=True
        )
        db.add(mapping)

    db.commit()

    return RedirectResponse(url="/hub/category-mappings", status_code=303)


@app.post("/api/category-mappings/sync-from-inventory")
async def sync_categories_from_inventory(db: Session = Depends(get_db)):
    """
    Sync categories from Inventory system to category_gl_mapping table.
    Creates placeholder entries for unmapped categories.
    """
    from sqlalchemy import text as sql_text

    try:
        # Fetch categories from Inventory database (with hierarchy)
        inventory_categories = db.execute(sql_text("""
            SELECT name, parent_name, description
            FROM dblink(
                'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                'SELECT c.name, p.name as parent_name, c.description
                 FROM categories c
                 LEFT JOIN categories p ON c.parent_id = p.id
                 WHERE c.is_active = true OR c.is_active IS NULL
                 ORDER BY COALESCE(p.name, c.name), c.name'
            ) AS t(name VARCHAR, parent_name VARCHAR, description TEXT)
        """)).fetchall()

        if not inventory_categories:
            return {"success": False, "error": "No categories found in Inventory system"}

        imported_count = 0
        already_exists = 0
        unmapped = []

        for cat in inventory_categories:
            cat_name = cat[0]
            parent_name = cat[1]

            # Build standardized category name (Parent - Child format)
            if parent_name:
                standardized_name = f"{parent_name} - {cat_name}"
            else:
                standardized_name = cat_name

            # Check if this category already exists in mappings
            existing = db.query(CategoryGLMapping).filter(
                CategoryGLMapping.inventory_category == standardized_name
            ).first()

            if existing:
                already_exists += 1
            else:
                # Create placeholder entry (will need GL accounts assigned)
                # Use 0 as placeholder for required GL accounts
                new_mapping = CategoryGLMapping(
                    inventory_category=standardized_name,
                    asset_account_name=f"{standardized_name} Inventory",
                    gl_asset_account=0,  # Placeholder - needs to be set
                    gl_cogs_account=0,   # Placeholder - needs to be set
                    gl_waste_account=None,
                    is_active=False  # Mark inactive until GL accounts are assigned
                )
                db.add(new_mapping)
                imported_count += 1
                unmapped.append(standardized_name)

        db.commit()

        return {
            "success": True,
            "imported": imported_count,
            "already_exists": already_exists,
            "total_synced": len(inventory_categories),
            "unmapped": unmapped
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


# ============================================================================
# WEBHOOK ENDPOINT (for email forwarding)
# ============================================================================

@app.post("/api/webhook/email")
async def receive_email_invoice(request: Request, db: Session = Depends(get_db)):
    """Receive invoice via email webhook (e.g., from SendGrid, Mailgun)"""

    # TODO: Implement email parsing
    # This will depend on which email service you use
    # For now, just log it

    body = await request.json()

    return {"status": "received", "message": "Email webhook not yet implemented"}


# ============================================================================
# SEND TO SYSTEMS APIs
# ============================================================================

@app.post("/api/invoices/{invoice_id}/send")
async def send_invoice_to_systems(invoice_id: int, db: Session = Depends(get_db)):
    """Send invoice to both Inventory and Accounting systems"""

    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Don't send statements to systems
    if invoice.is_statement:
        raise HTTPException(status_code=400, detail="Statements cannot be sent to inventory or accounting systems")

    if invoice.status not in ['ready', 'partial', 'error']:
        raise HTTPException(status_code=400, detail=f"Invoice status '{invoice.status}' cannot be sent")

    # Get service instances
    inventory_sender = get_inventory_sender(INVENTORY_API_URL)
    accounting_sender = get_accounting_sender(ACCOUNTING_API_URL)
    auto_send = get_auto_send_service(inventory_sender, accounting_sender)

    # Send invoice
    try:
        result = await auto_send.send_invoice(invoice_id, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/invoices/{invoice_id}/retry")
async def retry_invoice_send(
    invoice_id: int,
    system: str = 'both',  # 'inventory', 'accounting', or 'both'
    db: Session = Depends(get_db)
):
    """Retry sending invoice to failed system(s)"""

    if system not in ['inventory', 'accounting', 'both']:
        raise HTTPException(status_code=400, detail="system must be 'inventory', 'accounting', or 'both'")

    invoice = db.query(HubInvoice).filter(HubInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get service instances
    inventory_sender = get_inventory_sender(INVENTORY_API_URL)
    accounting_sender = get_accounting_sender(ACCOUNTING_API_URL)
    auto_send = get_auto_send_service(inventory_sender, accounting_sender)

    # Retry send
    try:
        result = await auto_send.retry_failed_send(invoice_id, db, retry_system=system)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VENDOR MANAGEMENT
# ============================================================================

@app.get("/api/vendors/", response_model=List[VendorResponse])
async def get_vendors(db: Session = Depends(get_db)):
    """Get all vendors from Hub database"""
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()
    return vendors


@app.post("/api/vendors/", response_model=VendorResponse)
async def create_vendor(
    vendor_data: VendorCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new vendor and optionally push to Inventory and Accounting systems
    """
    # Create vendor in Hub database
    vendor = Vendor(
        name=vendor_data.name,
        contact_name=vendor_data.contact_name,
        email=vendor_data.email,
        phone=vendor_data.phone,
        address=vendor_data.address,
        city=vendor_data.city,
        state=vendor_data.state,
        zip_code=vendor_data.zip_code,
        payment_terms=vendor_data.payment_terms,
        tax_id=vendor_data.tax_id,
        notes=vendor_data.notes,
        is_active=vendor_data.is_active
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)

    # Get sync service
    vendor_sync = get_vendor_sync_service()

    # Push to other systems if requested
    errors = []

    if vendor_data.push_to_inventory:
        inv_result = await vendor_sync.push_vendor_to_inventory(vendor)
        if inv_result.get("success"):
            vendor.inventory_vendor_id = inv_result.get("vendor_id")
            db.commit()
        else:
            errors.append(f"Inventory sync failed: {inv_result.get('error')}")

    if vendor_data.push_to_accounting:
        acc_result = await vendor_sync.push_vendor_to_accounting(vendor)
        if acc_result.get("success"):
            vendor.accounting_vendor_id = acc_result.get("vendor_id")
            db.commit()
        else:
            errors.append(f"Accounting sync failed: {acc_result.get('error')}")

    db.refresh(vendor)

    # Return vendor with sync status info
    return vendor


@app.post("/api/vendors/sync")
async def sync_vendors(db: Session = Depends(get_db)):
    """Sync vendors from Inventory and Accounting systems to Hub"""
    vendor_sync = get_vendor_sync_service()
    result = await vendor_sync.sync_vendors_to_hub(db)
    return result


@app.get("/vendors", response_class=HTMLResponse)
async def vendors_page(request: Request, db: Session = Depends(get_db)):
    """Vendor management page - only show active vendors"""
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    return templates.TemplateResponse("vendors.html", {
        "request": request,
        "vendors": vendors
    })


@app.get("/duplicates", response_class=HTMLResponse)
async def duplicates_page(request: Request):
    """Duplicate invoice detection page"""
    return templates.TemplateResponse("duplicates.html", {
        "request": request
    })


@app.get("/vendor-items", response_class=HTMLResponse)
async def vendor_items_page(
    request: Request,
    db: Session = Depends(get_db),
    master_item: Optional[int] = Query(None, description="Filter by master item ID")
):
    """Hub Vendor Items management page - Hub is source of truth"""
    from sqlalchemy.orm import joinedload
    from integration_hub.models.hub_vendor_item import VendorItemStatus

    # Build query with optional master item filter
    query = db.query(HubVendorItem).options(
        joinedload(HubVendorItem.vendor),
        joinedload(HubVendorItem.size_unit),
        joinedload(HubVendorItem.container)
    )

    if master_item:
        query = query.filter(HubVendorItem.inventory_master_item_id == master_item)

    vendor_items = query.order_by(HubVendorItem.vendor_product_name).all()

    # Get active vendors for filters and forms
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    # Get distinct categories
    categories_query = db.query(HubVendorItem.category).filter(
        HubVendorItem.category.isnot(None),
        HubVendorItem.category != ''
    ).distinct().order_by(HubVendorItem.category).all()
    categories = [c[0] for c in categories_query]

    # Fetch units of measure from Hub database
    from integration_hub.models.unit_of_measure import UnitOfMeasure
    units_query = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).order_by(UnitOfMeasure.name).all()
    units = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation or ""} for u in units_query]

    # Fallback if no units
    if not units:
        units = [
            {"id": 1, "name": "Each", "abbreviation": "EA"},
            {"id": 2, "name": "Case", "abbreviation": "CS"},
            {"id": 3, "name": "Pound", "abbreviation": "LB"},
            {"id": 4, "name": "Gallon", "abbreviation": "GAL"},
        ]

    # Fetch locations and master items from Inventory database directly (no auth needed)
    from sqlalchemy import create_engine, text as sql_text
    inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')
    locations = []
    master_items = []
    try:
        inv_engine = create_engine(inventory_db_url)
        with inv_engine.connect() as conn:
            # Fetch locations
            results = conn.execute(
                sql_text("SELECT id, name FROM locations WHERE is_active = true ORDER BY name")
            ).fetchall()
            locations = [{"id": row[0], "name": row[1]} for row in results]

            # Fetch master items (limit 2000 for dropdown)
            items_results = conn.execute(
                sql_text("SELECT id, name, category FROM master_items WHERE is_active = true ORDER BY name LIMIT 2000")
            ).fetchall()
            master_items = [{"id": row[0], "name": row[1], "category": row[2]} for row in items_results]
    except Exception as e:
        logger.warning(f"Could not fetch data from Inventory database: {e}")

    # Stats with status counts
    stats = {
        "total": len(vendor_items),
        "active": sum(1 for vi in vendor_items if vi.status == VendorItemStatus.active),
        "needs_review": sum(1 for vi in vendor_items if vi.status == VendorItemStatus.needs_review),
        "inactive": sum(1 for vi in vendor_items if vi.status == VendorItemStatus.inactive),
        "synced": sum(1 for vi in vendor_items if vi.synced_to_inventory),
        "vendors": len(vendors)
    }

    # Get filtered master item name if filtering
    filter_master_item_name = None
    if master_item:
        for mi in master_items:
            if mi["id"] == master_item:
                filter_master_item_name = mi["name"]
                break

    return templates.TemplateResponse("hub_vendor_items.html", {
        "request": request,
        "vendor_items": vendor_items,
        "vendors": vendors,
        "locations": locations,
        "categories": categories,
        "units": units,
        "master_items": master_items,
        "stats": stats,
        "filter_master_item_id": master_item,
        "filter_master_item_name": filter_master_item_name
    })


@app.get("/vendor-item-detail", response_class=HTMLResponse)
async def vendor_item_detail_page(request: Request, id: int = Query(..., description="Vendor Item ID"), db: Session = Depends(get_db)):
    """
    Vendor Item detail page - comprehensive view of a single vendor item.

    Shows:
    - Product details (vendor, SKU, name, description)
    - Pricing information (last price, cost per unit)
    - Master item mapping
    - Price history from invoices
    - AI similar items
    - Review status and sync info
    """
    # Get vendors for edit modal
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    # Get distinct categories
    categories_query = db.query(HubVendorItem.category).filter(
        HubVendorItem.category.isnot(None),
        HubVendorItem.category != ''
    ).distinct().order_by(HubVendorItem.category).all()
    categories = [c[0] for c in categories_query]

    # Get units of measure (legacy, for compatibility)
    from integration_hub.models.unit_of_measure import UnitOfMeasure
    units_query = db.query(UnitOfMeasure).filter(UnitOfMeasure.is_active == True).order_by(UnitOfMeasure.name).all()
    units = [{"id": u.id, "name": u.name, "abbreviation": u.abbreviation or ""} for u in units_query]

    # Fallback if no units
    if not units:
        units = [
            {"id": 1, "name": "Each", "abbreviation": "EA"},
            {"id": 2, "name": "Case", "abbreviation": "CS"},
            {"id": 3, "name": "Pound", "abbreviation": "LB"},
            {"id": 4, "name": "Gallon", "abbreviation": "GAL"},
        ]

    # Get Backbar-style size units
    from integration_hub.models.size_unit import SizeUnit
    size_units_query = db.query(SizeUnit).filter(SizeUnit.is_active == True).order_by(SizeUnit.measure_type, SizeUnit.sort_order).all()
    size_units = [{"id": u.id, "name": u.name, "symbol": u.symbol, "measure_type": u.measure_type} for u in size_units_query]

    # Get containers
    from integration_hub.models.container import Container
    containers_query = db.query(Container).filter(Container.is_active == True).order_by(Container.sort_order).all()
    containers = [{"id": c.id, "name": c.name} for c in containers_query]

    # Fetch locations and master items from Inventory database
    from sqlalchemy import create_engine, text as sql_text
    inventory_db_url = os.getenv('INVENTORY_DATABASE_URL',
                                 'postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db')
    locations = []
    master_items = []
    try:
        inv_engine = create_engine(inventory_db_url)
        with inv_engine.connect() as conn:
            results = conn.execute(
                sql_text("SELECT id, name FROM locations WHERE is_active = true ORDER BY name")
            ).fetchall()
            locations = [{"id": row[0], "name": row[1]} for row in results]

            items_results = conn.execute(
                sql_text("SELECT id, name, category FROM master_items WHERE is_active = true ORDER BY name LIMIT 2000")
            ).fetchall()
            master_items = [{"id": row[0], "name": row[1], "category": row[2]} for row in items_results]
    except Exception as e:
        logger.warning(f"Could not fetch data from Inventory database: {e}")

    return templates.TemplateResponse("vendor_item_detail.html", {
        "request": request,
        "item_id": id,
        "vendors": vendors,
        "categories": categories,
        "units": units,
        "size_units": size_units,
        "containers": containers,
        "locations": locations,
        "master_items": master_items
    })


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """System settings configuration page"""
    from datetime import datetime
    response = templates.TemplateResponse("settings.html", {
        "request": request,
        "cache_bust": int(datetime.now().timestamp())
    })
    # Add cache-control headers to prevent browser caching
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/settings/size", response_class=HTMLResponse)
def size_settings_page(request: Request):
    """Size units and containers settings page (Backbar-style sizing)"""
    return templates.TemplateResponse("size_settings.html", {
        "request": request
    })


# ============================================================================
# ITEM CODE MANAGEMENT
# ============================================================================

@app.get("/item-codes", response_class=HTMLResponse)
async def item_codes_page(
    request: Request,
    search: str = "",
    filter: str = "all",
    db: Session = Depends(get_db)
):
    """Item code management page for fixing OCR errors"""
    from sqlalchemy import text as sql_text

    # Build query based on filter
    if filter == "duplicates":
        # Find item codes that might be duplicates (similar codes with different descriptions)
        query = """
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE item_code IS NOT NULL
            ORDER BY canonical_description, item_code
        """
    elif filter == "single":
        # Single occurrence items are often OCR errors
        query = """
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE occurrence_count = 1
            ORDER BY canonical_description
        """
    elif filter == "unverified":
        # Show only unverified item codes
        query = """
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE item_code IS NOT NULL AND (is_verified = false OR is_verified IS NULL)
            ORDER BY occurrence_count DESC, canonical_description
        """
    elif filter == "verified":
        # Show only verified item codes
        query = """
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE item_code IS NOT NULL AND is_verified = true
            ORDER BY canonical_description
        """
    else:
        query = """
            SELECT item_code, canonical_description, occurrence_count, is_verified
            FROM item_code_mapping
            WHERE item_code IS NOT NULL
            ORDER BY canonical_description
        """

    results = db.execute(sql_text(query)).fetchall()

    # Apply search filter
    item_codes = []
    for row in results:
        if search:
            if search.lower() not in row[0].lower() and search.lower() not in row[1].lower():
                continue
        item_codes.append({
            "item_code": row[0],
            "canonical_description": row[1],
            "occurrence_count": row[2],
            "is_verified": row[3] or False
        })

    # Get count of verified vendor items from Inventory system
    inventory_items_count = 0
    try:
        inv_result = db.execute(sql_text("""
            SELECT COUNT(*) FROM dblink(
                'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                'SELECT id FROM vendor_items WHERE vendor_sku IS NOT NULL'
            ) AS t(id INTEGER)
        """)).scalar()
        inventory_items_count = inv_result or 0
    except Exception:
        pass  # Inventory count unavailable, keep as 0

    return templates.TemplateResponse("item_codes.html", {
        "request": request,
        "item_codes": item_codes,
        "search": search,
        "filter_type": filter,
        "inventory_items_count": inventory_items_count
    })


@app.post("/api/item-codes/merge")
async def merge_item_codes(
    wrong_codes: str = Form(...),
    correct_code: str = Form(...),
    correct_description: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Merge wrong item codes into the correct one.
    Updates all invoice items with wrong codes to use the correct code and description.
    """
    from sqlalchemy import text as sql_text

    # Parse wrong codes (comma-separated)
    wrong_code_list = [c.strip() for c in wrong_codes.split(",") if c.strip()]

    if not wrong_code_list:
        raise HTTPException(status_code=400, detail="No wrong codes provided")

    if correct_code in wrong_code_list:
        raise HTTPException(status_code=400, detail="Correct code cannot be in the list of wrong codes")

    # Get the correct description (from existing mapping or use provided)
    if not correct_description:
        result = db.execute(
            sql_text("SELECT canonical_description FROM item_code_mapping WHERE item_code = :code"),
            {"code": correct_code}
        ).fetchone()
        if result:
            correct_description = result[0]
        else:
            # Get from the first wrong code
            result = db.execute(
                sql_text("SELECT canonical_description FROM item_code_mapping WHERE item_code = :code"),
                {"code": wrong_code_list[0]}
            ).fetchone()
            if result:
                correct_description = result[0]
            else:
                raise HTTPException(status_code=400, detail="Could not determine correct description")

    # Update all invoice items with wrong codes
    items_updated = 0
    for wrong_code in wrong_code_list:
        result = db.execute(
            sql_text("""
                UPDATE hub_invoice_items
                SET item_code = :correct_code, item_description = :description
                WHERE item_code = :wrong_code
            """),
            {"correct_code": correct_code, "description": correct_description, "wrong_code": wrong_code}
        )
        items_updated += result.rowcount

    # Delete wrong codes from mapping table
    db.execute(
        sql_text("DELETE FROM item_code_mapping WHERE item_code = ANY(:codes)"),
        {"codes": wrong_code_list}
    )

    # Update or create correct code mapping
    existing = db.execute(
        sql_text("SELECT id, occurrence_count FROM item_code_mapping WHERE item_code = :code"),
        {"code": correct_code}
    ).fetchone()

    if existing:
        db.execute(
            sql_text("""
                UPDATE item_code_mapping
                SET canonical_description = :description,
                    occurrence_count = occurrence_count + :added,
                    is_verified = true,
                    updated_at = NOW()
                WHERE item_code = :code
            """),
            {"description": correct_description, "added": items_updated, "code": correct_code}
        )
    else:
        db.execute(
            sql_text("""
                INSERT INTO item_code_mapping (item_code, canonical_description, occurrence_count, is_verified)
                VALUES (:code, :description, :count, true)
            """),
            {"code": correct_code, "description": correct_description, "count": items_updated}
        )

    # Also update the invoice_item_mapping if description changed
    db.execute(
        sql_text("""
            UPDATE invoice_item_mapping
            SET item_code = :code
            WHERE item_description = :description AND (item_code IS NULL OR item_code != :code)
        """),
        {"code": correct_code, "description": correct_description}
    )

    db.commit()

    return {
        "success": True,
        "items_updated": items_updated,
        "codes_merged": len(wrong_code_list),
        "correct_code": correct_code,
        "correct_description": correct_description
    }


@app.post("/api/item-codes/update")
async def update_item_code(
    item_code: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    """Update the canonical description for an item code"""
    from sqlalchemy import text as sql_text

    # Update item_code_mapping
    db.execute(
        sql_text("""
            UPDATE item_code_mapping
            SET canonical_description = :description, updated_at = NOW()
            WHERE item_code = :code
        """),
        {"description": description, "code": item_code}
    )

    # Update all invoice items with this code
    result = db.execute(
        sql_text("""
            UPDATE hub_invoice_items
            SET item_description = :description
            WHERE item_code = :code
        """),
        {"description": description, "code": item_code}
    )

    db.commit()

    return {
        "success": True,
        "items_updated": result.rowcount,
        "item_code": item_code,
        "description": description
    }


@app.post("/api/item-codes/verify")
async def verify_item_code(
    item_code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Mark an item code as verified (confirmed correct)"""
    from sqlalchemy import text as sql_text

    db.execute(
        sql_text("""
            UPDATE item_code_mapping
            SET is_verified = true, updated_at = NOW()
            WHERE item_code = :code
        """),
        {"code": item_code}
    )

    db.commit()

    return {"success": True, "item_code": item_code}


@app.post("/api/item-codes/fix")
async def fix_item_code(
    wrong_code: str = Form(...),
    correct_code: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Fix an OCR error by changing a wrong item code to the correct one.
    This updates all invoice items with the wrong code to use the correct code.
    Unlike merge, this doesn't require the correct code to already exist.
    """
    from sqlalchemy import text as sql_text

    if wrong_code == correct_code:
        raise HTTPException(status_code=400, detail="Codes must be different")

    # Get the description from the wrong code entry
    wrong_entry = db.execute(
        sql_text("SELECT canonical_description FROM item_code_mapping WHERE item_code = :code"),
        {"code": wrong_code}
    ).fetchone()

    description = wrong_entry[0] if wrong_entry else None

    # Update all invoice items with the wrong code
    result = db.execute(
        sql_text("""
            UPDATE hub_invoice_items
            SET item_code = :correct_code
            WHERE item_code = :wrong_code
        """),
        {"correct_code": correct_code, "wrong_code": wrong_code}
    )
    items_updated = result.rowcount

    # Check if the correct code already exists in mapping table
    existing = db.execute(
        sql_text("SELECT id, occurrence_count FROM item_code_mapping WHERE item_code = :code"),
        {"code": correct_code}
    ).fetchone()

    if existing:
        # Update existing entry's occurrence count
        db.execute(
            sql_text("""
                UPDATE item_code_mapping
                SET occurrence_count = occurrence_count + :added,
                    updated_at = NOW()
                WHERE item_code = :code
            """),
            {"added": items_updated, "code": correct_code}
        )
    else:
        # Create new entry for the correct code
        db.execute(
            sql_text("""
                INSERT INTO item_code_mapping (item_code, canonical_description, occurrence_count, is_verified)
                VALUES (:code, :description, :count, false)
            """),
            {"code": correct_code, "description": description, "count": items_updated}
        )

    # Delete the wrong code from mapping table
    db.execute(
        sql_text("DELETE FROM item_code_mapping WHERE item_code = :code"),
        {"code": wrong_code}
    )

    db.commit()

    return {
        "success": True,
        "items_updated": items_updated,
        "wrong_code": wrong_code,
        "correct_code": correct_code
    }


@app.post("/api/item-codes/add")
async def add_item_code(
    item_description: str = Form(...),
    item_code: str = Form(...),
    new_description: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Add an item code to invoice items that currently have no code.
    This is used when OCR failed to capture the item code from the invoice.
    """
    from sqlalchemy import text as sql_text

    if not item_code.strip():
        raise HTTPException(status_code=400, detail="Item code cannot be empty")

    item_code = item_code.strip()

    # Update all invoice items with this description that have no code
    if new_description and new_description.strip():
        # Also update the description if provided
        result = db.execute(
            sql_text("""
                UPDATE hub_invoice_items
                SET item_code = :item_code,
                    item_description = :new_description
                WHERE item_description = :description
                  AND (item_code IS NULL OR item_code = '')
            """),
            {
                "item_code": item_code,
                "new_description": new_description.strip(),
                "description": item_description
            }
        )
    else:
        result = db.execute(
            sql_text("""
                UPDATE hub_invoice_items
                SET item_code = :item_code
                WHERE item_description = :description
                  AND (item_code IS NULL OR item_code = '')
            """),
            {"item_code": item_code, "description": item_description}
        )

    items_updated = result.rowcount

    # Check if this code already exists in item_code_mapping
    existing = db.execute(
        sql_text("SELECT id FROM item_code_mapping WHERE item_code = :code"),
        {"code": item_code}
    ).fetchone()

    final_description = new_description.strip() if new_description and new_description.strip() else item_description

    if existing:
        # Update existing entry
        db.execute(
            sql_text("""
                UPDATE item_code_mapping
                SET occurrence_count = occurrence_count + :added,
                    updated_at = NOW()
                WHERE item_code = :code
            """),
            {"added": items_updated, "code": item_code}
        )
    else:
        # Create new entry in item_code_mapping
        db.execute(
            sql_text("""
                INSERT INTO item_code_mapping (item_code, canonical_description, occurrence_count, is_verified, created_at, updated_at)
                VALUES (:code, :desc, :count, false, NOW(), NOW())
            """),
            {"code": item_code, "desc": final_description, "count": items_updated}
        )

    db.commit()

    return {
        "success": True,
        "items_updated": items_updated,
        "item_code": item_code,
        "description": final_description
    }


@app.post("/api/item-codes/sync-from-inventory")
async def sync_item_codes_from_inventory(db: Session = Depends(get_db)):
    """
    Sync vendor items from Inventory system to item_code_mapping table.
    This ensures item codes have verified descriptions from the source system.
    """
    from sqlalchemy import text as sql_text

    try:
        # Fetch vendor items from Inventory database
        vendor_items = db.execute(sql_text("""
            SELECT vendor_sku, vendor_product_name, vendor_id
            FROM dblink(
                'dbname=inventory_db user=inventory_user password=inventory_pass host=inventory-db',
                'SELECT vendor_sku, vendor_product_name, vendor_id FROM vendor_items WHERE vendor_sku IS NOT NULL AND vendor_product_name IS NOT NULL'
            ) AS t(vendor_sku VARCHAR, vendor_product_name VARCHAR, vendor_id INTEGER)
        """)).fetchall()

        if not vendor_items:
            return {"success": False, "error": "No vendor items found in Inventory system"}

        imported_count = 0
        updated_count = 0

        for item in vendor_items:
            vendor_sku = item[0].strip() if item[0] else None
            vendor_product_name = item[1].strip() if item[1] else None
            vendor_id = item[2]

            if not vendor_sku or not vendor_product_name:
                continue

            # Check if this item code already exists
            existing = db.execute(
                sql_text("SELECT id, canonical_description FROM item_code_mapping WHERE item_code = :code"),
                {"code": vendor_sku}
            ).fetchone()

            if existing:
                # Update existing entry with verified description if different
                if existing[1] != vendor_product_name:
                    db.execute(
                        sql_text("""
                            UPDATE item_code_mapping
                            SET canonical_description = :desc,
                                vendor_id = :vendor_id,
                                is_verified = true,
                                updated_at = NOW()
                            WHERE item_code = :code
                        """),
                        {"desc": vendor_product_name, "vendor_id": vendor_id, "code": vendor_sku}
                    )
                    updated_count += 1
                else:
                    # Just mark as verified if description matches
                    db.execute(
                        sql_text("""
                            UPDATE item_code_mapping
                            SET is_verified = true, vendor_id = :vendor_id, updated_at = NOW()
                            WHERE item_code = :code
                        """),
                        {"vendor_id": vendor_id, "code": vendor_sku}
                    )
            else:
                # Insert new item code mapping
                db.execute(
                    sql_text("""
                        INSERT INTO item_code_mapping (item_code, canonical_description, vendor_id, is_verified, occurrence_count)
                        VALUES (:code, :desc, :vendor_id, true, 0)
                    """),
                    {"code": vendor_sku, "desc": vendor_product_name, "vendor_id": vendor_id}
                )
                imported_count += 1

        # Also update invoice items that match synced codes
        normalized_count = db.execute(sql_text("""
            UPDATE hub_invoice_items hi
            SET item_description = icm.canonical_description
            FROM item_code_mapping icm
            WHERE hi.item_code = icm.item_code
              AND hi.item_description != icm.canonical_description
              AND icm.is_verified = true
        """)).rowcount

        db.commit()

        return {
            "success": True,
            "imported": imported_count,
            "updated": updated_count,
            "total_synced": len(vendor_items),
            "items_normalized": normalized_count
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


@app.get("/api/item-codes/{item_code}/invoices")
async def get_invoices_by_item_code(item_code: str, db: Session = Depends(get_db)):
    """Get all invoices that contain a specific item code"""
    from sqlalchemy import text as sql_text

    try:
        # Find all invoices containing this item code
        results = db.execute(sql_text("""
            SELECT DISTINCT
                hi.id as invoice_id,
                hi.invoice_number,
                hi.vendor_name,
                hi.invoice_date,
                hi.pdf_path,
                hii.item_description,
                hii.item_code,
                hii.quantity,
                hii.unit_price
            FROM hub_invoices hi
            JOIN hub_invoice_items hii ON hi.id = hii.invoice_id
            WHERE hii.item_code = :item_code
            ORDER BY hi.invoice_date DESC
            LIMIT 50
        """), {"item_code": item_code}).fetchall()

        invoices = []
        for row in results:
            invoices.append({
                "invoice_id": row[0],
                "invoice_number": row[1],
                "vendor_name": row[2],
                "invoice_date": row[3].isoformat() if row[3] else None,
                "pdf_path": row[4],
                "item_description": row[5],
                "item_code": row[6],
                "quantity": float(row[7]) if row[7] else None,
                "unit_price": float(row[8]) if row[8] else None
            })

        return {"success": True, "invoices": invoices, "count": len(invoices)}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
