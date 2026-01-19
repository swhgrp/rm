"""
Website Management System - Main FastAPI Application
"""
from fastapi import FastAPI, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List
from datetime import datetime
import os

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from database import get_db, engine
from models import Base, Site, Menu, MenuCategory, MenuItem, Hours, SpecialHours, Image, Page, PageBlock, FormSubmission, ActivityLog
from schemas import (
    SiteCreate, SiteUpdate, SiteResponse,
    MenuCreate, MenuUpdate, MenuResponse,
    MenuCategoryCreate, MenuCategoryUpdate,
    MenuItemCreate, MenuItemUpdate,
    HoursUpdate, SpecialHoursCreate,
    PageCreate, PageUpdate,
    PageBlockCreate, PageBlockUpdate,
    ReorderRequest
)
from auth import require_auth, get_current_user, User
from config import get_settings

settings = get_settings()

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Website Manager", docs_url="/api/docs", redoc_url=None)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Templates
templates = Jinja2Templates(directory="templates")

# Add custom template globals
def format_time_12h(t):
    """Format time as 12-hour with AM/PM"""
    if t is None:
        return ""
    return t.strftime("%I:%M %p").lstrip("0")

templates.env.globals["format_time_12h"] = format_time_12h
templates.env.globals["now"] = datetime.now


# ============ SSO Authentication ============

@app.get("/api/auth/sso-login")
async def sso_login(token: str):
    """Handle SSO login from Portal - validate token and set cookie"""
    from jose import jwt, JWTError

    try:
        # Decode and validate the token from Portal
        payload = jwt.decode(token, settings.portal_sso_secret, algorithms=["HS256"])

        # Create response with redirect to dashboard
        response = RedirectResponse(url="/websites/", status_code=303)

        # Set the portal_token cookie for subsequent requests
        response.set_cookie(
            key="portal_token",
            value=token,
            httponly=True,
            max_age=1800,  # 30 minutes - matches session timeout
            path="/",
            samesite="lax",
            secure=True  # Always use secure cookies in production
        )

        return response

    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ============ Admin UI Routes ============

@app.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Main dashboard - shows all sites"""
    sites = db.query(Site).order_by(Site.name).all()

    # Get counts for each site
    site_stats = []
    for site in sites:
        menu_count = db.query(Menu).filter(Menu.site_id == site.id).count()
        page_count = db.query(Page).filter(Page.site_id == site.id).count()
        unread_submissions = db.query(FormSubmission).filter(
            FormSubmission.site_id == site.id,
            FormSubmission.is_read == False
        ).count()
        site_stats.append({
            "site": site,
            "menu_count": menu_count,
            "page_count": page_count,
            "unread_submissions": unread_submissions
        })

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "site_stats": site_stats,
        "active_page": "dashboard"
    })


@app.get("/sites/new", response_class=HTMLResponse)
async def admin_site_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Create new site form"""
    return templates.TemplateResponse("admin/sites/edit.html", {
        "request": request,
        "user": user,
        "site": None,
        "is_new": True,
        "active_page": "sites"
    })


@app.get("/sites/{site_id}", response_class=HTMLResponse)
async def admin_site_dashboard(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Site-specific dashboard"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Get recent activity (limited to 5 for dashboard)
    recent_activity = db.query(ActivityLog).filter(
        ActivityLog.site_id == site_id
    ).order_by(ActivityLog.created_at.desc()).limit(5).all()

    # Get total activity count for "View All" link
    total_activity_count = db.query(ActivityLog).filter(
        ActivityLog.site_id == site_id
    ).count()

    # Get counts
    menu_count = db.query(Menu).filter(Menu.site_id == site_id).count()
    page_count = db.query(Page).filter(Page.site_id == site_id).count()
    image_count = db.query(Image).filter(Image.site_id == site_id).count()
    unread_submissions = db.query(FormSubmission).filter(
        FormSubmission.site_id == site_id,
        FormSubmission.is_read == False
    ).count()

    # Get all sites for switcher
    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/sites/dashboard.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "recent_activity": recent_activity,
        "total_activity_count": total_activity_count,
        "menu_count": menu_count,
        "page_count": page_count,
        "image_count": image_count,
        "unread_submissions": unread_submissions,
        "active_page": "dashboard"
    })


