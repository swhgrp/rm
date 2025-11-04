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

    return templates.TemplateResponse("invoice_detail.html", {
        "request": request,
        "invoice": invoice,
        "items": items,
        "locations": locations
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


# ============================================================================
# UNMAPPED ITEMS REVIEW
# ============================================================================

@app.get("/unmapped-items", response_class=HTMLResponse)
async def unmapped_items(request: Request, db: Session = Depends(get_db)):
    """Review all unmapped invoice items"""

    items = db.query(HubInvoiceItem).filter(
        HubInvoiceItem.is_mapped == False
    ).join(HubInvoice).order_by(HubInvoice.created_at.desc()).all()

    return templates.TemplateResponse("unmapped_items.html", {
        "request": request,
        "items": items
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

    mappings = db.query(CategoryGLMapping).order_by(CategoryGLMapping.inventory_category).all()

    return templates.TemplateResponse("category_mappings.html", {
        "request": request,
        "mappings": mappings
    })


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
