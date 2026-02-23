"""
Order Sheet CRUD + workflow endpoints

Order sheets reference hub vendor items (cross-database). Vendor item data
(name, sku, vendor, category, uom) is snapshotted from the template at
creation time so historical records remain accurate.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import logging

from restaurant_inventory.core.deps import (
    get_db, get_current_user, filter_by_user_locations, get_user_location_ids
)
from restaurant_inventory.models.order_sheet_template import OrderSheetTemplate, OrderSheetTemplateItem
from restaurant_inventory.models.order_sheet import OrderSheet, OrderSheetItem, OrderSheetStatus
from restaurant_inventory.models.user import User, user_locations
from restaurant_inventory.schemas.order_sheet import (
    OrderSheetCreate,
    OrderSheetUpdate,
    OrderSheetResponse,
    OrderSheetItemResponse,
    OrderSheetSendRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="src/restaurant_inventory/templates")


def _build_sheet_response(sheet):
    """Build response dict from an OrderSheet with loaded relationships."""
    items = []
    for item in sheet.items:
        items.append(OrderSheetItemResponse(
            id=item.id,
            order_sheet_id=item.order_sheet_id,
            hub_vendor_item_id=item.hub_vendor_item_id,
            par_level=item.par_level,
            on_hand=item.on_hand,
            to_order=item.to_order,
            unit_abbr=item.unit_abbr,
            notes=item.notes,
            item_name=item.item_name,
            vendor_sku=item.vendor_sku,
            vendor_name=item.vendor_name,
            item_category=item.category
        ))

    # Sort by category then item name for display
    items.sort(key=lambda x: (x.item_category or '', x.item_name or ''))

    return OrderSheetResponse(
        id=sheet.id,
        template_id=sheet.template_id,
        location_id=sheet.location_id,
        name=sheet.name,
        status=sheet.status.value if sheet.status else 'DRAFT',
        notes=sheet.notes,
        created_by=sheet.created_by,
        created_at=sheet.created_at,
        completed_at=sheet.completed_at,
        sent_to_emails=sheet.sent_to_emails,
        sent_at=sheet.sent_at,
        template_name=sheet.template.name if sheet.template else None,
        location_name=sheet.location.name if sheet.location else None,
        created_by_name=sheet.created_by_user.full_name if sheet.created_by_user else None,
        total_items=len(items),
        items_entered=sum(1 for i in items if i.on_hand is not None),
        total_to_order=sum(1 for i in items if i.to_order and i.to_order > 0),
        items=items
    )


def _load_sheet(db: Session, sheet_id: int):
    """Load an order sheet with all relationships eagerly loaded."""
    return db.query(OrderSheet).options(
        joinedload(OrderSheet.template),
        joinedload(OrderSheet.location),
        joinedload(OrderSheet.created_by_user),
        joinedload(OrderSheet.items)
    ).filter(OrderSheet.id == sheet_id).first()


@router.get("/", response_model=List[OrderSheetResponse])
async def get_order_sheets(
    location_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all order sheets, filtered by user's locations"""
    query = db.query(OrderSheet).options(
        joinedload(OrderSheet.template),
        joinedload(OrderSheet.location),
        joinedload(OrderSheet.created_by_user),
        joinedload(OrderSheet.items)
    )

    query = filter_by_user_locations(query, OrderSheet.location_id, current_user)

    if location_id:
        query = query.filter(OrderSheet.location_id == location_id)

    if status:
        try:
            status_enum = OrderSheetStatus(status.upper())
            query = query.filter(OrderSheet.status == status_enum)
        except ValueError:
            pass

    query = query.order_by(OrderSheet.created_at.desc()).limit(limit)
    sheets = query.all()

    return [_build_sheet_response(s) for s in sheets]