@app.get("/sites/{site_id}/activity", response_class=HTMLResponse)
async def admin_site_activity(request: Request, site_id: int, page: int = 1, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """View all activity for a site with pagination"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    per_page = 20
    offset = (page - 1) * per_page

    # Get activity with pagination
    activity = db.query(ActivityLog).filter(
        ActivityLog.site_id == site_id
    ).order_by(ActivityLog.created_at.desc()).offset(offset).limit(per_page).all()

    total_count = db.query(ActivityLog).filter(
        ActivityLog.site_id == site_id
    ).count()

    total_pages = (total_count + per_page - 1) // per_page

    # Get all sites for switcher
    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/sites/activity.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "activity": activity,
        "current_page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "active_page": "activity"
    })


@app.get("/sites/{site_id}/settings", response_class=HTMLResponse)
async def admin_site_settings(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Site settings form"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/sites/edit.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "is_new": False,
        "active_page": "settings"
    })


# ============ Menu Routes ============

@app.get("/sites/{site_id}/menus", response_class=HTMLResponse)
async def admin_menus_list(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """List all menus for site"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    menus = db.query(Menu).filter(Menu.site_id == site_id).order_by(Menu.sort_order).all()

    # Get item counts for each menu
    menu_data = []
    for menu in menus:
        category_count = len(menu.categories)
        item_count = sum(len(cat.items) for cat in menu.categories)
        menu_data.append({
            "menu": menu,
            "category_count": category_count,
            "item_count": item_count
        })

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/menus/list.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "menu_data": menu_data,
        "active_page": "menus"
    })


@app.get("/sites/{site_id}/menus/new", response_class=HTMLResponse)
async def admin_menu_new(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Create new menu form"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/menus/edit.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "menu": None,
        "is_new": True,
        "active_page": "menus"
    })


@app.get("/sites/{site_id}/menus/{menu_id}", response_class=HTMLResponse)
async def admin_menu_edit(request: Request, site_id: int, menu_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Menu editor with categories and items"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    menu = db.query(Menu).options(
        joinedload(Menu.categories).joinedload(MenuCategory.items)
    ).filter(Menu.id == menu_id, Menu.site_id == site_id).first()

    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/menus/edit.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "menu": menu,
        "is_new": False,
        "active_page": "menus"
    })


# ============ Hours Routes ============

@app.get("/sites/{site_id}/hours", response_class=HTMLResponse)
async def admin_hours(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Hours editor"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    hours = db.query(Hours).filter(Hours.site_id == site_id).order_by(Hours.day_of_week).all()
    special_hours = db.query(SpecialHours).filter(
        SpecialHours.site_id == site_id
    ).order_by(SpecialHours.date).all()

    # Create hours dict for easy template access
    hours_dict = {h.day_of_week: h for h in hours}

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/hours/edit.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "hours_dict": hours_dict,
        "special_hours": special_hours,
        "days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "active_page": "hours"
    })


# ============ Images Routes ============

@app.get("/sites/{site_id}/images", response_class=HTMLResponse)
async def admin_images(request: Request, site_id: int, folder: str = None, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Image library"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    query = db.query(Image).filter(Image.site_id == site_id)
    if folder:
        query = query.filter(Image.folder == folder)

    images = query.order_by(Image.created_at.desc()).all()

    # Get folder counts
    folder_counts = db.query(Image.folder, func.count(Image.id)).filter(
        Image.site_id == site_id
    ).group_by(Image.folder).all()

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/images/list.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "images": images,
        "folder_counts": dict(folder_counts),
        "current_folder": folder,
        "active_page": "images"
    })


# ============ Pages Routes ============

