"""
Employees API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session, joinedload
from hr.db.database import get_db
from hr.schemas.employee import Employee, EmployeeCreate, EmployeeUpdate
from hr.models.employee import Employee as EmployeeModel
from hr.models.employee_position import EmployeePosition
from hr.models.location import Location
from hr.models.user import User
from hr.api.auth import require_auth
from hr.core.authorization import filter_by_user_locations, get_user_location_ids
from hr.core.audit import log_employee_create, log_employee_update, log_employee_view
from typing import List, Optional
from datetime import datetime
import csv
import io
from decimal import Decimal
import os
import shutil

router = APIRouter()


@router.post("/", response_model=Employee, status_code=201)
def create_employee(
    employee: EmployeeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Create a new employee (requires authentication)"""
    # Check if employee_number already exists
    existing = db.query(EmployeeModel).filter(
        EmployeeModel.employee_number == employee.employee_number
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Employee number {employee.employee_number} already exists"
        )

    # Check if email already exists
    existing_email = db.query(EmployeeModel).filter(
        EmployeeModel.email == employee.email
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=400,
            detail=f"Email {employee.email} already exists"
        )

    # Create employee (exclude create_inventory_user and location_ids fields)
    employee_data = employee.dict(exclude={'create_inventory_user', 'location_ids'})
    db_employee = EmployeeModel(**employee_data)

    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)

    # Assign locations to employee
    if employee.location_ids:
        from hr.models.location import Location
        for location_id in employee.location_ids:
            location = db.query(Location).filter(Location.id == location_id).first()
            if location:
                db_employee.assigned_locations.append(location)
        db.commit()
        db.refresh(db_employee)

    # Send new hire notification email
    try:
        from hr.services.email import send_new_hire_notification
        employee_dict = {
            'employee_number': db_employee.employee_number,
            'first_name': db_employee.first_name,
            'last_name': db_employee.last_name,
            'middle_name': db_employee.middle_name,
            'date_of_birth': str(db_employee.date_of_birth) if db_employee.date_of_birth else None,
            'email': db_employee.email,
            'phone_number': db_employee.phone_number,
            'street_address': db_employee.street_address,
            'city': db_employee.city,
            'state': db_employee.state,
            'zip_code': db_employee.zip_code,
            'emergency_contact_name': db_employee.emergency_contact_name,
            'emergency_contact_relationship': db_employee.emergency_contact_relationship,
            'emergency_contact_phone': db_employee.emergency_contact_phone,
            'hire_date': str(db_employee.hire_date),
            'employment_status': db_employee.employment_status,
            'employee_type': db_employee.employee_type,
            'starting_pay_rate': str(db_employee.starting_pay_rate) if db_employee.starting_pay_rate else None
        }
        created_by_info = f"{current_user.full_name} ({current_user.email})"
        send_new_hire_notification(employee_dict, created_by_info)
    except Exception as e:
        # Log error but don't fail the employee creation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send new hire notification: {str(e)}")

    # Audit log: Employee created
    try:
        log_employee_create(
            db=db,
            employee_id=db_employee.id,
            user_id=current_user.id,
            username=current_user.username,
            request=request
        )
    except Exception as e:
        # Log error but don't fail the employee creation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to log employee creation audit: {str(e)}")

    # TODO: Phase 5 - Create inventory user if create_inventory_user is True

    return db_employee