@router.get("/{sheet_id}", response_model=OrderSheetResponse)
async def get_order_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific order sheet with items"""
    sheet = _load_sheet(db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    return _build_sheet_response(sheet)


@router.post("/", response_model=OrderSheetResponse)
async def create_order_sheet(
    data: OrderSheetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new order sheet from a template (snapshots vendor item data)"""

    # Load template with items
    template = db.query(OrderSheetTemplate).options(
        joinedload(OrderSheetTemplate.items)
    ).filter(OrderSheetTemplate.id == data.template_id).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Template is inactive")

    # Verify user has access to this location
    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and template.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Create order sheet
    sheet = OrderSheet(
        template_id=template.id,
        location_id=template.location_id,
        name=data.name or f"{template.name} - {datetime.now().strftime('%m/%d/%Y')}",
        status=OrderSheetStatus.DRAFT,
        notes=data.notes,
        created_by=current_user.id
    )
    db.add(sheet)
    db.flush()

    # Snapshot items from template (all vendor item data is already denormalized on template items)
    for t_item in sorted(template.items, key=lambda x: x.sort_order):
        sheet_item = OrderSheetItem(
            order_sheet_id=sheet.id,
            hub_vendor_item_id=t_item.hub_vendor_item_id,
            par_level=t_item.par_level,
            unit_abbr=t_item.unit_abbr,
            item_name=t_item.item_name,
            vendor_sku=t_item.vendor_sku,
            vendor_name=t_item.vendor_name,
            category=t_item.category,
            on_hand=None,
            to_order=None
        )
        db.add(sheet_item)

    db.commit()

    sheet = _load_sheet(db, sheet.id)
    return _build_sheet_response(sheet)