@app.get("/sites/{site_id}/pages", response_class=HTMLResponse)
async def admin_pages_list(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """List all pages"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    pages = db.query(Page).filter(Page.site_id == site_id).order_by(Page.nav_order).all()

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/pages/list.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "pages": pages,
        "active_page": "pages"
    })


@app.get("/sites/{site_id}/pages/{page_id}", response_class=HTMLResponse)
async def admin_page_edit(request: Request, site_id: int, page_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Page block editor"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    page = db.query(Page).options(
        joinedload(Page.blocks)
    ).filter(Page.id == page_id, Page.site_id == site_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get menus for menu_embed block
    menus = db.query(Menu).filter(Menu.site_id == site_id, Menu.is_active == True).all()

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/pages/edit.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "page": page,
        "menus": menus,
        "active_page": "pages"
    })


# ============ Submissions Routes ============

@app.get("/sites/{site_id}/submissions", response_class=HTMLResponse)
async def admin_submissions(request: Request, site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Contact form submissions"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    submissions = db.query(FormSubmission).filter(
        FormSubmission.site_id == site_id
    ).order_by(FormSubmission.created_at.desc()).limit(100).all()

    all_sites = db.query(Site).order_by(Site.name).all()

    return templates.TemplateResponse("admin/submissions/list.html", {
        "request": request,
        "user": user,
        "site": site,
        "all_sites": all_sites,
        "submissions": submissions,
        "active_page": "submissions"
    })


# ============ htmx Partial Routes ============

@app.post("/htmx/sites", response_class=HTMLResponse)
async def htmx_create_site(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    domain: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create new site"""
    site = Site(name=name, slug=slug, domain=domain)
    db.add(site)
    db.commit()
    db.refresh(site)

    # Log activity
    log = ActivityLog(
        site_id=site.id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="create",
        entity_type="site",
        entity_id=site.id,
        entity_name=site.name
    )
    db.add(log)
    db.commit()

    # Initialize default hours
    for day in range(7):
        hours = Hours(site_id=site.id, day_of_week=day, is_closed=(day == 0))  # Closed Sundays by default
        db.add(hours)
    db.commit()

    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/websites/sites/{site.id}"}
    )