@router.get("/", response_model=List[Employee])
def list_employees(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    List all employees with optional filtering (filtered by user's assigned locations)

    Employees are filtered based on their position assignments.
    Users only see employees who have positions at locations they have access to.
    """
    # Get user's accessible location IDs
    location_ids = get_user_location_ids(current_user)

    # Build base query with position assignments
    query = db.query(EmployeeModel).outerjoin(
        EmployeePosition,
        EmployeeModel.id == EmployeePosition.employee_id
    ).options(
        joinedload(EmployeeModel.position_assignments)
    )

    # Apply location filtering
    if location_ids is not None:  # Not admin
        # Filter to employees with positions at accessible locations
        # OR employees with no positions (EmployeePosition.id is null)
        query = query.filter(
            (EmployeePosition.location_id.in_(location_ids)) |
            (EmployeePosition.id == None)
        )

    # Apply additional filters
    if status:
        query = query.filter(EmployeeModel.employment_status == status)

    if location_id:
        # Additional filter by specific location
        query = query.filter(EmployeePosition.location_id == location_id)

    # Distinct to avoid duplicates (employee with multiple positions)
    employees = query.distinct().offset(skip).limit(limit).all()
    return employees


@router.get("/{employee_id}", response_model=Employee)
def get_employee(
    employee_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get a specific employee by ID (only if user has access to their location)"""
    location_ids = get_user_location_ids(current_user)

    # Build query with location filtering and eager load assigned_locations
    query = db.query(EmployeeModel).options(
        joinedload(EmployeeModel.assigned_locations)
    ).filter(EmployeeModel.id == employee_id)

    # If not admin, verify user has access to at least one of employee's locations
    # OR employee has no positions assigned
    if location_ids is not None:
        query = query.outerjoin(
            EmployeePosition,
            EmployeeModel.id == EmployeePosition.employee_id
        ).filter(
            (EmployeePosition.location_id.in_(location_ids)) |
            (EmployeePosition.id == None)
        )

    employee = query.first()
    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found or you don't have access to their location"
        )

    # Audit log: Employee viewed (sensitive fields accessed)
    try:
        log_employee_view(
            db=db,
            employee_id=employee.id,
            user_id=current_user.id,
            username=current_user.username,
            request=request,
            viewed_sensitive_fields=True
        )
    except Exception as e:
        # Log error but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to log employee view audit: {str(e)}")

    return employee


@router.put("/{employee_id}", response_model=Employee)
def update_employee(
    employee_id: int,
    employee: EmployeeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Update an employee (requires authentication and location access)"""
    from hr.models.location import Location
    from hr.models.employee import employee_locations
    from sqlalchemy import or_

    location_ids = get_user_location_ids(current_user)

    # First, get the employee
    db_employee = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id).first()

    if not db_employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    # If not admin, verify user has access to at least one of the employee's locations
    if location_ids is not None:
        # Get employee's location IDs
        employee_location_ids = db.query(employee_locations.c.location_id).filter(
            employee_locations.c.employee_id == employee_id
        ).all()
        employee_location_ids = [loc[0] for loc in employee_location_ids]

        # Check if user has access: either employee has no locations OR user has access to at least one
        if employee_location_ids:  # Employee has locations assigned
            has_access = any(loc_id in location_ids for loc_id in employee_location_ids)
            if not has_access:
                raise HTTPException(
                    status_code=404,
                    detail="Employee not found or you don't have access to their location"
                )
        # If employee has no locations, allow any manager to edit (for setup purposes)

    # Check if being terminated
    was_terminated = False
    if employee.employment_status == "Terminated" and db_employee.employment_status != "Terminated":
        was_terminated = True
        if not employee.termination_date:
            # Auto-set termination date to today if not provided
            employee.termination_date = datetime.now().date()

        # TODO: Phase 5 - Sync termination to inventory (deactivate user)

    # Extract location_ids before updating other fields
    location_ids_to_assign = None
    update_data = employee.dict(exclude_unset=True)
    if 'location_ids' in update_data:
        location_ids_to_assign = update_data.pop('location_ids')

    # Update only provided fields (excluding location_ids)
    for key, value in update_data.items():
        setattr(db_employee, key, value)

    # Handle location assignments if provided
    if location_ids_to_assign is not None:
        from hr.models.location import Location
        # Clear existing location assignments
        db_employee.assigned_locations.clear()
        # Assign new locations
        for location_id in location_ids_to_assign:
            location = db.query(Location).filter(Location.id == location_id).first()
            if location:
                db_employee.assigned_locations.append(location)

    db.commit()
    db.refresh(db_employee)

    # Send termination notification email if employee was just terminated
    if was_terminated:
        try:
            from hr.services.email import send_termination_notification
            employee_dict = {
                'employee_number': db_employee.employee_number,
                'first_name': db_employee.first_name,
                'last_name': db_employee.last_name,
                'email': db_employee.email,
                'phone_number': db_employee.phone_number,
                'hire_date': str(db_employee.hire_date),
                'termination_date': str(db_employee.termination_date) if db_employee.termination_date else None,
                'termination_type': db_employee.termination_type,
                'termination_reason': db_employee.termination_reason,
                'final_decision_date': str(db_employee.final_decision_date) if db_employee.final_decision_date else None,
                'authorized_by': db_employee.authorized_by
            }
            processed_by_info = f"{current_user.full_name} ({current_user.email})"
            send_termination_notification(employee_dict, processed_by_info)
        except Exception as e:
            # Log error but don't fail the employee update
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send termination notification: {str(e)}")

    # Audit log: Employee updated
    try:
        log_employee_update(
            db=db,
            employee_id=db_employee.id,
            updated_fields=update_data,
            user_id=current_user.id,
            username=current_user.username,
            request=request
        )
    except Exception as e:
        # Log error but don't fail the update
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to log employee update audit: {str(e)}")

    return db_employee


@router.delete("/{employee_id}", status_code=204)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Delete an employee (soft delete by setting status to Terminated)
    Use with caution - consider using PUT to update status instead
    Requires authentication and location access
    """
    location_ids = get_user_location_ids(current_user)

    # Build query with location filtering
    query = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id)

    # If not admin, verify access
    if location_ids is not None:
        query = query.join(
            EmployeePosition,
            EmployeeModel.id == EmployeePosition.employee_id
        ).filter(EmployeePosition.location_id.in_(location_ids))

    db_employee = query.first()
    if not db_employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found or you don't have access to their location"
        )

    # Soft delete: set to terminated
    db_employee.employment_status = "Terminated"
    db_employee.termination_date = datetime.now().date()

    db.commit()
    return None


