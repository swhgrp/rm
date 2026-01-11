"""
API endpoints for E-Signature functionality using Dropbox Sign
"""

import os
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
import json

from hr.db.database import get_db
from hr.models.employee import Employee
from hr.models.document import Document
from hr.models.user import User
from hr.models.esignature import SignatureRequest, SignatureTemplate
from hr.schemas.esignature import (
    SignatureRequestCreate,
    SignatureRequestResponse,
    SignatureRequestWithEmployee,
    SignatureTemplateCreate,
    SignatureTemplateUpdate,
    SignatureTemplateResponse,
    SendSignatureRequest,
    SendSignatureResponse
)
from hr.api.auth import require_auth
from hr.services.dropbox_sign import dropbox_sign_service, DropboxSignService

logger = logging.getLogger(__name__)
router = APIRouter()

# Upload directory for signed documents
SIGNED_DOCS_DIR = "/app/documents/signed"

# Document templates directory
TEMPLATES_DIR = "/app/documents/templates"


# ============ Signature Request Endpoints ============

@router.post("/send", response_model=SendSignatureResponse)
async def send_for_signature(
    request_data: SendSignatureRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Send a document to an employee for e-signature via Dropbox Sign.
    """
    # Get employee
    employee = db.query(Employee).filter(Employee.id == request_data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    if not employee.email:
        raise HTTPException(status_code=400, detail="Employee has no email address")

    # Determine document title and template
    title = request_data.title or f"New Hire Packet - {employee.first_name} {employee.last_name}"
    subject = request_data.subject or f"Please sign: {title}"
    message = request_data.message or (
        f"Hi {employee.first_name},\n\n"
        f"Please review and sign the attached document at your earliest convenience.\n\n"
        f"Thank you!"
    )

    # Build signer info
    signers = [{
        "email_address": employee.email,
        "name": f"{employee.first_name} {employee.last_name}",
        "order": 0
    }]

    # Check for template
    template_id = None
    file_paths = []

    if request_data.template_id:
        template = db.query(SignatureTemplate).filter(
            SignatureTemplate.id == request_data.template_id,
            SignatureTemplate.is_active == True
        ).first()
        if template:
            template_id = template.dropbox_template_id
            if template.template_file_path and os.path.exists(template.template_file_path):
                file_paths.append(template.template_file_path)

    # If no template, look for default new hire packet
    if not template_id and not file_paths:
        default_template_path = os.path.join(TEMPLATES_DIR, "new_hire_packet.pdf")
        if os.path.exists(default_template_path):
            file_paths.append(default_template_path)
        else:
            raise HTTPException(
                status_code=400,
                detail="No template found. Please upload a document template first."
            )

    try:
        # Send via Dropbox Sign
        # Use test_mode=True for testing without legal binding
        test_mode = os.getenv("DROPBOX_SIGN_TEST_MODE", "false").lower() == "true"

        response = await dropbox_sign_service.send_signature_request(
            title=title,
            subject=subject,
            message=message,
            signers=signers,
            file_paths=file_paths if file_paths else None,
            template_id=template_id,
            metadata={
                "employee_id": str(employee.id),
                "document_type": request_data.document_type,
                "created_by": str(current_user.id)
            },
            test_mode=test_mode
        )

        # Extract signature request ID from response
        sig_request = response.get("signature_request", {})
        dropbox_sig_id = sig_request.get("signature_request_id")

        if not dropbox_sig_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to get signature request ID from Dropbox Sign"
            )

        # Create local record
        signature_request = SignatureRequest(
            dropbox_signature_request_id=dropbox_sig_id,
            employee_id=employee.id,
            document_title=title,
            document_type=request_data.document_type,
            status="sent",
            signer_email=employee.email,
            signer_name=f"{employee.first_name} {employee.last_name}",
            sent_at=datetime.utcnow(),
            created_by=current_user.id,
            request_metadata={
                "subject": subject,
                "test_mode": test_mode
            }
        )

        db.add(signature_request)
        db.commit()
        db.refresh(signature_request)

        logger.info(f"Signature request sent: {dropbox_sig_id} for employee {employee.id}")

        return SendSignatureResponse(
            success=True,
            signature_request_id=signature_request.id,
            dropbox_signature_request_id=dropbox_sig_id,
            message=f"Signature request sent to {employee.email}"
        )

    except Exception as e:
        logger.error(f"Error sending signature request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            dropbox_signature_request_id=req.dropbox_signature_request_id,
            employee_id=req.employee_id,
            document_title=req.document_title,
            document_type=req.document_type,
            status=req.status,
            signer_email=req.signer_email,
            signer_name=req.signer_name,
            created_at=req.created_at,
            sent_at=req.sent_at,
            viewed_at=req.viewed_at,
            signed_at=req.signed_at,
            signed_document_id=req.signed_document_id,
            created_by=req.created_by,
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
    request = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Signature request not found")
    return request


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
async def send_reminder(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Send a reminder for a pending signature request."""
    request = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Signature request not found")

    if request.status not in ["pending", "sent", "viewed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send reminder for request with status '{request.status}'"
        )

    try:
        await dropbox_sign_service.send_reminder(
            request.dropbox_signature_request_id,
            request.signer_email
        )
        return {"message": f"Reminder sent to {request.signer_email}"}
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/requests/{request_id}/cancel")
async def cancel_signature_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Cancel a signature request."""
    request = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Signature request not found")

    if request.status == "signed":
        raise HTTPException(status_code=400, detail="Cannot cancel a signed request")

    try:
        await dropbox_sign_service.cancel_signature_request(
            request.dropbox_signature_request_id
        )
        request.status = "cancelled"
        db.commit()
        return {"message": "Signature request cancelled"}
    except Exception as e:
        logger.error(f"Error cancelling request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests/{request_id}/status")
async def check_signature_status(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Check the current status of a signature request from Dropbox Sign."""
    request = db.query(SignatureRequest).filter(SignatureRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Signature request not found")

    try:
        response = await dropbox_sign_service.get_signature_request(
            request.dropbox_signature_request_id
        )
        sig_request = response.get("signature_request", {})

        # Update local status
        is_complete = sig_request.get("is_complete", False)
        if is_complete and request.status != "signed":
            request.status = "signed"
            request.signed_at = datetime.utcnow()
            db.commit()

        return {
            "local_status": request.status,
            "dropbox_status": sig_request.get("signing_status"),
            "is_complete": is_complete,
            "signatures": sig_request.get("signatures", [])
        }
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Webhook Endpoint ============

@router.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Handle webhooks from Dropbox Sign.

    Dropbox Sign sends events for:
    - signature_request_sent
    - signature_request_viewed
    - signature_request_signed
    - signature_request_declined
    - signature_request_all_signed
    """
    try:
        # Dropbox Sign sends data as form-urlencoded with a 'json' field
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form_data = await request.form()
            json_str = form_data.get("json", "{}")
            data = json.loads(json_str)
        else:
            # Fallback to raw JSON body
            body = await request.body()
            data = json.loads(body)

        # Dropbox Sign sends a test event on webhook creation
        if data.get("event", {}).get("event_type") == "callback_test":
            return JSONResponse(content="Hello API Event Received", status_code=200)

        # Parse the event
        event_data = DropboxSignService.parse_webhook_event(data)
        event_type = event_data.get("event_type")
        signature_request_id = event_data.get("signature_request_id")

        logger.info(f"Webhook received: {event_type} for {signature_request_id}")

        if not signature_request_id:
            return JSONResponse(content="OK", status_code=200)

        # Find our local record
        sig_request = db.query(SignatureRequest).filter(
            SignatureRequest.dropbox_signature_request_id == signature_request_id
        ).first()

        if not sig_request:
            logger.warning(f"Signature request not found: {signature_request_id}")
            return JSONResponse(content="OK", status_code=200)

        # Update status based on event
        now = datetime.utcnow()

        if event_type == "signature_request_sent":
            sig_request.status = "sent"
            sig_request.sent_at = now

        elif event_type == "signature_request_viewed":
            sig_request.status = "viewed"
            sig_request.viewed_at = now

        elif event_type in ["signature_request_signed", "signature_request_all_signed"]:
            sig_request.status = "signed"
            sig_request.signed_at = now

            # Download and save signed document in background
            background_tasks.add_task(
                download_signed_document,
                signature_request_id,
                sig_request.id,
                sig_request.employee_id,
                sig_request.document_type,
                sig_request.document_title
            )

        elif event_type == "signature_request_declined":
            sig_request.status = "declined"

        db.commit()
        logger.info(f"Updated signature request {sig_request.id} to status: {sig_request.status}")

        return JSONResponse(content="Hello API Event Received", status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        # Return 200 to prevent Dropbox Sign from retrying
        return JSONResponse(content="OK", status_code=200)


async def download_signed_document(
    dropbox_signature_request_id: str,
    local_request_id: int,
    employee_id: int,
    document_type: str,
    document_title: str
):
    """Background task to download and save signed document."""
    from hr.db.database import SessionLocal

    db = SessionLocal()
    try:
        # Download the signed PDF
        pdf_content = await dropbox_sign_service.get_signature_request_files(
            dropbox_signature_request_id,
            file_type="pdf"
        )

        # Ensure directory exists
        employee_dir = os.path.join(SIGNED_DOCS_DIR, str(employee_id))
        os.makedirs(employee_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_signed_{document_type.replace(' ', '_')}.pdf"
        file_path = os.path.join(employee_dir, filename)

        # Save file
        with open(file_path, "wb") as f:
            f.write(pdf_content)

        # Create document record
        document = Document(
            employee_id=employee_id,
            document_type=f"{document_type} (Signed)",
            file_name=filename,
            file_path=file_path,
            file_size=len(pdf_content),
            mime_type="application/pdf",
            notes=f"E-signed document: {document_title}"
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Update signature request with document reference
        sig_request = db.query(SignatureRequest).filter(
            SignatureRequest.id == local_request_id
        ).first()
        if sig_request:
            sig_request.signed_document_id = document.id
            db.commit()

        logger.info(f"Saved signed document: {file_path}")

    except Exception as e:
        logger.error(f"Error downloading signed document: {e}")
    finally:
        db.close()


# ============ Template Endpoints ============

@router.get("/templates", response_model=List[SignatureTemplateResponse])
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all signature templates."""
    templates = db.query(SignatureTemplate).filter(
        SignatureTemplate.is_active == True
    ).all()
    return templates


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
        dropbox_template_id=template_data.dropbox_template_id,
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


@router.get("/dropbox-templates")
async def list_dropbox_templates(
    current_user: User = Depends(require_auth)
):
    """List templates from Dropbox Sign account."""
    try:
        response = await dropbox_sign_service.list_templates()
        return response
    except Exception as e:
        logger.error(f"Error listing Dropbox templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Create templates directory if it doesn't exist
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ").replace(" ", "_")
    filename = f"{timestamp}_{safe_name}.pdf"
    file_path = os.path.join(TEMPLATES_DIR, filename)

    # Save the file
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Error saving template file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Create database record
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

    # Update fields
    template.signature_fields = fields_data.get("fields", [])
    template.updated_at = datetime.utcnow()
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
