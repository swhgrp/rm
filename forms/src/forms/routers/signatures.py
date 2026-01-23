"""Signatures API Router"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from forms.database import get_db
from forms.auth import get_current_user
from forms.models import (
    Signature, FormSubmission, SignatureRequest, AuditLog,
    SignatureType, SignatureMethod, SubmissionStatus, AuditAction
)
from forms.schemas import (
    SignatureCreate, SignatureResponse,
    SignatureRequestCreate, SignatureRequestResponse
)

router = APIRouter()


@router.get("/submission/{submission_id}", response_model=List[SignatureResponse])
async def list_submission_signatures(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all signatures for a submission."""
    result = await db.execute(
        select(Signature)
        .where(Signature.submission_id == submission_id)
        .order_by(Signature.signed_at)
    )
    signatures = result.scalars().all()

    return signatures


@router.post("/submission/{submission_id}", response_model=SignatureResponse)
async def sign_submission(
    submission_id: UUID,
    signature_data: SignatureCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Sign a submission."""
    # Get submission
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status not in [SubmissionStatus.PENDING_SIGNATURE, SubmissionStatus.SUBMITTED]:
        raise HTTPException(status_code=400, detail="Submission is not awaiting signature")

    # Check if user already signed
    existing = await db.execute(
        select(Signature)
        .where(
            Signature.submission_id == submission_id,
            Signature.employee_id == user.get("id"),
            Signature.signature_type == signature_data.signature_type
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You have already signed this submission")

    # Create signature
    signature = Signature(
        submission_id=submission_id,
        employee_id=user.get("id"),
        signature_type=signature_data.signature_type,
        signature_data=signature_data.signature_data,
        signature_method=signature_data.signature_method,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    db.add(signature)

    # Log signature
    audit = AuditLog(
        submission_id=submission_id,
        template_id=submission.template_id,
        employee_id=user.get("id"),
        action=AuditAction.SIGNED,
        details={
            "signature_type": signature_data.signature_type.value,
            "signature_method": signature_data.signature_method.value
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(audit)

    # Check if signature request was fulfilled
    sig_request_result = await db.execute(
        select(SignatureRequest)
        .where(
            SignatureRequest.submission_id == submission_id,
            SignatureRequest.requested_employee_id == user.get("id"),
            SignatureRequest.signature_type == signature_data.signature_type,
            SignatureRequest.is_fulfilled == False
        )
    )
    sig_request = sig_request_result.scalar_one_or_none()
    if sig_request:
        sig_request.is_fulfilled = True
        sig_request.fulfilled_at = datetime.utcnow()

    await db.commit()
    await db.refresh(signature)

    return signature


@router.post("/request", response_model=SignatureRequestResponse)
async def create_signature_request(
    request_data: SignatureRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a signature request."""
    # Verify submission exists
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == request_data.submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Generate token for email link
    import secrets
    token = secrets.token_urlsafe(32)

    sig_request = SignatureRequest(
        submission_id=request_data.submission_id,
        requested_employee_id=request_data.requested_employee_id,
        signature_type=request_data.signature_type,
        expires_at=request_data.expires_at,
        token=token,
        created_by=user.get("id")
    )

    db.add(sig_request)
    await db.commit()
    await db.refresh(sig_request)

    # TODO: Send notification email

    return sig_request


@router.get("/pending", response_model=List[SignatureRequestResponse])
async def list_my_pending_signatures(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List signature requests for the current user."""
    result = await db.execute(
        select(SignatureRequest)
        .where(
            SignatureRequest.requested_employee_id == user.get("id"),
            SignatureRequest.is_fulfilled == False
        )
        .order_by(SignatureRequest.created_at.desc())
    )
    requests = result.scalars().all()

    return requests


@router.get("/token/{token}")
async def get_submission_by_signature_token(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get submission details for a signature token (used in email links)."""
    result = await db.execute(
        select(SignatureRequest)
        .where(SignatureRequest.token == token, SignatureRequest.is_fulfilled == False)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(status_code=404, detail="Invalid or expired signature token")

    # Check expiration
    if sig_request.expires_at and sig_request.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Signature request has expired")

    # Get submission
    sub_result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == sig_request.submission_id)
    )
    submission = sub_result.scalar_one_or_none()

    return {
        "submission_id": sig_request.submission_id,
        "signature_type": sig_request.signature_type.value,
        "requested_employee_id": sig_request.requested_employee_id,
        "reference_number": submission.reference_number if submission else None
    }
