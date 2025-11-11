"""
Integration Hub - FastAPI Application

Central hub for receiving invoices and routing to Inventory and Accounting systems.
Provides mapping UI and auto-send functionality while keeping systems independent.
"""

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import os
from pathlib import Path

from integration_hub.db.database import get_db, engine, Base
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.models.hub_invoice_item import HubInvoiceItem
from integration_hub.models.item_gl_mapping import ItemGLMapping, CategoryGLMapping
from integration_hub.models.vendor import Vendor
from integration_hub.schemas.vendor import VendorCreate, VendorResponse, VendorSyncStatus
from integration_hub.services.inventory_sender import get_inventory_sender
from integration_hub.services.accounting_sender import get_accounting_sender
from integration_hub.services.auto_send import get_auto_send_service
from integration_hub.services.vendor_sync import get_vendor_sync_service
from integration_hub.services.email_scheduler import get_email_scheduler
from integration_hub.api import auth as auth_router
from integration_hub.api import settings as settings_router

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

    # Get unmapped items count
    unmapped_items = db.query(HubInvoiceItem).filter(HubInvoiceItem.is_mapped == False).count()

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
        "unmapped_items": unmapped_items,
        "recent_invoices": recent_invoices,
        "vendors": vendors
    })


# ============================================================================
# INVOICE MANAGEMENT
# ============================================================================

@app.get("/invoices", response_class=HTMLResponse)
async def list_invoices(request: Request, db: Session = Depends(get_db)):
    """List all invoices with filtering"""
    invoices = db.query(HubInvoice).order_by(HubInvoice.created_at.desc()).all()

    # Get vendors for dropdown
    vendors = db.query(Vendor).filter(Vendor.is_active == True).order_by(Vendor.name).all()

    return templates.TemplateResponse("invoices.html", {
        "request": request,
        "invoices": invoices,
        "vendors": vendors
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

    return templates.TemplateResponse("invoice_detail.html", {
        "request": request,
        "invoice": invoice,
        "items": items,
        "locations": locations,
        "vendors": vendors
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


@app.post("/api/invoices/{invoice_id}/parse")
async def parse_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """
    Parse an invoice PDF using OpenAI to extract invoice data and line items
    """
    from integration_hub.services.invoice_parser import get_invoice_parser

    try:
        parser = get_invoice_parser()
        result = parser.parse_and_save(invoice_id, db)
        return result
    except ValueError as e:
        # Configuration error (e.g., missing API key)
        return {
            "success": False,
            "message": f"Configuration error: {str(e)}"
        }
    except Exception as e:
        # Unexpected error
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error parsing invoice {invoice_id}: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Error parsing invoice: {str(e)}"
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
            else:
                invoice.location_id = None

        if "location_name" in data:
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
    # Query returns: (item_description, item_code, count, list of invoice numbers, list of vendors)
    unique_items_query = db.query(
        HubInvoiceItem.item_description,
        HubInvoiceItem.item_code,
        func.count(HubInvoiceItem.id).label('occurrence_count'),
        func.array_agg(distinct(HubInvoice.invoice_number)).label('invoice_numbers'),
        func.array_agg(distinct(HubInvoice.vendor_name)).label('vendor_names')
    ).join(HubInvoice).filter(
        HubInvoiceItem.is_mapped == False
    ).group_by(
        HubInvoiceItem.item_description,
        HubInvoiceItem.item_code
    ).order_by(
        func.count(HubInvoiceItem.id).desc()  # Show most frequent items first
    ).all()

    # Format results for template
    unique_items = []
    for desc, item_code, count, invoice_nums, vendors in unique_items_query:
        unique_items.append({
            'item_description': desc,
            'item_code': item_code,
            'occurrence_count': count,
            'invoice_numbers': invoice_nums if invoice_nums else [],
            'vendor_names': vendors if vendors else []
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

    # Fetch vendor items from Inventory API (not master items - those are just for counts)
    inventory_items = []
    try:
        async with httpx.AsyncClient() as client:
            # Use special /_hub/sync endpoint that doesn't require authentication
            response = await client.get(f"{INVENTORY_API_URL}/vendor-items/_hub/sync", params={"is_active": True, "limit": 5000})
            if response.status_code == 200:
                inventory_items = response.json()
            else:
                logger.warning(f"Failed to fetch vendor items: status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch vendor items from Inventory API: {str(e)}")

    response = templates.TemplateResponse("unmapped_items.html", {
        "request": request,
        "unique_items": unique_items,
        "gl_accounts": gl_accounts,
        "inventory_items": inventory_items
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
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ACCOUNTING_API_URL}/accounts/", params={"is_active": True, "limit": 1000})
            if response.status_code == 200:
                gl_accounts = response.json()
            else:
                logger.warning(f"Failed to fetch GL accounts: status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch GL accounts from Accounting API: {str(e)}")

    # Fetch vendor items from Inventory API
    inventory_items = []
    inventory_items_map = {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{INVENTORY_API_URL}/vendor-items/_hub/sync", params={"is_active": True, "limit": 5000})
            if response.status_code == 200:
                inventory_items = response.json()
                # Create a map of vendor item ID to item details for quick lookup
                for item in inventory_items:
                    inventory_items_map[item['id']] = item
            else:
                logger.warning(f"Failed to fetch vendor items: status {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to fetch vendor items from Inventory API: {str(e)}")

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
            'gl_waste_account': waste_acct
        })

    return templates.TemplateResponse("mapped_items.html", {
        "request": request,
        "unique_items": unique_items,
        "gl_accounts": gl_accounts,
        "inventory_items": inventory_items
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

    return templates.TemplateResponse("category_mappings.html", {
        "request": request,
        "mappings": enriched_mappings,
        "gl_accounts": gl_accounts
    })


@app.get("/api/category-mappings/{category}")
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
        "cogs_account_name": mapping.cogs_account_name
    }


@app.post("/api/category-mappings")
async def create_category_mapping(
    inventory_category: str = Form(...),
    asset_account_name: Optional[str] = Form(None),
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
        mapping.gl_asset_account = gl_asset_account
        mapping.gl_cogs_account = gl_cogs_account
        mapping.gl_waste_account = gl_waste_account
        mapping.is_active = True
    else:
        # Create new
        mapping = CategoryGLMapping(
            inventory_category=inventory_category,
            asset_account_name=asset_account_name,
            gl_asset_account=gl_asset_account,
            gl_cogs_account=gl_cogs_account,
            gl_waste_account=gl_waste_account,
            is_active=True
        )
        db.add(mapping)

    db.commit()

    return RedirectResponse(url="/hub/category-mappings", status_code=303)


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
    """Vendor management page"""
    vendors = db.query(Vendor).order_by(Vendor.name).all()

    return templates.TemplateResponse("vendors.html", {
        "request": request,
        "vendors": vendors
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


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
