"""HTML Page Routes for Forms Service"""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pathlib import Path

from forms.database import get_db
from forms.auth import get_current_user_optional, verify_portal_session
from forms.models import (
    FormSubmission, FormTemplate, SignatureRequest, Category, UserPermission
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Templates directory - /app/templates in container
# Path: pages.py -> routers -> forms -> /app
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


async def get_user_from_request(request: Request) -> Optional[dict]:
    """Try to get user from Portal session cookie."""
    session_token = request.cookies.get("portal_session")
    if not session_token:
        return None

    try:
        user = await verify_portal_session(session_token)
        return user
    except Exception as e:
        logger.debug(f"Session verification failed: {e}")
        return None


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Main dashboard page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/", status_code=302)

    # Get basic metrics
    metrics = {
        "open_forms": {},
        "my_action_items": [],
        "recent_submissions": [],
        "alerts": []
    }

    # Count forms by status (use string values for PostgreSQL ENUM)
    for status in ['draft', 'submitted', 'pending_signature', 'pending_review']:
        result = await db.execute(
            select(func.count()).select_from(FormSubmission).where(
                FormSubmission.status == status
            )
        )
        metrics["open_forms"][status] = result.scalar() or 0

    # Recent submissions
    recent_result = await db.execute(
        select(FormSubmission)
        .options(selectinload(FormSubmission.template))
        .order_by(FormSubmission.created_at.desc())
        .limit(10)
    )
    for sub in recent_result.scalars().all():
        metrics["recent_submissions"].append({
            "id": str(sub.id),
            "template_name": sub.template.name if sub.template else "Form",
            "reference_number": sub.reference_number or str(sub.id)[:8],
            "status": sub.status.value if sub.status else "draft",
            "created_at": sub.created_at
        })

    # Pending signature requests for this user
    user_id = user.get("id")
    if user_id:
        sig_result = await db.execute(
            select(SignatureRequest)
            .where(
                SignatureRequest.requested_employee_id == user_id,
                SignatureRequest.is_fulfilled == False
            )
            .limit(10)
        )
        for req in sig_result.scalars().all():
            sub_result = await db.execute(
                select(FormSubmission)
                .options(selectinload(FormSubmission.template))
                .where(FormSubmission.id == req.submission_id)
            )
            submission = sub_result.scalar_one_or_none()
            if submission:
                metrics["my_action_items"].append({
                    "id": str(submission.id),
                    "template_name": submission.template.name if submission.template else "Form",
                    "reference_number": submission.reference_number or str(submission.id)[:8],
                    "status": "pending_signature"
                })

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "metrics": metrics
    })


