"""
API endpoints for document management
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
import os
import shutil

from hr.db.database import get_db
from hr.models.document import Document
from hr.models.employee import Employee as EmployeeModel
from hr.models.user import User
from hr.schemas.document import Document as DocumentSchema, DocumentUpdate, DocumentWithEmployee
from hr.api.auth import require_auth

router = APIRouter()

UPLOAD_DIR = "/app/documents"
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png', '.txt', '.xlsx', '.xls'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def update_document_status(document: Document):
    """Update document status based on expiration date"""
    if not document.expiration_date:
        document.status = "Current"
        return

    today = date.today()
    days_until_expiration = (document.expiration_date - today).days

    if days_until_expiration < 0:
        document.status = "Expired"
    elif days_until_expiration <= 30:
        document.status = "Expiring Soon"
    else:
        document.status = "Current"


@router.post("/employees/{employee_id}/documents", status_code=201)
async def upload_document(
    employee_id: int,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    expiration_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Upload a document for an employee (requires authentication)"""

    # Check if employee exists
    employee = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Validate file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {MAX_FILE_SIZE / 1024 / 1024}MB)"
        )

    # Create employee directory
    employee_dir = os.path.join(UPLOAD_DIR, str(employee_id))
    os.makedirs(employee_dir, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(employee_dir, safe_filename)

    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Parse expiration date
    exp_date = None
    if expiration_date:
        try:
            exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        except ValueError:
            # If parsing fails, ignore
            pass

    # Create database record
    document = Document(
        employee_id=employee_id,
        document_type=document_type,
        file_name=file.filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
        expiration_date=exp_date,
        notes=notes,
        uploaded_by=current_user.id
    )

    # Update status based on expiration
    update_document_status(document)

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


@router.get("/employees/{employee_id}/documents", response_model=List[DocumentSchema])
def list_employee_documents(employee_id: int, db: Session = Depends(get_db)):
    """List all documents for an employee"""

    # Check if employee exists
    employee = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    documents = db.query(Document).filter(
        Document.employee_id == employee_id
    ).order_by(Document.uploaded_at.desc()).all()

    # Update status for all documents
    for doc in documents:
        update_document_status(doc)

    db.commit()

    return documents


@router.get("/", response_model=List[DocumentWithEmployee])
def list_all_documents(
    skip: int = 0,
    limit: int = 100,
    document_type: Optional[str] = None,
    status: Optional[str] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """List all documents with optional filters (requires authentication)"""

    query = db.query(Document).join(EmployeeModel)

    if document_type:
        query = query.filter(Document.document_type == document_type)

    if status:
        query = query.filter(Document.status == status)

    if employee_id:
        query = query.filter(Document.employee_id == employee_id)

    documents = query.order_by(Document.uploaded_at.desc()).offset(skip).limit(limit).all()

    # Update status for all documents and prepare response with employee info
    results = []
    for doc in documents:
        update_document_status(doc)
        results.append({
            **DocumentSchema.from_orm(doc).dict(),
            'employee_name': f"{doc.employee.first_name} {doc.employee.last_name}",
            'employee_number': doc.employee.employee_number
        })

    db.commit()

    return results


@router.get("/expiring", response_model=List[DocumentSchema])
def list_expiring_documents(days: int = 30, db: Session = Depends(get_db)):
    """List documents expiring within specified days"""

    today = date.today()
    documents = db.query(Document).filter(
        Document.expiration_date.isnot(None),
        Document.expiration_date >= today
    ).all()

    # Filter and update status
    expiring = []
    for doc in documents:
        update_document_status(doc)
        days_until_exp = (doc.expiration_date - today).days
        if 0 <= days_until_exp <= days:
            expiring.append(doc)

    db.commit()

    return sorted(expiring, key=lambda x: x.expiration_date)


@router.get("/{document_id}", response_model=DocumentSchema)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document metadata by ID"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    update_document_status(document)
    db.commit()

    return document


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Download a document file (requires authentication, ID/SSN restricted to admins)"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Restrict ID and SSN documents to admins only
    restricted_types = ['ID Copy', 'Social Security Card']
    if document.document_type in restricted_types and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Only administrators can view ID and Social Security documents."
        )

    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        document.file_path,
        filename=document.file_name,
        media_type=document.mime_type
    )


@router.put("/{document_id}", response_model=DocumentSchema)
def update_document(
    document_id: int,
    document_update: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """Update document metadata"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update fields
    for key, value in document_update.dict(exclude_unset=True).items():
        setattr(document, key, value)

    # Update status based on new expiration date
    update_document_status(document)

    db.commit()
    db.refresh(document)

    return document


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete a document"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    if os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

    # Delete database record
    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}