@router.put("/{sheet_id}", response_model=OrderSheetResponse)
async def update_order_sheet(
    sheet_id: int,
    data: OrderSheetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an order sheet (save on-hand values, notes)"""

    sheet = _load_sheet(db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    if sheet.status != OrderSheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft order sheets can be updated")

    if data.name is not None:
        sheet.name = data.name
    if data.notes is not None:
        sheet.notes = data.notes

    # Update items
    if data.items:
        item_map = {item.id: item for item in sheet.items}
        for item_update in data.items:
            sheet_item = item_map.get(item_update.id)
            if not sheet_item:
                continue

            if item_update.on_hand is not None:
                sheet_item.on_hand = item_update.on_hand

                # Auto-calculate to_order if not explicitly provided
                if item_update.to_order is not None:
                    sheet_item.to_order = item_update.to_order
                elif sheet_item.par_level is not None:
                    calculated = sheet_item.par_level - item_update.on_hand
                    sheet_item.to_order = max(calculated, 0)

            elif item_update.to_order is not None:
                # Manual override of to_order without changing on_hand
                sheet_item.to_order = item_update.to_order

            if item_update.notes is not None:
                sheet_item.notes = item_update.notes

    db.commit()

    sheet = _load_sheet(db, sheet.id)
    return _build_sheet_response(sheet)


@router.post("/{sheet_id}/complete")
async def complete_order_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an order sheet as completed and auto-send to location users"""
    from restaurant_inventory.services.email import EmailService

    sheet = _load_sheet(db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    if sheet.status != OrderSheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft order sheets can be completed")

    sheet.status = OrderSheetStatus.COMPLETED
    sheet.completed_at = datetime.utcnow()
    db.commit()

    # Auto-send email to users assigned to this location + admins
    sheet = _load_sheet(db, sheet.id)
    response = _build_sheet_response(sheet)

    location_users = db.query(User).join(
        user_locations, User.id == user_locations.c.user_id
    ).filter(
        user_locations.c.location_id == sheet.location_id,
        User.is_active == True
    ).all()
    admin_users = db.query(User).filter(
        User.role == "Admin", User.is_active == True
    ).all()
    # Combine and deduplicate
    all_users = {u.id: u for u in location_users}
    for u in admin_users:
        all_users[u.id] = u
    emails = [u.email for u in all_users.values() if u.email]

    sent_count = 0
    email_error = None
    if emails:
        try:
            html_content = _build_order_sheet_email_html(response)
            location_name = response.location_name or ''
            template_name = response.template_name or ''
            order_date = response.created_at.strftime('%m/%d/%Y') if response.created_at else ''
            subject = f"Order Sheet: {template_name} - {location_name} ({order_date})"

            for email in emails:
                try:
                    success = EmailService.send_email(
                        to_email=email.strip(),
                        subject=subject,
                        html_content=html_content
                    )
                    if success:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to {email}: {e}")

            if sent_count > 0:
                sheet.status = OrderSheetStatus.SENT
                sheet.sent_to_emails = ', '.join(emails)
                sheet.sent_at = datetime.utcnow()
                db.commit()
                sheet = _load_sheet(db, sheet.id)
        except Exception as e:
            logger.error(f"Email sending error: {e}")
            email_error = str(e)

    result = _build_sheet_response(sheet)
    message = "Order sheet completed"
    if sent_count:
        message += f" and sent to {sent_count} recipient(s)"
    elif email_error:
        message += f" (email failed: {email_error})"
    elif emails:
        message += " (email delivery failed)"

    return {
        "sheet": result.model_dump(),
        "message": message
    }


def _build_order_sheet_email_html(response):
    """Build the HTML email body for an order sheet."""
    # Group items by category
    categories = {}
    for item in response.items:
        cat = item.item_category or 'Other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    # Build HTML table rows
    table_rows = ""
    for cat_name in sorted(categories.keys()):
        table_rows += f'<tr><td colspan="5" style="background-color:#455A64;color:white;font-weight:bold;padding:8px;">{cat_name}</td></tr>'
        for item in categories[cat_name]:
            to_order_val = float(item.to_order) if item.to_order else 0
            row_style = 'font-weight:bold;' if to_order_val > 0 else ''
            vendor_line = f'<br><span style="font-size:11px;color:#666;">{item.vendor_name}</span>' if item.vendor_name else ''
            notes_val = item.notes or ''
            table_rows += f"""<tr style="{row_style}">
                <td style="padding:6px 8px;border-bottom:1px solid #ddd;">{item.item_name or ''}{vendor_line}</td>
                <td style="padding:6px 8px;border-bottom:1px solid #ddd;text-align:center;">{item.par_level or ''}</td>
                <td style="padding:6px 8px;border-bottom:1px solid #ddd;text-align:center;">{item.on_hand or ''}</td>
                <td style="padding:6px 8px;border-bottom:1px solid #ddd;text-align:center;">{item.to_order or ''}</td>
                <td style="padding:6px 8px;border-bottom:1px solid #ddd;">{notes_val}</td>
            </tr>"""

    location_name = response.location_name or ''
    template_name = response.template_name or ''
    created_by_name = response.created_by_name or ''
    order_date = response.created_at.strftime('%m/%d/%Y') if response.created_at else ''
    notes_html = f'<p><strong>Notes:</strong> {response.notes}</p>' if response.notes else ''

    return f"""<!DOCTYPE html>
<html>
<head><style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
    .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
    .header {{ background-color: #455A64; color: white; padding: 20px; text-align: center; }}
    .content {{ background-color: white; padding: 20px; }}
    .meta {{ background-color: #f5f5f5; padding: 15px; margin: 15px 0; border-radius: 5px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
    th {{ background-color: #ECEFF1; padding: 8px; text-align: left; border-bottom: 2px solid #B0BEC5; }}
    .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #666; }}
    .summary {{ background-color: #e7f3ff; padding: 10px 15px; border-radius: 5px; margin: 15px 0; }}
</style></head>
<body>
    <div class="container">
        <div class="header">
            <h1>SW Hospitality Group</h1>
            <p>Order Sheet</p>
        </div>
        <div class="content">
            <div class="meta">
                <strong>Location:</strong> {location_name}<br>
                <strong>Template:</strong> {template_name}<br>
                <strong>Date:</strong> {order_date}<br>
                <strong>Created By:</strong> {created_by_name}
            </div>
            <div class="summary">
                <strong>Items to Order:</strong> {response.total_to_order} of {response.total_items} items
            </div>
            {notes_html}
            <table>
                <thead>
                    <tr>
                        <th>Item</th>
                        <th style="text-align:center;">Par</th>
                        <th style="text-align:center;">On Hand</th>
                        <th style="text-align:center;">To Order</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
        <div class="footer">
            <p>&copy; SW Hospitality Group. All rights reserved.</p>
        </div>
    </div>
</body>
</html>"""


@router.post("/{sheet_id}/send")
async def send_order_sheet(
    sheet_id: int,
    data: OrderSheetSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Email a completed order sheet to specified recipients"""
    from restaurant_inventory.services.email import EmailService

    sheet = _load_sheet(db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    if sheet.status == OrderSheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Complete the order sheet before sending")

    if not data.emails:
        raise HTTPException(status_code=400, detail="At least one email address is required")

    response = _build_sheet_response(sheet)
    html_content = _build_order_sheet_email_html(response)

    location_name = response.location_name or ''
    template_name = response.template_name or ''
    order_date = response.created_at.strftime('%m/%d/%Y') if response.created_at else ''
    subject = f"Order Sheet: {template_name} - {location_name} ({order_date})"

    # Send to each recipient
    sent = []
    failed = []
    for email in data.emails:
        try:
            success = EmailService.send_email(
                to_email=email.strip(),
                subject=subject,
                html_content=html_content
            )
            if success:
                sent.append(email.strip())
            else:
                failed.append(email.strip())
        except Exception as e:
            logger.error(f"Failed to send to {email}: {e}")
            failed.append(email.strip())

    # Update sheet
    sheet.status = OrderSheetStatus.SENT
    sheet.sent_to_emails = ', '.join(data.emails)
    sheet.sent_at = datetime.utcnow()
    db.commit()

    result = {"message": f"Order sheet sent to {len(sent)} recipient(s)"}
    if failed:
        result["message"] += f" ({len(failed)} failed)"
        result["failed"] = failed
    return result


@router.get("/{sheet_id}/print", response_class=HTMLResponse)
async def print_order_sheet(
    request: Request,
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Printable view of an order sheet"""

    sheet = _load_sheet(db, sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    response = _build_sheet_response(sheet)

    # Group items by category
    categories = {}
    for item in response.items:
        cat = item.item_category or 'Other'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return templates.TemplateResponse("order_sheet_print.html", {
        "request": request,
        "sheet": response,
        "categories": categories,
        "sorted_categories": sorted(categories.keys())
    })


@router.get("/{sheet_id}/location-emails")
async def get_location_emails(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get emails of users assigned to this order sheet's location"""

    sheet = db.query(OrderSheet).filter(OrderSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    # Get all active users assigned to this location + admins
    location_users = db.query(User).join(
        user_locations, User.id == user_locations.c.user_id
    ).filter(
        user_locations.c.location_id == sheet.location_id,
        User.is_active == True
    ).all()
    admin_users = db.query(User).filter(
        User.role == "Admin", User.is_active == True
    ).all()
    # Combine and deduplicate
    all_users = {u.id: u for u in location_users}
    for u in admin_users:
        all_users[u.id] = u

    return {
        "emails": [
            {"email": u.email, "name": u.full_name}
            for u in all_users.values() if u.email
        ]
    }


@router.delete("/{sheet_id}")
async def delete_order_sheet(
    sheet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a draft order sheet"""

    sheet = db.query(OrderSheet).filter(OrderSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Order sheet not found")

    location_ids = get_user_location_ids(current_user, db)
    if location_ids is not None and sheet.location_id not in location_ids:
        raise HTTPException(status_code=403, detail="No access to this location")

    if sheet.status != OrderSheetStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft order sheets can be deleted")

    db.delete(sheet)
    db.commit()

    return {"message": "Order sheet deleted successfully"}