@router.post("/bulk-upload")
async def bulk_upload_employees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Bulk upload employees from CSV file

    CSV Format:
    employee_number,first_name,last_name,middle_name,email,phone_number,hire_date,employment_status,employee_type,starting_pay_rate,street_address,city,state,zip_code,emergency_contact_name,emergency_contact_relationship,emergency_contact_phone,date_of_birth,location_names

    location_names should be pipe-separated (e.g., "Seaside Grill|SW Grill")
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    # Read CSV file
    contents = await file.read()
    csv_data = contents.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(csv_data))

    results = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "errors": []
    }

    # Get all locations for mapping
    all_locations = db.query(Location).all()
    location_map = {loc.name: loc.id for loc in all_locations}

    for row_num, row in enumerate(csv_reader, start=2):  # start=2 because row 1 is headers
        results["total"] += 1

        try:
            # Parse location names
            location_ids = []
            if row.get('location_names'):
                location_names = [name.strip() for name in row['location_names'].split('|')]
                for loc_name in location_names:
                    if loc_name in location_map:
                        location_ids.append(location_map[loc_name])
                    else:
                        results["errors"].append(f"Row {row_num}: Unknown location '{loc_name}'")

            # Check if employee exists
            existing = db.query(EmployeeModel).filter(
                EmployeeModel.employee_number == row['employee_number']
            ).first()

            # Validate minimum required fields
            if not row.get('employee_number'):
                results["errors"].append(f"Row {row_num}: Missing employee_number")
                continue

            if not row.get('first_name'):
                results["errors"].append(f"Row {row_num}: Missing first_name")
                continue

            if not row.get('last_name'):
                results["errors"].append(f"Row {row_num}: Missing last_name")
                continue

            # Prepare employee data - all fields optional except employee_number, first_name, last_name
            employee_data = {
                'employee_number': row['employee_number'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'middle_name': row.get('middle_name') or None,
                'email': row.get('email') or None,
                'phone_number': row.get('phone_number') or None,
                'hire_date': datetime.strptime(row['hire_date'], '%Y-%m-%d').date() if row.get('hire_date') and row['hire_date'].strip() else None,
                'employment_status': row.get('employment_status', 'Active'),
                'employee_type': row.get('employee_type', 'Part-Time'),
                'starting_pay_rate': Decimal(row['starting_pay_rate']) if row.get('starting_pay_rate') and row['starting_pay_rate'].strip() else None,
                'street_address': row.get('street_address') or None,
                'city': row.get('city') or None,
                'state': row.get('state') or None,
                'zip_code': row.get('zip_code') or None,
                'emergency_contact_name': row.get('emergency_contact_name') or None,
                'emergency_contact_relationship': row.get('emergency_contact_relationship') or None,
                'emergency_contact_phone': row.get('emergency_contact_phone') or None,
                'date_of_birth': datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date() if row.get('date_of_birth') and row['date_of_birth'].strip() else None,
            }

            if existing:
                # Update existing employee
                for key, value in employee_data.items():
                    if key != 'employee_number':  # Don't update employee number
                        setattr(existing, key, value)

                # Update locations
                if location_ids:
                    existing.assigned_locations.clear()
                    for loc_id in location_ids:
                        location = db.query(Location).filter(Location.id == loc_id).first()
                        if location:
                            existing.assigned_locations.append(location)

                results["updated"] += 1
            else:
                # Create new employee
                db_employee = EmployeeModel(**employee_data)
                db.add(db_employee)
                db.flush()  # Get the ID

                # Assign locations
                if location_ids:
                    for loc_id in location_ids:
                        location = db.query(Location).filter(Location.id == loc_id).first()
                        if location:
                            db_employee.assigned_locations.append(location)

                results["created"] += 1

            db.commit()

        except Exception as e:
            results["errors"].append(f"Row {row_num} ({row.get('employee_number', 'unknown')}): {str(e)}")
            db.rollback()
            continue

    return results


@router.get("/{employee_id}/documents")
async def get_employee_documents(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Get all documents for a specific employee"""
    from hr.models.document import Document
    from datetime import date

    # Check if employee exists
    employee = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Get documents
    documents = db.query(Document).filter(
        Document.employee_id == employee_id
    ).order_by(Document.uploaded_at.desc()).all()

    # Update document statuses
    def update_document_status(document):
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

    for doc in documents:
        update_document_status(doc)

    db.commit()

    # Return documents as dict
    return [{
        "id": doc.id,
        "employee_id": doc.employee_id,
        "document_type": doc.document_type,
        "file_name": doc.file_name,
        "file_path": doc.file_path,
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
        "status": doc.status,
        "notes": doc.notes
    } for doc in documents]


@router.post("/{employee_id}/documents")
async def upload_employee_document(
    employee_id: int,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    expiration_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Upload a document for an employee"""
    from hr.models.document import Document

    UPLOAD_DIR = "/app/documents"
    ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png', '.txt', '.xlsx', '.xls'}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

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
    from datetime import date
    exp_date = None
    if expiration_date:
        try:
            exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        except ValueError:
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

    # Set initial status
    if not exp_date:
        document.status = "Current"
    else:
        today = date.today()
        days_until_expiration = (exp_date - today).days
        if days_until_expiration < 0:
            document.status = "Expired"
        elif days_until_expiration <= 30:
            document.status = "Expiring Soon"
        else:
            document.status = "Current"

    db.add(document)
    db.commit()
    db.refresh(document)

    return {
        "id": document.id,
        "employee_id": document.employee_id,
        "document_type": document.document_type,
        "file_name": document.file_name,
        "status": document.status,
        "message": "Document uploaded successfully"
    }
