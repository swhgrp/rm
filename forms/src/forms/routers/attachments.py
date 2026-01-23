"""Attachments API Router"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from forms.database import get_db
from forms.auth import get_current_user
from forms.models import Attachment, FormSubmission
from forms.schemas import AttachmentCreate, AttachmentResponse
from forms.config import settings

router = APIRouter()


@router.get("/submission/{submission_id}", response_model=List[AttachmentResponse])
async def list_submission_attachments(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all attachments for a submission."""
    result = await db.execute(
        select(Attachment)
        .where(Attachment.submission_id == submission_id)
        .order_by(Attachment.created_at)
    )
    attachments = result.scalars().all()

    return attachments


@router.post("/submission/{submission_id}", response_model=AttachmentResponse)
async def upload_attachment(
    submission_id: UUID,
    file: UploadFile = File(...),
    description: str = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Upload an attachment to a submission."""
    # Verify submission exists
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Validate file size
    contents = await file.read()
    file_size = len(contents)

    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum of {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )

    # Validate file type
    allowed_extensions = settings.ALLOWED_EXTENSIONS.split(",")
    file_ext = file.filename.split(".")[-1].lower() if file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )

    # TODO: Upload to Files service and get file_id
    # For now, generate a placeholder UUID
    import uuid
    file_id = uuid.uuid4()

    attachment = Attachment(
        submission_id=submission_id,
        file_id=file_id,
        file_name=file.filename or "unnamed",
        file_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        description=description,
        created_by=user.get("id")
    )

    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return attachment


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get attachment details."""
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    return attachment


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete an attachment."""
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Check permission - only the uploader or admin can delete
    if attachment.created_by != user.get("id") and user.get("role") not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this attachment")

    # TODO: Also delete from Files service

    await db.delete(attachment)
    await db.commit()

    return {"message": "Attachment deleted"}
