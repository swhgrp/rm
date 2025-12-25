"""
Invoice API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, or_
from typing import List, Optional
from datetime import datetime
import os
import shutil
from pathlib import Path

from restaurant_inventory.core.deps import get_db, get_current_user, filter_by_user_locations
from restaurant_inventory.core.audit import log_audit_event
from restaurant_inventory.models import User, Invoice, InvoiceItem, Vendor, Location, MasterItem, VendorItem, InvoiceStatus
from restaurant_inventory.schemas.invoice import (
    InvoiceCreate, InvoiceUpdate, InvoiceInDB, InvoiceWithDetails, InvoiceList,
    InvoiceItemCreate, InvoiceItemUpdate, InvoiceItemInDB,
    InvoiceParseRequest, InvoiceParseResponse, InvoiceApproveRequest, InvoiceRejectRequest
)

router = APIRouter()

# Upload directory
UPLOAD_DIR = Path("/app/uploads/invoices")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.get("/", response_model=List[InvoiceList])
def list_invoices(
    skip: int = 0,
    limit: int = 100,
    location_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    status: Optional[InvoiceStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all invoices with optional filtering (filtered by user's assigned locations)"""
    query = db.query(Invoice).options(
        joinedload(Invoice.vendor),
        joinedload(Invoice.location),
        joinedload(Invoice.uploaded_by)
    )

    # Apply user location filtering FIRST
    query = filter_by_user_locations(query, Invoice.location_id, current_user)

    # Apply filters
    if location_id:
        query = query.filter(Invoice.location_id == location_id)
    if vendor_id:
        query = query.filter(Invoice.vendor_id == vendor_id)
    if status:
        query = query.filter(Invoice.status == status)
    if search:
        query = query.filter(
            or_(
                Invoice.invoice_number.ilike(f"%{search}%"),
                Invoice.filename.ilike(f"%{search}%")
            )
        )

    query = query.order_by(desc(Invoice.uploaded_at))
    invoices = query.offset(skip).limit(limit).all()

    # Format response
    result = []
    for invoice in invoices:
        result.append(InvoiceList(
            id=invoice.id,
            filename=invoice.filename,
            vendor_id=invoice.vendor_id,
            vendor_name=invoice.vendor.name if invoice.vendor else None,
            location_id=invoice.location_id,
            location_name=invoice.location.name if invoice.location else None,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            total=invoice.total,
            status=invoice.status,
            uploaded_at=invoice.uploaded_at,
            uploaded_by_name=invoice.uploaded_by.full_name if invoice.uploaded_by else None
        ))

    return result


