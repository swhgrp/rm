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
    FormSubmission, FormTemplate, SignatureRequest
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
