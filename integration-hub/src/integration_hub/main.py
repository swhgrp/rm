"""
Integration Hub - FastAPI Application

Central hub for receiving invoices and routing to Inventory and Accounting systems.
Provides mapping UI and auto-send functionality while keeping systems independent.
"""

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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
from integration_hub.api import auth as auth_router

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

# Create static directory if it doesn't exist
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(auth_router.router)


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

    return templates.TemplateResponse("invoice_detail.html", {
        "request": request,
        "invoice": invoice,
        "items": items
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
    display_name: str = Form(...),
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
        mapping.display_name = display_name
        mapping.gl_asset_account = gl_asset_account
        mapping.gl_cogs_account = gl_cogs_account
        mapping.gl_waste_account = gl_waste_account
    else:
        # Create new
        mapping = CategoryGLMapping(
            inventory_category=inventory_category,
            display_name=display_name,
            gl_asset_account=gl_asset_account,
            gl_cogs_account=gl_cogs_account,
            gl_waste_account=gl_waste_account
        )
        db.add(mapping)

    db.commit()

    return RedirectResponse(url="/category-mappings", status_code=303)


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


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