@app.put("/htmx/sites/{site_id}", response_class=HTMLResponse)
async def htmx_update_site(
    request: Request,
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update site settings"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    form_data = await request.form()

    # Track what changed
    changes = []
    for key, value in form_data.items():
        if hasattr(site, key) and key not in ["id", "created_at"]:
            old_value = getattr(site, key)
            new_value = value if value else None
            if str(old_value) != str(new_value):
                # Format field name nicely
                field_name = key.replace("_", " ").title()
                changes.append(field_name)
            setattr(site, key, new_value)

    site.updated_at = get_now()
    db.commit()

    # Log activity with details
    log = ActivityLog(
        site_id=site.id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="update",
        entity_type="site",
        entity_id=site.id,
        entity_name=site.name,
        details={"changed_fields": changes} if changes else None
    )
    db.add(log)
    db.commit()

    return templates.TemplateResponse("admin/partials/toast.html", {
        "request": request,
        "message": "Site settings saved",
        "type": "success"
    })


@app.post("/htmx/sites/{site_id}/menus", response_class=HTMLResponse)
async def htmx_create_menu(
    request: Request,
    site_id: int,
    name: str = Form(...),
    slug: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create new menu"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Get next sort order
    max_order = db.query(func.max(Menu.sort_order)).filter(Menu.site_id == site_id).scalar() or 0

    menu = Menu(
        site_id=site_id,
        name=name,
        slug=slug,
        sort_order=max_order + 1
    )
    db.add(menu)
    db.commit()
    db.refresh(menu)

    # Log activity
    log = ActivityLog(
        site_id=site_id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="create",
        entity_type="menu",
        entity_id=menu.id,
        entity_name=menu.name
    )
    db.add(log)
    db.commit()

    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/websites/sites/{site_id}/menus/{menu.id}"}
    )


@app.put("/htmx/menus/{menu_id}", response_class=HTMLResponse)
async def htmx_update_menu(
    request: Request,
    menu_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update menu"""
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    form_data = await request.form()
    for key, value in form_data.items():
        if hasattr(menu, key) and key not in ["id", "site_id", "created_at"]:
            if key in ["served_start_time", "served_end_time"] and value:
                # Parse time
                from datetime import time as dt_time
                parts = value.split(":")
                setattr(menu, key, dt_time(int(parts[0]), int(parts[1])))
            elif key == "is_active":
                setattr(menu, key, value == "on" or value == "true")
            else:
                setattr(menu, key, value if value else None)

    menu.updated_at = get_now()
    db.commit()

    return templates.TemplateResponse("admin/partials/toast.html", {
        "request": request,
        "message": "Menu saved",
        "type": "success"
    })


@app.delete("/htmx/menus/{menu_id}", response_class=HTMLResponse)
async def htmx_delete_menu(
    request: Request,
    menu_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete menu"""
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    site_id = menu.site_id

    # Log activity
    log = ActivityLog(
        site_id=site_id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="delete",
        entity_type="menu",
        entity_id=menu.id,
        entity_name=menu.name
    )
    db.add(log)

    db.delete(menu)
    db.commit()

    return HTMLResponse(content="", headers={"HX-Redirect": f"/websites/sites/{site_id}/menus"})


@app.post("/htmx/menus/{menu_id}/categories", response_class=HTMLResponse)
async def htmx_add_category(
    request: Request,
    menu_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Add category, return new row HTML"""
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    # Get next sort order
    max_order = db.query(func.max(MenuCategory.sort_order)).filter(MenuCategory.menu_id == menu_id).scalar() or 0

    category = MenuCategory(
        menu_id=menu_id,
        name="New Category",
        sort_order=max_order + 1
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    return templates.TemplateResponse("admin/menus/partials/category_card.html", {
        "request": request,
        "category": category,
        "site": menu.site
    })


@app.put("/htmx/categories/{category_id}", response_class=HTMLResponse)
async def htmx_update_category(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update category"""
    category = db.query(MenuCategory).filter(MenuCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    form_data = await request.form()
    for key, value in form_data.items():
        if hasattr(category, key) and key not in ["id", "menu_id", "created_at"]:
            setattr(category, key, value if value else None)

    category.updated_at = get_now()
    db.commit()

    return HTMLResponse(content="")  # No content needed for inline update


@app.delete("/htmx/categories/{category_id}", response_class=HTMLResponse)
async def htmx_delete_category(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete category"""
    category = db.query(MenuCategory).filter(MenuCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(category)
    db.commit()

    return HTMLResponse(content="")  # Returns empty, htmx removes the element


@app.post("/htmx/categories/{category_id}/items", response_class=HTMLResponse)
async def htmx_add_item(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Add menu item, return new row HTML"""
    category = db.query(MenuCategory).filter(MenuCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Get next sort order
    max_order = db.query(func.max(MenuItem.sort_order)).filter(MenuItem.category_id == category_id).scalar() or 0

    item = MenuItem(
        category_id=category_id,
        name="New Item",
        sort_order=max_order + 1
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return templates.TemplateResponse("admin/menus/partials/item_row.html", {
        "request": request,
        "item": item
    })


@app.put("/htmx/items/{item_id}", response_class=HTMLResponse)
async def htmx_update_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update menu item"""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    form_data = await request.form()

    # Handle dietary flags as a list
    dietary_flags = []
    for key, value in form_data.items():
        if key.startswith("dietary_"):
            flag_name = key.replace("dietary_", "").replace("_", "-")
            if value == "on" or value == "true":
                dietary_flags.append(flag_name)
        elif hasattr(item, key) and key not in ["id", "category_id", "created_at", "dietary_flags"]:
            if key == "price" and value:
                from decimal import Decimal
                setattr(item, key, Decimal(value))
            elif key in ["is_featured", "is_available"]:
                setattr(item, key, value == "on" or value == "true")
            else:
                setattr(item, key, value if value else None)

    item.dietary_flags = dietary_flags if dietary_flags else None
    item.updated_at = get_now()
    db.commit()

    return HTMLResponse(content="")


@app.delete("/htmx/items/{item_id}", response_class=HTMLResponse)
async def htmx_delete_item(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete menu item"""
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(item)
    db.commit()

    return HTMLResponse(content="")


@app.post("/htmx/menus/{menu_id}/reorder", response_class=HTMLResponse)
async def htmx_reorder_menu(
    request: Request,
    menu_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Reorder categories and items"""
    import json

    form_data = await request.form()
    order_data = json.loads(form_data.get("order", "{}"))

    for cat_id, cat_data in order_data.items():
        category = db.query(MenuCategory).filter(MenuCategory.id == int(cat_id)).first()
        if category and category.menu_id == menu_id:
            category.sort_order = cat_data.get("order", 0)

            for item_data in cat_data.get("items", []):
                item = db.query(MenuItem).filter(MenuItem.id == item_data["id"]).first()
                if item:
                    item.category_id = int(cat_id)  # Allow moving between categories
                    item.sort_order = item_data["order"]

    db.commit()

    return HTMLResponse(content="")


@app.put("/htmx/sites/{site_id}/hours", response_class=HTMLResponse)
async def htmx_update_hours(
    request: Request,
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update all hours for a site"""
    from datetime import time as dt_time

    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    form_data = await request.form()

    for day in range(7):
        hours = db.query(Hours).filter(Hours.site_id == site_id, Hours.day_of_week == day).first()
        if not hours:
            hours = Hours(site_id=site_id, day_of_week=day)
            db.add(hours)

        is_closed = form_data.get(f"closed_{day}") == "on"
        hours.is_closed = is_closed

        if not is_closed:
            open_time = form_data.get(f"open_{day}")
            close_time = form_data.get(f"close_{day}")

            if open_time:
                parts = open_time.split(":")
                hours.open_time = dt_time(int(parts[0]), int(parts[1]))
            if close_time:
                parts = close_time.split(":")
                hours.close_time = dt_time(int(parts[0]), int(parts[1]))

    db.commit()

    return templates.TemplateResponse("admin/partials/toast.html", {
        "request": request,
        "message": "Hours saved",
        "type": "success"
    })


# ============ Page Block htmx Routes ============

@app.post("/htmx/sites/{site_id}/pages", response_class=HTMLResponse)
async def htmx_create_page(
    request: Request,
    site_id: int,
    title: str = Form(...),
    slug: str = Form(...),
    template: str = Form("page"),
    is_published: bool = Form(False),
    is_in_nav: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Create new page"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Get next nav order
    max_order = db.query(func.max(Page.nav_order)).filter(Page.site_id == site_id).scalar() or 0

    page = Page(
        site_id=site_id,
        title=title,
        slug=slug,
        template=template,
        is_published=is_published,
        is_in_nav=is_in_nav,
        nav_order=max_order + 1
    )
    db.add(page)
    db.commit()
    db.refresh(page)

    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/websites/sites/{site_id}/pages/{page.id}"}
    )


@app.put("/htmx/pages/{page_id}", response_class=HTMLResponse)
async def htmx_update_page(
    request: Request,
    page_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update page settings"""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Handle both form data and JSON
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        import json
        body = await request.body()
        data = json.loads(body)
    else:
        form_data = await request.form()
        data = dict(form_data)

    for key, value in data.items():
        if hasattr(page, key) and key not in ["id", "site_id", "created_at"]:
            if key in ["is_published", "is_in_nav"]:
                if isinstance(value, bool):
                    setattr(page, key, value)
                else:
                    setattr(page, key, value == "on" or value == "true" or value == True)
            elif key == "nav_order" and value:
                setattr(page, key, int(value))
            else:
                setattr(page, key, value if value else None)

    page.updated_at = get_now()
    db.commit()

    return HTMLResponse(content="")


@app.delete("/htmx/pages/{page_id}", response_class=HTMLResponse)
async def htmx_delete_page(
    request: Request,
    page_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete page"""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    site_id = page.site_id
    db.delete(page)
    db.commit()

    return HTMLResponse(content="", headers={"HX-Redirect": f"/websites/sites/{site_id}/pages"})


@app.post("/htmx/pages/{page_id}/blocks", response_class=HTMLResponse)
async def htmx_add_block(
    request: Request,
    page_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Add a new block to a page"""
    import json

    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Parse JSON body
    body = await request.body()
    data = json.loads(body)

    block_type = data.get("block_type", "text")
    content = data.get("content", {})

    # Set default content based on block type
    if block_type == "hero" and not content:
        content = {"headline": "", "subheadline": "", "button_text": "", "button_url": ""}
    elif block_type == "text" and not content:
        content = {"heading": "", "body": ""}
    elif block_type == "cta" and not content:
        content = {"title": "", "subtitle": "", "button_text": "", "button_url": "", "bg_color": "#1a1a1a"}
    elif block_type == "hours" and not content:
        content = {"heading": "Hours & Location"}
    elif block_type == "contact_form" and not content:
        content = {}
    elif block_type == "menu_preview" and not content:
        content = {"show_prices": True}
    elif block_type == "map" and not content:
        content = {"embed_url": ""}
    elif block_type == "image" and not content:
        content = {"image_url": "", "alt_text": "", "caption": ""}

    # Get next sort order
    max_order = db.query(func.max(PageBlock.sort_order)).filter(PageBlock.page_id == page_id).scalar() or 0

    block = PageBlock(
        page_id=page_id,
        block_type=block_type,
        content=content,
        sort_order=max_order + 1,
        is_visible=True
    )
    db.add(block)
    db.commit()
    db.refresh(block)

    # Log activity
    log = ActivityLog(
        site_id=page.site_id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="add",
        entity_type="block",
        entity_id=block.id,
        entity_name=page.title,
        details={
            "block_type": block_type.replace("_", " ").title(),
            "description": f"Added {block_type.replace('_', ' ').title()} block to page"
        }
    )
    db.add(log)
    db.commit()

    # Get site for template
    site = db.query(Site).filter(Site.id == page.site_id).first()

    return templates.TemplateResponse("admin/pages/partials/block_card.html", {
        "request": request,
        "block": block,
        "site": site,
        "page": page
    })


@app.put("/htmx/blocks/{block_id}", response_class=HTMLResponse)
async def htmx_update_block(
    request: Request,
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update block settings"""
    block = db.query(PageBlock).filter(PageBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    # Handle both form data and JSON
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        import json
        body = await request.body()
        data = json.loads(body)
    else:
        form_data = await request.form()
        data = dict(form_data)

    for key, value in data.items():
        if key == "is_visible":
            if isinstance(value, bool):
                block.is_visible = value
            else:
                block.is_visible = value == "on" or value == "true" or value == True
        elif key == "content" and isinstance(value, dict):
            block.content = value
        elif hasattr(block, key) and key not in ["id", "page_id", "created_at"]:
            setattr(block, key, value if value else None)

    block.updated_at = get_now()
    db.commit()

    return HTMLResponse(content="")


@app.put("/htmx/blocks/{block_id}/content", response_class=HTMLResponse)
async def htmx_update_block_content(
    request: Request,
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update specific content fields in a block"""
    block = db.query(PageBlock).filter(PageBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    # Handle both form data and JSON
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form_data = await request.form()
        data = dict(form_data)

    # Track what changed
    old_content = dict(block.content) if block.content else {}
    changed_fields = []
    for key, value in data.items():
        old_val = old_content.get(key)
        if str(old_val) != str(value):
            field_name = key.replace("_", " ").title()
            changed_fields.append(field_name)

    # Merge new values into existing content
    content = dict(block.content) if block.content else {}
    for key, value in data.items():
        content[key] = value

    block.content = content
    block.updated_at = get_now()
    db.commit()

    # Log activity if something changed
    if changed_fields:
        page = db.query(Page).filter(Page.id == block.page_id).first()
        if page:
            log = ActivityLog(
                site_id=page.site_id,
                user_id=user.user_id,
                user_name=user.full_name,
                action="update",
                entity_type="page",
                entity_id=page.id,
                entity_name=page.title,
                details={
                    "block_type": block.block_type.replace("_", " ").title(),
                    "changed_fields": changed_fields
                }
            )
            db.add(log)
            db.commit()

    return HTMLResponse(content="")


@app.delete("/htmx/blocks/{block_id}", response_class=HTMLResponse)
async def htmx_delete_block(
    request: Request,
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete a block"""
    block = db.query(PageBlock).filter(PageBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    # Get page info before deletion for logging
    page = db.query(Page).filter(Page.id == block.page_id).first()
    block_type = block.block_type

    db.delete(block)
    db.commit()

    # Log activity
    if page:
        log = ActivityLog(
            site_id=page.site_id,
            user_id=user.user_id,
            user_name=user.full_name,
            action="delete",
            entity_type="block",
            entity_id=block_id,
            entity_name=page.title,
            details={
                "block_type": block_type.replace("_", " ").title(),
                "description": f"Removed {block_type.replace('_', ' ').title()} block from page"
            }
        )
        db.add(log)
        db.commit()

    return HTMLResponse(content="")


@app.post("/htmx/blocks/reorder", response_class=HTMLResponse)
async def htmx_reorder_blocks(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Reorder blocks"""
    import json

    body = await request.body()
    data = json.loads(body)

    for item in data.get("items", []):
        block = db.query(PageBlock).filter(PageBlock.id == item["id"]).first()
        if block:
            block.sort_order = item["sort_order"]

    db.commit()

    return HTMLResponse(content="")


@app.post("/htmx/pages/reorder", response_class=HTMLResponse)
async def htmx_reorder_pages(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Reorder pages"""
    import json

    body = await request.body()
    data = json.loads(body)

    for item in data.get("items", []):
        page = db.query(Page).filter(Page.id == item["id"]).first()
        if page:
            page.nav_order = item["sort_order"]

    db.commit()

    return HTMLResponse(content="")


# ============ Image htmx Routes ============

import uuid
from PIL import Image as PILImage

UPLOAD_DIR = "/app/uploads"


@app.post("/htmx/sites/{site_id}/images", response_class=HTMLResponse)
async def htmx_upload_image(
    request: Request,
    site_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Upload an image for a site"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Create site upload directory if it doesn't exist
    site_dir = os.path.join(UPLOAD_DIR, site.slug)
    os.makedirs(site_dir, exist_ok=True)

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        raise HTTPException(status_code=400, detail="Invalid image format")

    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(site_dir, unique_filename)

    # Save original file
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Get image dimensions and size
    file_size = len(contents)
    width, height = None, None
    try:
        with PILImage.open(file_path) as img:
            width, height = img.size

            # Create thumbnail (150px)
            thumb_filename = f"thumb_{unique_filename}"
            thumb_path = os.path.join(site_dir, thumb_filename)
            thumb = img.copy()
            thumb.thumbnail((150, 150), PILImage.Resampling.LANCZOS)
            thumb.save(thumb_path, quality=85)

            # Create medium version (600px)
            medium_filename = f"medium_{unique_filename}"
            medium_path = os.path.join(site_dir, medium_filename)
            medium = img.copy()
            medium.thumbnail((600, 600), PILImage.Resampling.LANCZOS)
            medium.save(medium_path, quality=85)

    except Exception as e:
        # If image processing fails, still save the record
        pass

    # Save to database
    image = Image(
        site_id=site_id,
        filename=unique_filename,
        original_filename=file.filename,
        folder="general",
        mime_type=file.content_type,
        file_size=file_size,
        width=width,
        height=height,
        thumb_url=f"/websites/uploads/{site.slug}/thumb_{unique_filename}" if width else None,
        medium_url=f"/websites/uploads/{site.slug}/medium_{unique_filename}" if width else None
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # Return the image card HTML
    return templates.TemplateResponse("admin/images/partials/image_card.html", {
        "request": request,
        "image": image,
        "site": site
    })


@app.get("/api/sites/{site_id}/images")
async def api_list_site_images(
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """List all images for a site"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    images = db.query(Image).filter(Image.site_id == site_id).order_by(Image.created_at.desc()).all()

    return [
        {
            "id": img.id,
            "filename": img.filename,
            "original_filename": img.original_filename,
            "url": f"/websites/uploads/{site.slug}/{img.filename}",
            "thumb_url": img.thumb_url,
            "medium_url": img.medium_url
        }
        for img in images
    ]


@app.get("/api/blocks/{block_id}")
async def api_get_block(
    block_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get block content for editing"""
    block = db.query(PageBlock).filter(PageBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    return {
        "id": block.id,
        "block_type": block.block_type,
        "content": block.content,
        "is_visible": block.is_visible,
        "sort_order": block.sort_order
    }


@app.get("/api/images/{image_id}")
async def api_get_image(
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get image details"""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    return {
        "id": image.id,
        "filename": image.filename,
        "original_filename": image.original_filename,
        "folder": image.folder,
        "alt_text": image.alt_text,
        "mime_type": image.mime_type,
        "file_size": image.file_size,
        "width": image.width,
        "height": image.height,
        "thumb_url": image.thumb_url,
        "medium_url": image.medium_url
    }


@app.put("/htmx/images/{image_id}", response_class=HTMLResponse)
async def htmx_update_image(
    request: Request,
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update image metadata"""
    import json

    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    body = await request.body()
    data = json.loads(body)

    if "alt_text" in data:
        image.alt_text = data["alt_text"]
    if "folder" in data:
        image.folder = data["folder"]

    db.commit()

    return HTMLResponse(content="")


@app.delete("/htmx/images/{image_id}", response_class=HTMLResponse)
async def htmx_delete_image(
    request: Request,
    image_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete an image"""
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Get site for path
    site = db.query(Site).filter(Site.id == image.site_id).first()
    site_dir = os.path.join(UPLOAD_DIR, site.slug) if site else UPLOAD_DIR

    # Delete physical files
    try:
        file_path = os.path.join(site_dir, image.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        thumb_path = os.path.join(site_dir, f"thumb_{image.filename}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)

        medium_path = os.path.join(site_dir, f"medium_{image.filename}")
        if os.path.exists(medium_path):
            os.remove(medium_path)
    except Exception:
        pass  # Continue even if file deletion fails

    # Delete from database
    db.delete(image)
    db.commit()

    return HTMLResponse(content="")


# ============ API Routes (JSON) ============

@app.get("/api/sites", response_model=List[SiteResponse])
async def api_list_sites(db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """List all sites"""
    sites = db.query(Site).order_by(Site.name).all()
    return sites


@app.post("/api/sites/{site_id}/generate")
async def api_generate_site(site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Trigger static site generation"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # TODO: Implement generator
    # from generator import SiteGenerator
    # generator = SiteGenerator(db)
    # output_dir = generator.generate_site(site_id)

    site.last_generated_at = get_now()
    db.commit()

    # Log activity
    log = ActivityLog(
        site_id=site_id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="generate",
        entity_type="site",
        entity_id=site.id,
        entity_name=site.name
    )
    db.add(log)
    db.commit()

    return {"status": "success", "message": f"Site {site.name} generated"}


@app.post("/api/sites/{site_id}/publish")
async def api_publish_site(site_id: int, db: Session = Depends(get_db), user: User = Depends(require_auth)):
    """Generate and mark site as published"""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # TODO: Implement generator
    site.is_published = True
    site.last_generated_at = get_now()
    db.commit()

    # Log activity
    log = ActivityLog(
        site_id=site_id,
        user_id=user.user_id,
        user_name=user.full_name,
        action="publish",
        entity_type="site",
        entity_id=site.id,
        entity_name=site.name
    )
    db.add(log)
    db.commit()

    return {"status": "success", "message": f"Site {site.name} published"}


# ============ Submission API ============

@app.get("/api/submissions/{submission_id}")
async def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Get a single submission"""
    submission = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {
        "id": submission.id,
        "site_id": submission.site_id,
        "name": submission.name,
        "email": submission.email,
        "phone": submission.phone,
        "subject": submission.subject,
        "message": submission.message,
        "is_read": submission.is_read,
        "is_spam": submission.is_spam,
        "created_at": submission.created_at.isoformat() if submission.created_at else None
    }


@app.put("/htmx/submissions/{submission_id}")
async def update_submission(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Update submission (read/spam status)"""
    submission = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    data = await request.json()

    if "is_read" in data:
        submission.is_read = data["is_read"]
    if "is_spam" in data:
        submission.is_spam = data["is_spam"]

    db.commit()
    return {"status": "success"}


@app.delete("/htmx/submissions/{submission_id}")
async def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Delete a submission"""
    submission = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    db.delete(submission)
    db.commit()
    return {"status": "success"}


@app.post("/htmx/sites/{site_id}/submissions/mark-read")
async def mark_all_submissions_read(
    site_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Mark all submissions for a site as read"""
    db.query(FormSubmission).filter(
        FormSubmission.site_id == site_id,
        FormSubmission.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"status": "success"}


# ============ Public API (for generated sites) ============

@app.post("/api/public/contact")
async def public_contact_form(
    request: Request,
    site_slug: str,
    db: Session = Depends(get_db)
):
    """Handle contact form submissions from generated sites (accepts JSON or Form data)"""
    site = db.query(Site).filter(Site.slug == site_slug).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Get client IP
    client_ip = request.client.host

    # Handle both JSON and form data
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone")
        subject = data.get("subject")
        message = data.get("message")
    else:
        form = await request.form()
        name = form.get("name")
        email = form.get("email")
        phone = form.get("phone")
        subject = form.get("subject")
        message = form.get("message")

    submission = FormSubmission(
        site_id=site.id,
        name=name,
        email=email,
        phone=phone,
        subject=subject,
        message=message,
        ip_address=client_ip
    )
    db.add(submission)
    db.commit()

    return {"status": "success", "message": "Thank you for your message!"}


# ============ Preview Routes ============

@app.get("/preview/{site_slug}/{page_slug}", response_class=HTMLResponse)
async def preview_page(
    request: Request,
    site_slug: str,
    page_slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_auth)
):
    """Preview a page before publishing"""
    site = db.query(Site).filter(Site.slug == site_slug).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    page = db.query(Page).options(
        joinedload(Page.blocks)
    ).filter(Page.site_id == site.id, Page.slug == page_slug).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get hours for hours block
    hours = db.query(Hours).filter(Hours.site_id == site.id).order_by(Hours.day_of_week).all()
    hours_dict = {h.day_of_week: h for h in hours}

    # Get menus for menu blocks
    menus = db.query(Menu).options(
        joinedload(Menu.categories).joinedload(MenuCategory.items)
    ).filter(Menu.site_id == site.id, Menu.is_active == True).all()

    # Get all pages for navigation
    nav_pages = db.query(Page).filter(
        Page.site_id == site.id,
        Page.is_in_nav == True,
        Page.is_published == True
    ).order_by(Page.nav_order).all()

    return templates.TemplateResponse("preview/page.html", {
        "request": request,
        "site": site,
        "page": page,
        "hours_dict": hours_dict,
        "menus": menus,
        "nav_pages": nav_pages,
        "days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "is_preview": True
    })