@router.get("/{invoice_id}", response_model=InvoiceWithDetails)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get invoice details by ID (only if user has access to its location)"""
    query = db.query(Invoice).options(
        joinedload(Invoice.vendor),
        joinedload(Invoice.location),
        joinedload(Invoice.uploaded_by),
        joinedload(Invoice.reviewed_by),
        joinedload(Invoice.approved_by),
        joinedload(Invoice.items).joinedload(InvoiceItem.master_item),
        joinedload(Invoice.items).joinedload(InvoiceItem.vendor_item).joinedload(VendorItem.purchase_unit),
        joinedload(Invoice.items).joinedload(InvoiceItem.unit_of_measure)
    ).filter(Invoice.id == invoice_id)

    # Apply user location filtering
    query = filter_by_user_locations(query, Invoice.location_id, current_user)
    invoice = query.first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Build response with related data
    invoice_dict = InvoiceInDB.from_orm(invoice).dict()
    invoice_dict["vendor_name"] = invoice.vendor.name if invoice.vendor else None
    invoice_dict["location_name"] = invoice.location.name if invoice.location else None
    invoice_dict["uploaded_by_name"] = invoice.uploaded_by.full_name if invoice.uploaded_by else None
    invoice_dict["reviewed_by_name"] = invoice.reviewed_by.full_name if invoice.reviewed_by else None
    invoice_dict["approved_by_name"] = invoice.approved_by.full_name if invoice.approved_by else None

    return InvoiceWithDetails(**invoice_dict)


@router.post("/upload", response_model=InvoiceInDB)
async def upload_invoice(
    file: UploadFile = File(...),
    location_id: Optional[int] = Form(None),
    vendor_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload an invoice file (PDF or image) - location and vendor will be extracted by AI during parsing"""

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Validate location if provided
    if location_id:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")

    # Validate vendor if provided
    if vendor_id:
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Create invoice record
    invoice = Invoice(
        filename=file.filename,
        file_path=str(file_path),
        file_type=file_ext.lstrip('.'),
        vendor_id=vendor_id,
        location_id=location_id,
        status=InvoiceStatus.UPLOADED,
        uploaded_by_id=current_user.id
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    # Log action
    log_audit_event(
        db=db,
        user=current_user,
        action="invoice_upload",
        entity_type="invoice",
        entity_id=invoice.id,
        changes={"filename": file.filename, "location_id": location_id}
    )

    return InvoiceInDB.from_orm(invoice)


@router.get("/{invoice_id}/download")
def download_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download the original invoice file"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not os.path.exists(invoice.file_path):
        raise HTTPException(status_code=404, detail="Invoice file not found on disk")

    return FileResponse(
        path=invoice.file_path,
        filename=invoice.filename,
        media_type="application/octet-stream"
    )


@router.put("/{invoice_id}", response_model=InvoiceInDB)
def update_invoice(
    invoice_id: int,
    invoice_update: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update invoice details"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Track changes for audit
    changes = {}
    update_data = invoice_update.dict(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(invoice, field):
            old_value = getattr(invoice, field)
            if old_value != value:
                changes[field] = {"old": old_value, "new": value}
                setattr(invoice, field, value)

    if changes:
        db.commit()
        db.refresh(invoice)

        log_audit_event(
            db=db,
            user=current_user,
            action="invoice_update",
            entity_type="invoice",
            entity_id=invoice.id,
            changes=changes
        )

    return InvoiceInDB.from_orm(invoice)


@router.post("/{invoice_id}/items", response_model=InvoiceItemInDB)
def add_invoice_item(
    invoice_id: int,
    item: InvoiceItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a line item to an invoice"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice_item = InvoiceItem(
        invoice_id=invoice_id,
        **item.dict()
    )

    db.add(invoice_item)
    db.commit()
    db.refresh(invoice_item)

    return InvoiceItemInDB.from_orm(invoice_item)


@router.put("/items/{item_id}", response_model=InvoiceItemInDB)
@router.patch("/items/{item_id}", response_model=InvoiceItemInDB)
def update_invoice_item(
    item_id: int,
    item_update: InvoiceItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an invoice line item"""
    item = db.query(InvoiceItem).filter(InvoiceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Invoice item not found")

    update_data = item_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    # If manually mapped to vendor item or master item, record who did it
    if ("vendor_item_id" in update_data or "master_item_id" in update_data) and item.mapping_method != "auto":
        item.mapping_method = "manual"
        item.mapped_by_id = current_user.id
        item.mapped_at = datetime.now()

    # If vendor_item_id is set, automatically set master_item_id from vendor item
    # and update the vendor item's unit_price with the latest price
    if "vendor_item_id" in update_data and update_data["vendor_item_id"]:
        from restaurant_inventory.models import VendorItem
        vendor_item = db.query(VendorItem).filter(VendorItem.id == update_data["vendor_item_id"]).first()
        if vendor_item:
            item.master_item_id = vendor_item.master_item_id

            # Update vendor item's last price with the current invoice line price
            if item.unit_price is not None:
                vendor_item.last_price = vendor_item.unit_price  # Save previous price
                vendor_item.unit_price = item.unit_price  # Update to latest price

    db.commit()
    db.refresh(item)

    return InvoiceItemInDB.from_orm(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an invoice line item"""
    item = db.query(InvoiceItem).filter(InvoiceItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Invoice item not found")

    db.delete(item)
    db.commit()

    return None


@router.post("/{invoice_id}/review")
def mark_as_reviewed(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark invoice as reviewed"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status not in [InvoiceStatus.PARSED, InvoiceStatus.UPLOADED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot review invoice with status {invoice.status}"
        )

    invoice.status = InvoiceStatus.REVIEWED
    invoice.reviewed_by_id = current_user.id
    invoice.reviewed_at = datetime.now()

    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="invoice_review",
        entity_type="invoice",
        entity_id=invoice.id,
        changes={"status": InvoiceStatus.REVIEWED}
    )

    return {"message": "Invoice marked as reviewed", "invoice_id": invoice_id}


@router.post("/{invoice_id}/parse", response_model=InvoiceParseResponse)
def parse_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Parse invoice using AI (OpenAI Vision API)"""
    from restaurant_inventory.core.invoice_parser import InvoiceParser
    import traceback

    try:
        parser = InvoiceParser()
        result = parser.parse_and_save(invoice_id, db)

        print(f"Parse result: {result}")

        log_audit_event(
            db=db,
            user=current_user,
            action="invoice_parse",
            entity_type="invoice",
            entity_id=invoice_id,
            changes={"result": result.get("message")}
        )

        # If parsing failed, raise an HTTPException with the error details
        if not result.get("success"):
            error_msg = result.get("error", result.get("message", "Unknown error"))
            print(f"Parsing failed with error: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

        return InvoiceParseResponse(**result)

    except ValueError as e:
        print(f"ValueError in parse_invoice: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"Exception in parse_invoice: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.post("/{invoice_id}/approve")
def approve_invoice(
    invoice_id: int,
    approve_request: InvoiceApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Approve invoice and update inventory costs"""
    from restaurant_inventory.models import Inventory
    from decimal import Decimal
    import traceback

    try:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        if invoice.status in [InvoiceStatus.APPROVED, InvoiceStatus.REJECTED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve invoice with status {invoice.status.value}"
            )

        # Update master item costs from invoice
        items_updated = 0
        for line_item in invoice.items:
            if line_item.master_item_id:
                master_item = db.query(MasterItem).filter(
                    MasterItem.id == line_item.master_item_id
                ).first()

                if master_item:
                    # Update cost
                    master_item.cost = line_item.unit_price
                    items_updated += 1

                    # Update inventory quantities if this is a purchase
                    inventory_records = db.query(Inventory).filter(
                        Inventory.master_item_id == master_item.id,
                        Inventory.location_id == invoice.location_id
                    ).all()

                    for inv_record in inventory_records:
                        inv_record.current_quantity += Decimal(str(line_item.quantity))

        # Mark invoice as approved
        invoice.status = InvoiceStatus.APPROVED
        invoice.approved_by_id = current_user.id
        invoice.approved_at = datetime.utcnow()
        if approve_request.notes:
            invoice.notes = (invoice.notes or "") + f"\n[Approved] {approve_request.notes}"

        db.commit()

        try:
            log_audit_event(
                db=db,
                user=current_user,
                action="invoice_approve",
                entity_type="invoice",
                entity_id=invoice.id,
                changes={"status": "APPROVED", "items_updated": items_updated}
            )
        except Exception as e:
            # Don't fail if audit logging fails
            print(f"Audit logging error: {e}")

        return {
            "message": "Invoice approved and inventory updated",
            "invoice_id": invoice_id,
            "items_updated": items_updated
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        print(f"Error approving invoice {invoice_id}: {error_msg}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error approving invoice: {error_msg}"
        )


@router.post("/{invoice_id}/mark-reviewed")
def mark_invoice_reviewed(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an invoice as reviewed"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in [InvoiceStatus.APPROVED, InvoiceStatus.REJECTED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark invoice as reviewed - already {invoice.status.value}"
        )

    invoice.status = InvoiceStatus.REVIEWED
    invoice.reviewed_by_id = current_user.id
    invoice.reviewed_at = datetime.utcnow()

    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="invoice_review",
        entity_type="invoice",
        entity_id=invoice.id,
        changes={"status": "REVIEWED"}
    )

    return {
        "message": "Invoice marked as reviewed",
        "invoice_id": invoice_id,
        "status": "REVIEWED"
    }


@router.post("/{invoice_id}/reject")
def reject_invoice(
    invoice_id: int,
    reject_request: InvoiceRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reject an invoice"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Cannot reject an already approved invoice")

    invoice.status = InvoiceStatus.REJECTED
    invoice.notes = (invoice.notes or "") + f"\n[Rejected] {reject_request.reason}"

    db.commit()

    try:
        log_audit_event(
            db=db,
            user=current_user,
            action="invoice_reject",
            entity_type="invoice",
            entity_id=invoice.id,
            changes={"status": "REJECTED", "reason": reject_request.reason}
        )
    except Exception as e:
        print(f"Audit logging error: {e}")

    return {"message": "Invoice rejected", "invoice_id": invoice_id}


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an invoice and its file"""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Delete file if it exists
    if os.path.exists(invoice.file_path):
        try:
            os.remove(invoice.file_path)
        except Exception as e:
            print(f"Failed to delete file: {e}")

    # Delete database record (cascade will handle items)
    db.delete(invoice)
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="invoice_delete",
        entity_type="invoice",
        entity_id=invoice_id,
        changes={"filename": invoice.filename}
    )

    return None


@router.post("/from-hub")
def receive_invoice_from_hub(
    invoice_data: dict,
    db: Session = Depends(get_db)
):
    """
    Receive invoice from Integration Hub

    This endpoint is called by the Integration Hub when an invoice is fully mapped
    and ready to be created in the inventory system.

    Expected payload:
    {
        "vendor_name": "US Foods",
        "invoice_number": "INV-12345",
        "invoice_date": "2025-10-19",
        "due_date": "2025-11-19",
        "total_amount": 1234.56,
        "source": "hub",
        "hub_invoice_id": 123,
        "items": [
            {
                "inventory_item_id": 45,
                "description": "Chicken Breast",
                "quantity": 25.0,
                "unit_of_measure": "LB",
                "unit_price": 3.50,
                "line_total": 87.50,
                "category": "poultry"
            }
        ]
    }
    """
    try:
        # Extract invoice data
        vendor_name = invoice_data.get("vendor_name")
        invoice_number = invoice_data.get("invoice_number")
        invoice_date_str = invoice_data.get("invoice_date")
        due_date_str = invoice_data.get("due_date")
        total_amount = invoice_data.get("total_amount")
        hub_invoice_id = invoice_data.get("hub_invoice_id")
        items_data = invoice_data.get("items", [])

        # Parse dates
        invoice_date = datetime.fromisoformat(invoice_date_str) if invoice_date_str else None
        due_date = datetime.fromisoformat(due_date_str) if due_date_str else None

        # Check for duplicate invoice (same invoice_number and vendor)
        if invoice_number and vendor_name:
            # First find the vendor
            existing_vendor = db.query(Vendor).filter(Vendor.name == vendor_name).first()
            if existing_vendor:
                existing_invoice = db.query(Invoice).filter(
                    Invoice.invoice_number == invoice_number,
                    Invoice.vendor_id == existing_vendor.id
                ).first()
                if existing_invoice:
                    return {
                        "status": "duplicate",
                        "message": f"Invoice {invoice_number} from {vendor_name} already exists in inventory (ID: {existing_invoice.id})",
                        "existing_invoice_id": existing_invoice.id
                    }

        # Find or create vendor
        vendor = db.query(Vendor).filter(Vendor.name == vendor_name).first()
        if not vendor:
            # Create new vendor
            vendor = Vendor(
                name=vendor_name,
                contact_name="",
                email="",
                phone="",
                address="",
                is_active=True
            )
            db.add(vendor)
            db.flush()  # Get vendor ID

        # Get location_id from hub data, default to finding first active location
        location_id = invoice_data.get("location_id")
        if not location_id:
            from restaurant_inventory.models.location import Location
            default_location = db.query(Location).filter(Location.is_active == True).first()
            location_id = default_location.id if default_location else None

        # Create invoice record
        # Note: uploaded_by_id and approved_by_id are nullable for hub-imported invoices
        invoice = Invoice(
            filename=f"hub_{hub_invoice_id}_{invoice_number}.pdf",
            file_path=f"/app/uploads/invoices/hub_{hub_invoice_id}_{invoice_number}.pdf",
            file_type="pdf",
            vendor_id=vendor.id,
            location_id=location_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            subtotal=total_amount,
            tax=0.0,
            total=total_amount,
            status=InvoiceStatus.APPROVED,  # Auto-approve from hub
            notes=f"Received from Integration Hub (hub_invoice_id: {hub_invoice_id})",
            uploaded_by_id=None,  # No user for hub imports
            approved_by_id=None,  # No user for hub imports
            uploaded_at=datetime.utcnow(),
            approved_at=datetime.utcnow()
        )

        db.add(invoice)
        db.flush()  # Get invoice ID

        # Create invoice items
        for item_data in items_data:
            # Note: Hub sends "inventory_item_id" which is actually the VENDOR ITEM ID
            # (the ID from the vendor_items table, not master_items)
            hub_item_id = item_data.get("inventory_item_id")
            item_code = item_data.get("item_code")  # Vendor's item code from invoice
            description = item_data.get("description")
            quantity = item_data.get("quantity")
            unit_of_measure = item_data.get("unit_of_measure")
            unit_price = item_data.get("unit_price")
            line_total = item_data.get("line_total")
            category = item_data.get("category")

            # Look up vendor item to get the master_item_id and other details
            valid_vendor_item_id = None
            valid_master_item_id = None
            vendor_sku = item_code  # Default to hub's item_code
            pack_size = None
            purchase_unit_id = None

            if hub_item_id:
                # First try to find as vendor_item_id (correct interpretation)
                vendor_item = db.query(VendorItem).options(
                    joinedload(VendorItem.purchase_unit)
                ).filter(VendorItem.id == hub_item_id).first()
                if vendor_item:
                    valid_vendor_item_id = vendor_item.id
                    valid_master_item_id = vendor_item.master_item_id
                    # Get vendor_sku and pack_size from vendor_item
                    vendor_sku = vendor_item.vendor_sku or item_code
                    pack_size = vendor_item.pack_size
                    purchase_unit_id = vendor_item.purchase_unit_id
                    # Update vendor item's last price
                    vendor_item.unit_price = unit_price
                    # Also update master item's current cost if linked
                    if vendor_item.master_item:
                        vendor_item.master_item.current_cost = unit_price

            # Create invoice item with vendor details
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                description=description,
                quantity=quantity,
                unit=unit_of_measure,
                unit_price=unit_price,
                line_total=line_total,
                vendor_item_id=valid_vendor_item_id,
                master_item_id=valid_master_item_id,
                vendor_sku=vendor_sku,
                pack_size=pack_size,
                unit_of_measure_id=purchase_unit_id,
                mapping_method='hub' if valid_vendor_item_id else None
            )

            db.add(invoice_item)

        db.commit()

        return {
            "success": True,
            "invoice_id": invoice.id,
            "message": f"Invoice {invoice_number} created successfully",
            "items_count": len(items_data)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating invoice from hub: {str(e)}"
        )