@router.get("/submissions", response_class=HTMLResponse)
async def submissions_list_page(
    request: Request,
    template_id: Optional[str] = None,
    location_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Submissions list page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/submissions", status_code=302)

    # Get submissions with filters
    query = select(FormSubmission).options(selectinload(FormSubmission.template))

    if status:
        # Validate status is a valid value
        valid_statuses = ['draft', 'submitted', 'pending_signature', 'pending_review', 'approved', 'rejected', 'archived']
        if status in valid_statuses:
            query = query.where(FormSubmission.status == status)

    if location_id:
        query = query.where(FormSubmission.location_id == location_id)

    # Pagination
    per_page = 20
    offset = (page - 1) * per_page

    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(FormSubmission)
    )
    total = count_result.scalar() or 0

    # Get submissions
    query = query.order_by(FormSubmission.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    submissions = []
    for sub in result.scalars().all():
        submissions.append({
            "id": str(sub.id),
            "template_name": sub.template.name if sub.template else None,
            "location_id": sub.location_id,
            "location_name": f"Location {sub.location_id}",  # Would need to fetch from HR
            "status": sub.status.value if sub.status else "draft",
            "reference_number": sub.reference_number,
            "submitted_by_employee_id": sub.submitted_by_employee_id,
            "created_at": sub.created_at
        })

    # Get templates for filter dropdown
    templates_result = await db.execute(
        select(FormTemplate).where(FormTemplate.is_active == True)
    )
    form_templates = [{"id": str(t.id), "name": t.name} for t in templates_result.scalars().all()]

    # Pagination info
    pages = (total + per_page - 1) // per_page
    pagination = {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page
    }

    return templates.TemplateResponse("admin/submissions_list.html", {
        "request": request,
        "user": user,
        "submissions": submissions,
        "templates": form_templates,
        "locations": [],  # Would need to fetch from HR
        "pagination": pagination if pages > 1 else None
    })


@router.get("/templates", response_class=HTMLResponse)
async def templates_list_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Form templates list page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/templates", status_code=302)

    result = await db.execute(
        select(FormTemplate).order_by(FormTemplate.name)
    )
    form_templates = []
    for t in result.scalars().all():
        form_templates.append({
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "category": t.category.value if t.category else None,
            "description": t.description,
            "is_active": t.is_active,
            "requires_signature": t.requires_signature,
            "version": t.version
        })

    return templates.TemplateResponse("admin/templates_list.html", {
        "request": request,
        "user": user,
        "templates": form_templates
    })


@router.get("/templates/new", response_class=HTMLResponse)
async def template_new_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Create new form template page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/templates/new", status_code=302)

    # Check if user is admin
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    return templates.TemplateResponse("admin/template_form.html", {
        "request": request,
        "user": user,
        "template": None,  # New template
        "categories": [
            {"value": "hr_employment", "label": "HR & Employment"},
            {"value": "safety_compliance", "label": "Safety & Compliance"},
            {"value": "operations", "label": "Operations"}
        ]
    })


@router.get("/templates/{template_id}", response_class=HTMLResponse)
async def template_detail_page(
    request: Request,
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """View form template details page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url=f"/portal/login?next=/forms/templates/{template_id}", status_code=302)

    from uuid import UUID
    try:
        uuid_id = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == uuid_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return templates.TemplateResponse("admin/template_detail.html", {
        "request": request,
        "user": user,
        "template": {
            "id": str(template.id),
            "name": template.name,
            "slug": template.slug,
            "category": template.category.value if template.category else None,
            "description": template.description,
            "is_active": template.is_active,
            "requires_signature": template.requires_signature,
            "version": template.version,
            "schema": template.schema,
            "ui_schema": template.ui_schema,
            "workflow_config": template.workflow_config,
            "created_at": template.created_at,
            "updated_at": template.updated_at
        }
    })


@router.get("/templates/{template_id}/edit", response_class=HTMLResponse)
async def template_edit_page(
    request: Request,
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Edit form template page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url=f"/portal/login?next=/forms/templates/{template_id}/edit", status_code=302)

    # Check if user is admin
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from uuid import UUID
    try:
        uuid_id = UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Template not found")

    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == uuid_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return templates.TemplateResponse("admin/template_form.html", {
        "request": request,
        "user": user,
        "template": {
            "id": str(template.id),
            "name": template.name,
            "slug": template.slug,
            "category": template.category.value if template.category else None,
            "description": template.description,
            "is_active": template.is_active,
            "requires_signature": template.requires_signature,
            "version": template.version,
            "schema": template.schema,
            "ui_schema": template.ui_schema,
            "workflow_config": template.workflow_config
        },
        "categories": [
            {"value": "hr_employment", "label": "HR & Employment"},
            {"value": "safety_compliance", "label": "Safety & Compliance"},
            {"value": "operations", "label": "Operations"}
        ]
    })


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Reports page."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/reports", status_code=302)

    return templates.TemplateResponse("admin/reports.html", {
        "request": request,
        "user": user
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Settings page - admin only."""
    user = await get_user_from_request(request)
    if not user:
        return RedirectResponse(url="/portal/login?next=/forms/settings", status_code=302)

    # Check if user is admin or has manage_users permission
    if not user.get("is_admin"):
        # Check custom permissions
        perm_result = await db.execute(
            select(UserPermission).where(UserPermission.employee_id == user.get("id"))
        )
        perm = perm_result.scalar_one_or_none()
        if not perm or not (perm.can_manage_users or perm.can_manage_categories):
            raise HTTPException(status_code=403, detail="Admin access required")

    # Get all categories
    cat_result = await db.execute(
        select(Category).order_by(Category.sort_order, Category.name)
    )
    categories = [
        {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "description": c.description,
            "color": c.color,
            "icon": c.icon,
            "is_active": c.is_active
        }
        for c in cat_result.scalars().all()
    ]

    # Get users with custom permissions
    perm_result = await db.execute(select(UserPermission))
    permissions = perm_result.scalars().all()

    # Fetch user details from HR for each permission
    import httpx
    users = []
    for perm in permissions:
        user_info = {
            "employee_id": perm.employee_id,
            "name": f"Employee #{perm.employee_id}",
            "email": None,
            "initials": "?",
            "is_admin": False,
            "permissions": {
                "can_create_templates": perm.can_create_templates,
                "can_edit_templates": perm.can_edit_templates,
                "can_delete_templates": perm.can_delete_templates,
                "can_view_all_submissions": perm.can_view_all_submissions,
                "can_delete_submissions": perm.can_delete_submissions,
                "can_export_submissions": perm.can_export_submissions,
                "can_manage_categories": perm.can_manage_categories,
                "can_manage_users": perm.can_manage_users
            }
        }

        # Try to get employee details from HR
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://hr-service:8000/api/employees/{perm.employee_id}",
                    timeout=2.0
                )
                if response.status_code == 200:
                    emp = response.json()
                    first = emp.get("first_name", "")
                    last = emp.get("last_name", "")
                    user_info["name"] = f"{first} {last}".strip()
                    user_info["email"] = emp.get("email")
                    user_info["initials"] = (first[:1] + last[:1]).upper() if first and last else "?"
        except Exception:
            pass

        users.append(user_info)

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "user": user,
        "categories": categories,
        "users": users
    })
