"""
API endpoints for self-hosted E-Signature functionality
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)

from hr.db.database import get_db
from hr.models.employee import Employee
from hr.models.document import Document
from hr.models.user import User
from hr.models.esignature import SignatureRequest, SignatureTemplate
from hr.schemas.esignature import (
    SignatureRequestResponse,
    SignatureRequestWithEmployee,
    SignatureTemplateCreate,
    SignatureTemplateUpdate,
    SignatureTemplateResponse,
    SendSignatureRequest,
    SendSignatureResponse,
    SigningSubmission
)
from hr.api.auth import require_auth
from hr.services.signing_service import (
    generate_signing_token,
    compute_file_hash,
    create_signing_copy,
    get_signing_url,
    create_signed_pdf_with_audit,
    TOKEN_EXPIRY_DAYS
)
from hr.services.email import EmailService

logger = logging.getLogger(__name__)
router = APIRouter()

# Upload directory for signed documents
SIGNED_DOCS_DIR = "/app/documents/signed"

# Document templates directory
TEMPLATES_DIR = "/app/documents/templates"

# Templates for signing page
templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "templates")
templates = Jinja2Templates(directory=templates_dir)


# ============ Signature Request Endpoints ============

@router.post("/send", response_model=SendSignatureResponse)
def send_for_signature(
    request_data: SendSignatureRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Send a document to an employee for e-signature."""
    # Get employee
    employee = db.query(Employee).filter(Employee.id == request_data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if not employee.email:
        raise HTTPException(status_code=400, detail="Employee has no email address")

    # Determine document title
    title = request_data.title or f"New Hire Packet - {employee.first_name} {employee.last_name}"
    message = request_data.message or (
        f"Please review and sign the attached document at your earliest convenience."
    )

    # Find template
    template = None
    if request_data.template_id:
        template = db.query(SignatureTemplate).filter(
            SignatureTemplate.id == request_data.template_id,
            SignatureTemplate.is_active == True
        ).first()

    if not template:
        raise HTTPException(
            status_code=400,
            detail="No template selected. Please choose a document template."
        )

    if not template.template_file_path or not os.path.exists(template.template_file_path):
        raise HTTPException(
            status_code=400,
            detail="Template PDF file not found. Please re-upload the template."
        )

    # Generate signing token
    token = generate_signing_token()
    expires_at = get_now() + timedelta(days=TOKEN_EXPIRY_DAYS)

    # Create the record
    signature_request = SignatureRequest(
        employee_id=employee.id,
        template_id=template.id,
        document_title=title,
        document_type=request_data.document_type,
        status="sent",
        signer_email=employee.email,
        signer_name=f"{employee.first_name} {employee.last_name}",
        signing_token=token,
        token_expires_at=expires_at,
        sent_at=get_now(),
        created_by=current_user.id,
        request_metadata={
            "message": message,
        }
    )

    db.add(signature_request)
    db.commit()
    db.refresh(signature_request)

    # Copy the template and set the path + hash
    try:
        copy_path = create_signing_copy(
            template.template_file_path, employee.id, signature_request.id
        )
        doc_hash = compute_file_hash(copy_path)

        signature_request.original_file_path = copy_path
        signature_request.document_hash = doc_hash
        db.commit()
    except Exception as e:
        logger.error(f"Error creating signing copy: {e}")
        db.delete(signature_request)
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to prepare document for signing")

    # Send signing email
    signing_url = get_signing_url(token)
    try:
        EmailService.send_signature_request_email(
            to_email=employee.email,
            signer_name=f"{employee.first_name} {employee.last_name}",
            document_title=title,
            signing_url=signing_url,
            expires_in_days=TOKEN_EXPIRY_DAYS,
            custom_message=message
        )
    except Exception as e:
        logger.warning(f"Failed to send signing email (request still created): {e}")

    logger.info(f"Signature request created: ID={signature_request.id} for employee {employee.id}")

    return SendSignatureResponse(
        success=True,
        signature_request_id=signature_request.id,
        signing_url=signing_url,
        message=f"Signature request sent to {employee.email}"
    )


@router.get("/requests", response_model=List[SignatureRequestWithEmployee])
def list_signature_requests(
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all signature requests with optional filters."""
    query = db.query(SignatureRequest).join(Employee)

    if employee_id:
        query = query.filter(SignatureRequest.employee_id == employee_id)

    if status:
        query = query.filter(SignatureRequest.status == status)

    requests = query.order_by(SignatureRequest.created_at.desc()).offset(skip).limit(limit).all()

    results = []
    for req in requests:
        results.append(SignatureRequestWithEmployee(
            id=req.id,
            employee_id=req.employee_id,
            document_title=req.document_title,
            document_type=req.document_type,
            status=req.status,
            signer_email=req.signer_email,
            signer_name=req.signer_name,
            signing_token=req.signing_token if req.status in ["pending", "sent", "viewed"] else None,
            created_at=req.created_at,
            sent_at=req.sent_at,
            viewed_at=req.viewed_at,
            signed_at=req.signed_at,
            signed_document_id=req.signed_document_id,
            created_by=req.created_by,
            signer_ip=req.signer_ip,
            signer_user_agent=req.signer_user_agent,
            document_hash=req.document_hash,
            signed_document_hash=req.signed_document_hash,
            employee_name=f"{req.employee.first_name} {req.employee.last_name}",
            employee_email=req.employee.email
        ))

    return results


@router.get("/requests/{request_id}", response_model=SignatureRequestResponse)
def get_signature_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific signature request."""
    req = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Signature request not found")
    return req


@router.get("/requests/employee/{employee_id}", response_model=List[SignatureRequestResponse])
def get_employee_signature_requests(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all signature requests for an employee."""
    requests = db.query(SignatureRequest).filter(
        SignatureRequest.employee_id == employee_id
    ).order_by(SignatureRequest.created_at.desc()).all()
    return requests


@router.post("/requests/{request_id}/remind")
def send_reminder(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Send a reminder for a pending signature request."""
    req = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Signature request not found")

    if req.status not in ["pending", "sent", "viewed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send reminder for request with status '{req.status}'"
        )

    if not req.signing_token:
        raise HTTPException(status_code=400, detail="No signing token — request may have been cancelled")

    # Check if token is expired, generate new one if needed
    if req.token_expires_at and req.token_expires_at < get_now():
        req.signing_token = generate_signing_token()
        req.token_expires_at = get_now() + timedelta(days=TOKEN_EXPIRY_DAYS)
        db.commit()

    signing_url = get_signing_url(req.signing_token)

    try:
        EmailService.send_signature_request_email(
            to_email=req.signer_email,
            signer_name=req.signer_name,
            document_title=req.document_title,
            signing_url=signing_url,
            expires_in_days=TOKEN_EXPIRY_DAYS,
            custom_message="This is a reminder to please sign the following document."
        )
        return {"message": f"Reminder sent to {req.signer_email}"}
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/requests/{request_id}/cancel")
def cancel_signature_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Cancel a signature request."""
    req = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Signature request not found")

    if req.status == "signed":
        raise HTTPException(status_code=400, detail="Cannot cancel a signed request")

    req.status = "cancelled"
    req.signing_token = None  # Invalidate the token
    req.cancelled_at = get_now()
    req.cancelled_by = current_user.id
    db.commit()
    return {"message": "Signature request cancelled"}


@router.get("/requests/{request_id}/status")
def check_signature_status(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Check the current status of a signature request."""
    req = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Signature request not found")

    return {
        "status": req.status,
        "is_complete": req.status == "signed",
        "signed_at": req.signed_at.isoformat() if req.signed_at else None,
        "signer_ip": req.signer_ip,
        "document_hash": req.document_hash,
        "signed_document_hash": req.signed_document_hash,
    }


@router.get("/requests/{request_id}/signing-url")
def get_signing_link(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get the signing URL for a request (for copying to clipboard)."""
    req = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Signature request not found")

    if req.status in ["signed", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    if not req.signing_token:
        raise HTTPException(status_code=400, detail="No signing token available")

    return {"signing_url": get_signing_url(req.signing_token)}


# ============ Public Signing Endpoints (NO AUTH) ============

@router.get("/sign/{token}", response_class=HTMLResponse)
def signing_page(
    token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Public signing page — no auth required."""
    sig_req = db.query(SignatureRequest).filter(
        SignatureRequest.signing_token == token
    ).first()

    if not sig_req:
        return templates.TemplateResponse("signing_page.html", {
            "request": request,
            "error": "Invalid or expired signing link.",
            "sig_request": None,
            "fields": [],
        })

    # Check expiry
    if sig_req.token_expires_at and sig_req.token_expires_at < get_now():
        return templates.TemplateResponse("signing_page.html", {
            "request": request,
            "error": "This signing link has expired. Please contact HR for a new link.",
            "sig_request": None,
            "fields": [],
        })

    # Check if already signed
    if sig_req.status == "signed":
        return templates.TemplateResponse("signing_page.html", {
            "request": request,
            "error": "This document has already been signed.",
            "sig_request": None,
            "fields": [],
        })

    if sig_req.status == "cancelled":
        return templates.TemplateResponse("signing_page.html", {
            "request": request,
            "error": "This signature request has been cancelled.",
            "sig_request": None,
            "fields": [],
        })

    # Mark as viewed
    if sig_req.status in ["pending", "sent"]:
        sig_req.status = "viewed"
        sig_req.viewed_at = get_now()
        db.commit()

    # Get template fields
    fields = []
    if sig_req.template and sig_req.template.signature_fields:
        fields = sig_req.template.signature_fields

    return templates.TemplateResponse("signing_page.html", {
        "request": request,
        "error": None,
        "sig_request": sig_req,
        "fields": fields,
        "token": token,
    })


@router.get("/sign/{token}/pdf")
def serve_signing_pdf(
    token: str,
    db: Session = Depends(get_db)
):
    """Serve the PDF document for signing — no auth required."""
    sig_req = db.query(SignatureRequest).filter(
        SignatureRequest.signing_token == token
    ).first()

    if not sig_req:
        raise HTTPException(status_code=404, detail="Invalid signing link")

    if sig_req.token_expires_at and sig_req.token_expires_at < get_now():
        raise HTTPException(status_code=410, detail="Signing link expired")

    if sig_req.status in ["signed", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Request is {sig_req.status}")

    if not sig_req.original_file_path or not os.path.exists(sig_req.original_file_path):
        raise HTTPException(status_code=404, detail="Document file not found")

    return FileResponse(
        sig_req.original_file_path,
        media_type="application/pdf",
        filename=f"{sig_req.document_title}.pdf"
    )


@router.post("/sign/{token}/submit")
def submit_signing(
    token: str,
    submission: SigningSubmission,
    request: Request,
    db: Session = Depends(get_db)
):
    """Process a signature submission — no auth required."""
    sig_req = db.query(SignatureRequest).filter(
        SignatureRequest.signing_token == token
    ).first()

    if not sig_req:
        raise HTTPException(status_code=404, detail="Invalid signing link")

    if sig_req.token_expires_at and sig_req.token_expires_at < get_now():
        raise HTTPException(status_code=410, detail="Signing link expired")

    if sig_req.status == "signed":
        raise HTTPException(status_code=400, detail="Document already signed")

    if sig_req.status == "cancelled":
        raise HTTPException(status_code=400, detail="Request has been cancelled")

    if not submission.agreed_to_terms:
        raise HTTPException(status_code=400, detail="You must agree to the electronic signature terms")

    if not submission.signature_image:
        raise HTTPException(status_code=400, detail="Signature is required")

    if not submission.typed_name or not submission.typed_name.strip():
        raise HTTPException(status_code=400, detail="Typed name is required")

    # Capture signer info
    signer_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if "," in signer_ip:
        signer_ip = signer_ip.split(",")[0].strip()
    signer_ua = request.headers.get("User-Agent", "unknown")

    # Get signature fields from template
    fields = []
    if sig_req.template and sig_req.template.signature_fields:
        fields = sig_req.template.signature_fields

    if not sig_req.original_file_path or not os.path.exists(sig_req.original_file_path):
        raise HTTPException(status_code=500, detail="Original document not found")

    now = get_now()

    try:
        # Create the signed PDF with audit certificate
        final_pdf_bytes, signed_doc_hash = create_signed_pdf_with_audit(
            pdf_path=sig_req.original_file_path,
            signature_fields=fields,
            signature_image_b64=submission.signature_image,
            typed_name=submission.typed_name,
            field_values=submission.field_values,
            request_id=sig_req.id,
            document_title=sig_req.document_title,
            signer_name=sig_req.signer_name,
            signer_email=sig_req.signer_email,
            signed_at=now,
            signer_ip=signer_ip,
            signer_user_agent=signer_ua,
            document_hash=sig_req.document_hash
        )

        # Save the signed PDF
        employee_dir = os.path.join(SIGNED_DOCS_DIR, str(sig_req.employee_id))
        os.makedirs(employee_dir, exist_ok=True)

        timestamp = now.strftime("%Y%m%d_%H%M%S")
        safe_type = sig_req.document_type.replace(" ", "_")
        filename = f"{timestamp}_signed_{safe_type}.pdf"
        file_path = os.path.join(employee_dir, filename)

        with open(file_path, "wb") as f:
            f.write(final_pdf_bytes)

        # Create document record
        document = Document(
            employee_id=sig_req.employee_id,
            document_type=f"{sig_req.document_type} (Signed)",
            file_name=filename,
            file_path=file_path,
            file_size=len(final_pdf_bytes),
            mime_type="application/pdf",
            notes=f"E-signed: {sig_req.document_title} — Signed by {submission.typed_name}"
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Update signature request
        sig_req.status = "signed"
        sig_req.signed_at = now
        sig_req.signer_ip = signer_ip
        sig_req.signer_user_agent = signer_ua
        sig_req.signed_document_hash = signed_doc_hash
        sig_req.signed_document_id = document.id
        sig_req.signing_token = None  # Invalidate token
        sig_req.signing_data = {
            "typed_name": submission.typed_name,
            "field_values": submission.field_values or {},
            "has_signature_image": True,
        }
        db.commit()

        logger.info(f"Document signed: request={sig_req.id}, employee={sig_req.employee_id}")

        # Send notification to HR (non-blocking)
        try:
            creator_email = None
            if sig_req.creator:
                creator_email = sig_req.creator.email if hasattr(sig_req.creator, 'email') else None
            EmailService.send_signature_completed_email(
                creator_email=creator_email,
                signer_name=sig_req.signer_name,
                document_title=sig_req.document_title,
                employee_id=sig_req.employee_id,
                signer_email=sig_req.signer_email,
                signed_pdf_path=file_path
            )
        except Exception as e:
            logger.warning(f"Failed to send completion notification: {e}")

        return {"success": True, "message": "Document signed successfully. Thank you!"}

    except Exception as e:
        logger.error(f"Error processing signature: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your signature. Please try again.")


# ============ Template Endpoints ============

@router.get("/templates", response_model=List[SignatureTemplateResponse])
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all signature templates."""
    templates_list = db.query(SignatureTemplate).filter(
        SignatureTemplate.is_active == True
    ).all()
    return templates_list


@router.post("/templates", response_model=SignatureTemplateResponse, status_code=201)
def create_template(
    template_data: SignatureTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new signature template."""
    template = SignatureTemplate(
        name=template_data.name,
        description=template_data.description,
        document_type=template_data.document_type,
        signature_fields=([f.dict() for f in template_data.signature_fields]
                         if template_data.signature_fields else None),
        created_by=current_user.id
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put("/templates/{template_id}", response_model=SignatureTemplateResponse)
def update_template(
    template_id: int,
    template_data: SignatureTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update a signature template."""
    template = db.query(SignatureTemplate).filter(
        SignatureTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = template_data.dict(exclude_unset=True)
    if "signature_fields" in update_data and update_data["signature_fields"]:
        update_data["signature_fields"] = [f.dict() for f in update_data["signature_fields"]]

    for key, value in update_data.items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete (deactivate) a signature template."""
    template = db.query(SignatureTemplate).filter(
        SignatureTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.is_active = False
    db.commit()
    return {"message": "Template deleted"}


@router.post("/templates/upload")
async def upload_template_file(
    name: str = Form(...),
    document_type: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Upload a PDF template file for e-signatures."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").replace(" ", "_")
    filename = f"{timestamp}_{safe_name}.pdf"
    file_path = os.path.join(TEMPLATES_DIR, filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving template file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    template = SignatureTemplate(
        name=name,
        description=description,
        document_type=document_type,
        template_file_path=file_path,
        is_active=True,
        created_by=current_user.id
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    logger.info(f"Template uploaded: {name} -> {file_path}")

    return {
        "id": template.id,
        "name": template.name,
        "document_type": template.document_type,
        "file_path": file_path,
        "message": "Template uploaded successfully"
    }


@router.get("/templates/{template_id}")
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a single template with its fields."""
    template = db.query(SignatureTemplate).filter(
        SignatureTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "document_type": template.document_type,
        "is_active": template.is_active,
        "template_file_path": template.template_file_path,
        "signature_fields": template.signature_fields or [],
        "created_at": template.created_at,
        "updated_at": template.updated_at
    }


@router.put("/templates/{template_id}/fields")
def update_template_fields(
    template_id: int,
    fields_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update signature fields for a template."""
    template = db.query(SignatureTemplate).filter(
        SignatureTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.signature_fields = fields_data.get("fields", [])
    template.updated_at = get_now()
    db.commit()
    db.refresh(template)

    logger.info(f"Updated template {template_id} fields: {len(template.signature_fields or [])} fields")

    return {
        "id": template.id,
        "name": template.name,
        "signature_fields": template.signature_fields,
        "message": "Template fields updated successfully"
    }


@router.get("/templates/{template_id}/download")
async def download_template_file(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Download a template file."""
    template = db.query(SignatureTemplate).filter(
        SignatureTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.template_file_path or not os.path.exists(template.template_file_path):
        raise HTTPException(status_code=404, detail="Template file not found")

    return FileResponse(
        template.template_file_path,
        media_type="application/pdf",
        filename=f"{template.name}.pdf"
    )
