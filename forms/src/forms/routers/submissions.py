"""Form Submissions API Router"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from forms.database import get_db
from forms.auth import get_current_user, require_manager
from forms.models import (
    FormSubmission, FormTemplate, Signature, Attachment,
    WorkflowInstance, AuditLog, SubmissionStatus, AuditAction
)
from forms.schemas import (
    FormSubmissionCreate, FormSubmissionUpdate, FormSubmissionResponse,
    FormSubmissionSummary, FormSubmissionDetail, PaginatedResponse
)

router = APIRouter()


def generate_reference_number(template_slug: str) -> str:
    """Generate a unique reference number."""
    import random
    import string
    timestamp = datetime.now().strftime("%Y%m%d")
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{template_slug.upper()[:4]}-{timestamp}-{random_suffix}"


@router.get("/", response_model=PaginatedResponse)
async def list_submissions(
    template_id: Optional[UUID] = None,
    location_id: Optional[int] = None,
    status: Optional[SubmissionStatus] = None,
    subject_employee_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List submissions with filters."""
    query = select(FormSubmission).options(
        selectinload(FormSubmission.template)
    )

    # Apply filters
    filters = []

    if template_id:
        filters.append(FormSubmission.template_id == template_id)

    if location_id:
        filters.append(FormSubmission.location_id == location_id)
    else:
        # If user is not admin, filter by their locations
        user_role = user.get("role")
        if user_role not in ["admin", "superadmin"]:
            user_locations = user.get("locations", [])
            if user_locations:
                filters.append(FormSubmission.location_id.in_(user_locations))

    if status:
        filters.append(FormSubmission.status == status)

    if subject_employee_id:
        filters.append(FormSubmission.subject_employee_id == subject_employee_id)

    if date_from:
        filters.append(FormSubmission.created_at >= date_from)

    if date_to:
        filters.append(FormSubmission.created_at <= date_to)

    if search:
        filters.append(
            or_(
                FormSubmission.reference_number.ilike(f"%{search}%"),
                FormSubmission.data.cast(str).ilike(f"%{search}%")
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(FormSubmission)
    if filters:
        count_query = count_query.where(and_(*filters))
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.order_by(FormSubmission.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    submissions = result.scalars().all()

    # Convert to summary format
    items = []
    for sub in submissions:
        items.append(FormSubmissionSummary(
            id=sub.id,
            template_id=sub.template_id,
            template_name=sub.template.name if sub.template else None,
            location_id=sub.location_id,
            subject_employee_id=sub.subject_employee_id,
            submitted_by_employee_id=sub.submitted_by_employee_id,
            status=sub.status,
            reference_number=sub.reference_number,
            submitted_at=sub.submitted_at,
            created_at=sub.created_at
        ))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page
    )


@router.get("/{submission_id}", response_model=FormSubmissionDetail)
async def get_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get a submission with all details."""
    result = await db.execute(
        select(FormSubmission)
        .options(
            selectinload(FormSubmission.template),
            selectinload(FormSubmission.signatures),
            selectinload(FormSubmission.attachments),
            selectinload(FormSubmission.workflow_instance)
        )
        .where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Log view action
    audit = AuditLog(
        submission_id=submission.id,
        template_id=submission.template_id,
        employee_id=user.get("id"),
        action=AuditAction.VIEWED
    )
    db.add(audit)
    await db.commit()

    return submission


@router.post("/", response_model=FormSubmissionResponse)
async def create_submission(
    submission_data: FormSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new submission (starts as draft)."""
    # Get template
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == submission_data.template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Template is not active")

    # Generate reference number
    reference_number = generate_reference_number(template.slug)

    submission = FormSubmission(
        template_id=submission_data.template_id,
        template_version=template.version,
        location_id=submission_data.location_id,
        subject_employee_id=submission_data.subject_employee_id,
        submitted_by_employee_id=user.get("id"),
        data=submission_data.data,
        status=SubmissionStatus.DRAFT,
        reference_number=reference_number,
        created_by=user.get("id"),
        updated_by=user.get("id")
    )

    db.add(submission)

    # Log creation
    audit = AuditLog(
        submission_id=submission.id,
        template_id=template.id,
        employee_id=user.get("id"),
        action=AuditAction.CREATED,
        details={"reference_number": reference_number}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(submission)

    return submission


@router.put("/{submission_id}", response_model=FormSubmissionResponse)
async def update_submission(
    submission_id: UUID,
    submission_data: FormSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a draft submission."""
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != SubmissionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft submissions can be edited")

    # Check permission
    if submission.submitted_by_employee_id != user.get("id") and user.get("role") not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized to edit this submission")

    submission.data = submission_data.data
    submission.updated_by = user.get("id")

    # Log edit
    audit = AuditLog(
        submission_id=submission.id,
        template_id=submission.template_id,
        employee_id=user.get("id"),
        action=AuditAction.EDITED
    )
    db.add(audit)

    await db.commit()
    await db.refresh(submission)

    return submission


@router.post("/{submission_id}/submit", response_model=FormSubmissionResponse)
async def submit_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Submit a draft for processing."""
    result = await db.execute(
        select(FormSubmission)
        .options(selectinload(FormSubmission.template))
        .where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != SubmissionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Submission is not a draft")

    # Determine next status
    template = submission.template
    if template.requires_signature:
        submission.status = SubmissionStatus.PENDING_SIGNATURE
    elif template.workflow_id:
        submission.status = SubmissionStatus.PENDING_REVIEW
        # Create workflow instance (handled by workflow engine)
    else:
        submission.status = SubmissionStatus.SUBMITTED

    submission.submitted_at = datetime.utcnow()
    submission.updated_by = user.get("id")

    # Log status change
    audit = AuditLog(
        submission_id=submission.id,
        template_id=submission.template_id,
        employee_id=user.get("id"),
        action=AuditAction.STATUS_CHANGED,
        details={"new_status": submission.status.value}
    )
    db.add(audit)

    await db.commit()
    await db.refresh(submission)

    return submission


@router.get("/{submission_id}/pdf")
async def generate_pdf(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Generate PDF for a submission."""
    result = await db.execute(
        select(FormSubmission)
        .options(
            selectinload(FormSubmission.template),
            selectinload(FormSubmission.signatures)
        )
        .where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Log export
    audit = AuditLog(
        submission_id=submission.id,
        template_id=submission.template_id,
        employee_id=user.get("id"),
        action=AuditAction.EXPORTED,
        details={"format": "pdf"}
    )
    db.add(audit)
    await db.commit()

    # TODO: Implement actual PDF generation with WeasyPrint
    # For now, return placeholder
    return Response(
        content=b"PDF generation not yet implemented",
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={submission.reference_number}.pdf"}
    )


@router.delete("/{submission_id}")
async def delete_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_manager)
):
    """Delete a submission (manager only, draft status only)."""
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != SubmissionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft submissions can be deleted")

    await db.delete(submission)
    await db.commit()

    return {"message": "Submission deleted"}
