"""API endpoints for HR Forms (Corrective Action and First Report of Injury)"""
import logging
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field

from hr.db.database import get_db
from hr.models import (
    User, Employee, Document, Location,
    CorrectiveAction, FirstReportOfInjury,
    DisciplinaryLevel, FinalWarningType, CorrectiveActionSubject,
    FormStatus, InjuryBodyPart, InjuryType
)
from hr.api.auth import get_current_user
from hr.services.email import send_corrective_action_notification, send_injury_report_notification

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ Pydantic Schemas ============

class PriorNotification(BaseModel):
    level: str
    date: Optional[str] = None
    subject: Optional[str] = None


class CorrectiveActionCreate(BaseModel):
    employee_id: int
    location_id: int
    disciplinary_level: str
    final_warning_type: Optional[str] = None
    subject: str
    prior_notifications: Optional[List[PriorNotification]] = None
    incident_description: str
    incident_date: str
    incident_time: Optional[str] = None
    incident_location: Optional[str] = None
    persons_present: Optional[str] = None
    organizational_impact: Optional[str] = None
    improvement_goals: Optional[str] = None
    training_provided: Optional[str] = None
    interim_evaluation_needed: bool = False
    personal_improvement_input: Optional[str] = None
    positive_outcome: Optional[str] = None
    negative_outcome: Optional[str] = None
    scheduled_review_date: Optional[str] = None


class CorrectiveActionUpdate(BaseModel):
    disciplinary_level: Optional[str] = None
    final_warning_type: Optional[str] = None
    subject: Optional[str] = None
    prior_notifications: Optional[List[PriorNotification]] = None
    incident_description: Optional[str] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None
    incident_location: Optional[str] = None
    persons_present: Optional[str] = None
    organizational_impact: Optional[str] = None
    improvement_goals: Optional[str] = None
    training_provided: Optional[str] = None
    interim_evaluation_needed: Optional[bool] = None
    personal_improvement_input: Optional[str] = None
    positive_outcome: Optional[str] = None
    negative_outcome: Optional[str] = None
    scheduled_review_date: Optional[str] = None
    employee_comments: Optional[str] = None


class SignatureSubmit(BaseModel):
    signature: str  # Base64 PNG
    typed_name: str


class InjuryReportCreate(BaseModel):
    employee_id: int
    location_id: int
    accident_date: str
    accident_time: Optional[str] = None
    accident_am_pm: Optional[str] = None
    accident_description: str
    injury_type: str
    injury_description: Optional[str] = None
    body_part: str
    body_part_detail: Optional[str] = None
    accident_street: Optional[str] = None
    accident_city: Optional[str] = None
    accident_state: Optional[str] = None
    accident_zip: Optional[str] = None
    accident_county: Optional[str] = None
    date_employed: Optional[str] = None
    paid_for_injury_date: bool = False
    last_date_worked: Optional[str] = None
    returned_to_work: bool = False
    return_to_work_date: Optional[str] = None
    rate_of_pay: Optional[str] = None
    pay_period: Optional[str] = None
    hours_per_day: Optional[str] = None
    hours_per_week: Optional[str] = None
    days_per_week: Optional[str] = None
    physician_name: Optional[str] = None
    physician_address: Optional[str] = None
    physician_phone: Optional[str] = None
    hospital_name: Optional[str] = None
    treatment_authorized_by_employer: bool = True


class InjuryReportUpdate(BaseModel):
    accident_date: Optional[str] = None
    accident_time: Optional[str] = None
    accident_am_pm: Optional[str] = None
    accident_description: Optional[str] = None
    injury_type: Optional[str] = None
    injury_description: Optional[str] = None
    body_part: Optional[str] = None
    body_part_detail: Optional[str] = None
    accident_street: Optional[str] = None
    accident_city: Optional[str] = None
    accident_state: Optional[str] = None
    accident_zip: Optional[str] = None
    accident_county: Optional[str] = None
    paid_for_injury_date: Optional[bool] = None
    last_date_worked: Optional[str] = None
    returned_to_work: Optional[bool] = None
    return_to_work_date: Optional[str] = None
    rate_of_pay: Optional[str] = None
    pay_period: Optional[str] = None
    hours_per_day: Optional[str] = None
    hours_per_week: Optional[str] = None
    days_per_week: Optional[str] = None
    physician_name: Optional[str] = None
    physician_address: Optional[str] = None
    physician_phone: Optional[str] = None
    hospital_name: Optional[str] = None
    treatment_authorized_by_employer: Optional[bool] = None
    employer_agrees_with_description: Optional[bool] = None
    employer_disagreement_notes: Optional[str] = None
    will_continue_wages: Optional[bool] = None
    last_day_wages_paid: Optional[str] = None


# ============ Helper Functions ============

def generate_ca_reference(db: Session) -> str:
    """Generate next Corrective Action reference number (CA-YYYY-NNNN)"""
    year = datetime.now().year
    prefix = f"CA-{year}-"

    last = db.query(CorrectiveAction).filter(
        CorrectiveAction.reference_number.like(f"{prefix}%")
    ).order_by(CorrectiveAction.id.desc()).first()

    if last:
        try:
            last_num = int(last.reference_number.split("-")[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f"{prefix}{next_num:04d}"


def generate_injury_reference(db: Session) -> str:
    """Generate next Injury Report reference number (INJ-YYYY-NNNN)"""
    year = datetime.now().year
    prefix = f"INJ-{year}-"

    last = db.query(FirstReportOfInjury).filter(
        FirstReportOfInjury.reference_number.like(f"{prefix}%")
    ).order_by(FirstReportOfInjury.id.desc()).first()

    if last:
        try:
            last_num = int(last.reference_number.split("-")[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f"{prefix}{next_num:04d}"


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ============ Corrective Action Endpoints ============

@router.get("/corrective-actions")
async def list_corrective_actions(
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all corrective actions, optionally filtered by employee or status"""
    query = db.query(CorrectiveAction)

    if employee_id:
        query = query.filter(CorrectiveAction.employee_id == employee_id)
    if status:
        query = query.filter(CorrectiveAction.status == status)

    actions = query.order_by(CorrectiveAction.created_at.desc()).all()

    return [{
        "id": a.id,
        "reference_number": a.reference_number,
        "employee_id": a.employee_id,
        "employee_name": f"{a.employee.first_name} {a.employee.last_name}" if a.employee else None,
        "disciplinary_level": a.disciplinary_level,
        "subject": a.subject,
        "date_of_action": a.incident_date.isoformat() if a.incident_date else None,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in actions]


@router.get("/corrective-actions/employee/{employee_id}")
async def list_corrective_actions_by_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all corrective actions for a specific employee"""
    actions = db.query(CorrectiveAction).filter(
        CorrectiveAction.employee_id == employee_id
    ).order_by(CorrectiveAction.created_at.desc()).all()

    return [{
        "id": a.id,
        "reference_number": a.reference_number,
        "employee_id": a.employee_id,
        "disciplinary_level": a.disciplinary_level.value if a.disciplinary_level else None,
        "subject": a.subject.value if a.subject else None,
        "date_of_action": a.incident_date.isoformat() if a.incident_date else None,
        "status": a.status.value if a.status else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in actions]


@router.get("/corrective-actions/{action_id}")
async def get_corrective_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific corrective action by ID"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    employee = action.employee

    return {
        "id": action.id,
        "reference_number": action.reference_number,
        "employee_id": action.employee_id,
        "employee_name": f"{employee.first_name} {employee.last_name}" if employee else None,
        "employee_number": employee.employee_number if employee else None,
        "location_id": action.location_id,
        "disciplinary_level": action.disciplinary_level,
        "final_warning_type": action.final_warning_type,
        "subject": action.subject,
        "prior_notifications": action.prior_notifications,
        "incident_description": action.incident_description,
        "incident_date": action.incident_date.isoformat() if action.incident_date else None,
        "incident_time": action.incident_time,
        "incident_location": action.incident_location,
        "persons_present": action.persons_present,
        "organizational_impact": action.organizational_impact,
        "improvement_goals": action.improvement_goals,
        "training_provided": action.training_provided,
        "interim_evaluation_needed": action.interim_evaluation_needed,
        "personal_improvement_input": action.personal_improvement_input,
        "positive_outcome": action.positive_outcome,
        "negative_outcome": action.negative_outcome,
        "scheduled_review_date": action.scheduled_review_date.isoformat() if action.scheduled_review_date else None,
        "employee_comments": action.employee_comments,
        "status": action.status,
        "employee_signature": action.employee_signature is not None,
        "employee_signature_date": action.employee_signature_date.isoformat() if action.employee_signature_date else None,
        "employee_typed_name": action.employee_typed_name,
        "supervisor_signature": action.supervisor_signature is not None,
        "supervisor_signature_date": action.supervisor_signature_date.isoformat() if action.supervisor_signature_date else None,
        "supervisor_typed_name": action.supervisor_typed_name,
        "witness_name": action.witness_name,
        "witness_signature": action.witness_signature is not None,
        "witness_date": action.witness_date.isoformat() if action.witness_date else None,
        "supervisor_id": action.supervisor_id,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "updated_at": action.updated_at.isoformat() if action.updated_at else None,
    }


@router.post("/corrective-actions")
async def create_corrective_action(
    data: CorrectiveActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new corrective action"""
    # Verify employee exists
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    reference = generate_ca_reference(db)

    action = CorrectiveAction(
        reference_number=reference,
        employee_id=data.employee_id,
        location_id=data.location_id,
        disciplinary_level=data.disciplinary_level,
        final_warning_type=data.final_warning_type,
        subject=data.subject,
        prior_notifications=[n.dict() for n in data.prior_notifications] if data.prior_notifications else None,
        incident_description=data.incident_description,
        incident_date=parse_date(data.incident_date),
        incident_time=data.incident_time,
        incident_location=data.incident_location,
        persons_present=data.persons_present,
        organizational_impact=data.organizational_impact,
        improvement_goals=data.improvement_goals,
        training_provided=data.training_provided,
        interim_evaluation_needed=data.interim_evaluation_needed,
        personal_improvement_input=data.personal_improvement_input,
        positive_outcome=data.positive_outcome or "If you meet the company's and your own performance goals, no further disciplinary action will be taken regarding this issue.",
        negative_outcome=data.negative_outcome,
        scheduled_review_date=parse_date(data.scheduled_review_date),
        status=FormStatus.DRAFT,
        supervisor_id=current_user.id,
        created_by=current_user.id,
    )

    db.add(action)
    db.commit()
    db.refresh(action)

    logger.info(f"Created corrective action {reference} for employee {data.employee_id}")

    return {
        "id": action.id,
        "reference_number": action.reference_number,
        "message": "Corrective action created successfully"
    }


@router.put("/corrective-actions/{action_id}")
async def update_corrective_action(
    action_id: int,
    data: CorrectiveActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a corrective action"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status == FormStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Cannot edit completed corrective action")

    update_data = data.dict(exclude_unset=True)

    # Handle date fields
    date_fields = ['incident_date', 'scheduled_review_date']
    for field in date_fields:
        if field in update_data and update_data[field]:
            update_data[field] = parse_date(update_data[field])

    # Handle prior_notifications
    if 'prior_notifications' in update_data and update_data['prior_notifications']:
        update_data['prior_notifications'] = [n.dict() if hasattr(n, 'dict') else n for n in update_data['prior_notifications']]

    for key, value in update_data.items():
        setattr(action, key, value)

    action.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Corrective action updated successfully"}


@router.post("/corrective-actions/{action_id}/send-for-signature")
async def send_ca_for_signature(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send corrective action for employee signature"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status not in [FormStatus.DRAFT]:
        raise HTTPException(status_code=400, detail="Form is not in draft status")

    action.status = FormStatus.PENDING_EMPLOYEE_SIGNATURE
    action.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Corrective action sent for employee signature"}


@router.post("/corrective-actions/{action_id}/employee-sign")
async def employee_sign_ca(
    action_id: int,
    data: SignatureSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Employee signs corrective action"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status != FormStatus.PENDING_EMPLOYEE_SIGNATURE:
        raise HTTPException(status_code=400, detail="Form is not pending employee signature")

    action.employee_signature = data.signature
    action.employee_signature_date = datetime.utcnow()
    action.employee_typed_name = data.typed_name
    action.employee_signature_ip = get_client_ip(request)
    action.employee_signature_user_agent = request.headers.get("User-Agent", "")[:500]
    action.status = FormStatus.PENDING_SUPERVISOR_SIGNATURE
    action.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Employee signature recorded"}


@router.post("/corrective-actions/{action_id}/employee-refuse")
async def employee_refuse_ca(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark that employee refused to sign"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    action.status = FormStatus.EMPLOYEE_REFUSED
    action.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Employee refusal recorded. Witness signature required."}


@router.post("/corrective-actions/{action_id}/witness-sign")
async def witness_sign_ca(
    action_id: int,
    data: SignatureSubmit,
    witness_name: str,
    conference_time: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Witness signs corrective action (when employee refuses)"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status != FormStatus.EMPLOYEE_REFUSED:
        raise HTTPException(status_code=400, detail="Witness signature only needed when employee refuses")

    action.witness_name = witness_name
    action.witness_signature = data.signature
    action.witness_date = datetime.utcnow()
    action.witness_typed_name = data.typed_name
    action.witness_conference_time = conference_time
    action.witness_signature_ip = get_client_ip(request)
    action.status = FormStatus.PENDING_SUPERVISOR_SIGNATURE
    action.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Witness signature recorded"}


@router.post("/corrective-actions/{action_id}/supervisor-sign")
async def supervisor_sign_ca(
    action_id: int,
    data: SignatureSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Supervisor signs corrective action (completes the form)"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status != FormStatus.PENDING_SUPERVISOR_SIGNATURE:
        raise HTTPException(status_code=400, detail="Form is not pending supervisor signature")

    action.supervisor_signature = data.signature
    action.supervisor_signature_date = datetime.utcnow()
    action.supervisor_typed_name = data.typed_name
    action.supervisor_signature_ip = get_client_ip(request)
    action.supervisor_signature_user_agent = request.headers.get("User-Agent", "")[:500]
    action.status = FormStatus.COMPLETED
    action.updated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Corrective action {action.reference_number} completed")

    # Send email notification
    try:
        employee = action.employee
        location = db.query(Location).filter(Location.id == action.location_id).first()

        send_corrective_action_notification(
            employee_name=f"{employee.first_name} {employee.last_name}" if employee else "Unknown",
            employee_number=employee.employee_number if employee else "N/A",
            reference_number=action.reference_number,
            disciplinary_level=action.disciplinary_level or "N/A",
            subject=action.subject or "N/A",
            incident_date=action.incident_date.isoformat() if action.incident_date else "N/A",
            incident_description=action.incident_description or "No description provided",
            location_name=location.name if location else "N/A",
            supervisor_name=data.typed_name,
            completed_by=current_user.full_name
        )
    except Exception as e:
        logger.error(f"Failed to send corrective action email notification: {e}")

    return {"message": "Corrective action completed"}


@router.post("/corrective-actions/{action_id}/add-comments")
async def add_employee_comments(
    action_id: int,
    comments: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add employee comments/rebuttal"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    action.employee_comments = comments
    action.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Comments added"}


# ============ First Report of Injury Endpoints ============

@router.get("/injury-reports")
async def list_injury_reports(
    employee_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all injury reports, optionally filtered by employee or status"""
    query = db.query(FirstReportOfInjury)

    if employee_id:
        query = query.filter(FirstReportOfInjury.employee_id == employee_id)
    if status:
        query = query.filter(FirstReportOfInjury.status == status)

    reports = query.order_by(FirstReportOfInjury.created_at.desc()).all()

    return [{
        "id": r.id,
        "reference_number": r.reference_number,
        "employee_id": r.employee_id,
        "employee_name": f"{r.employee.first_name} {r.employee.last_name}" if r.employee else None,
        "date_of_injury": r.accident_date.isoformat() if r.accident_date else None,
        "injury_type": r.injury_type.value if r.injury_type else None,
        "body_part_affected": r.body_part.value if r.body_part else None,
        "status": r.status.value if r.status else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reports]


@router.get("/injury-reports/employee/{employee_id}")
async def list_injury_reports_by_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all injury reports for a specific employee"""
    reports = db.query(FirstReportOfInjury).filter(
        FirstReportOfInjury.employee_id == employee_id
    ).order_by(FirstReportOfInjury.created_at.desc()).all()

    return [{
        "id": r.id,
        "reference_number": r.reference_number,
        "employee_id": r.employee_id,
        "date_of_injury": r.accident_date.isoformat() if r.accident_date else None,
        "injury_type": r.injury_type.value if r.injury_type else None,
        "body_part_affected": r.body_part.value if r.body_part else None,
        "status": r.status.value if r.status else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reports]


@router.get("/injury-reports/{report_id}")
async def get_injury_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific injury report by ID"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    employee = report.employee

    return {
        "id": report.id,
        "reference_number": report.reference_number,
        "employee_id": report.employee_id,
        "employee_name": f"{employee.first_name} {employee.last_name}" if employee else None,
        "employee_number": employee.employee_number if employee else None,
        "employee_ssn_last4": employee.ssn[-4:] if employee and employee.ssn else None,
        "employee_dob": employee.date_of_birth.isoformat() if employee and employee.date_of_birth else None,
        "employee_address": f"{employee.street_address}, {employee.city}, {employee.state} {employee.zip_code}" if employee else None,
        "employee_phone": employee.phone_number if employee else None,
        "employee_occupation": employee.position.title if employee and employee.position else None,
        "accident_date": report.accident_date.isoformat() if report.accident_date else None,
        "accident_time": report.accident_time,
        "accident_am_pm": report.accident_am_pm,
        "accident_description": report.accident_description,
        "injury_type": report.injury_type,
        "injury_description": report.injury_description,
        "body_part": report.body_part,
        "body_part_detail": report.body_part_detail,
        "location_id": report.location_id,
        "accident_street": report.accident_street,
        "accident_city": report.accident_city,
        "accident_state": report.accident_state,
        "accident_zip": report.accident_zip,
        "accident_county": report.accident_county,
        "date_employed": report.date_employed.isoformat() if report.date_employed else None,
        "paid_for_injury_date": report.paid_for_injury_date,
        "last_date_worked": report.last_date_worked.isoformat() if report.last_date_worked else None,
        "returned_to_work": report.returned_to_work,
        "return_to_work_date": report.return_to_work_date.isoformat() if report.return_to_work_date else None,
        "rate_of_pay": report.rate_of_pay,
        "pay_period": report.pay_period,
        "hours_per_day": report.hours_per_day,
        "hours_per_week": report.hours_per_week,
        "days_per_week": report.days_per_week,
        "physician_name": report.physician_name,
        "physician_address": report.physician_address,
        "physician_phone": report.physician_phone,
        "hospital_name": report.hospital_name,
        "treatment_authorized_by_employer": report.treatment_authorized_by_employer,
        "employer_agrees_with_description": report.employer_agrees_with_description,
        "employer_disagreement_notes": report.employer_disagreement_notes,
        "will_continue_wages": report.will_continue_wages,
        "last_day_wages_paid": report.last_day_wages_paid.isoformat() if report.last_day_wages_paid else None,
        "date_of_death": report.date_of_death.isoformat() if report.date_of_death else None,
        "status": report.status,
        "employee_signature": report.employee_signature is not None,
        "employee_signature_date": report.employee_signature_date.isoformat() if report.employee_signature_date else None,
        "employee_typed_name": report.employee_typed_name,
        "employer_signature": report.employer_signature is not None,
        "employer_signature_date": report.employer_signature_date.isoformat() if report.employer_signature_date else None,
        "employer_typed_name": report.employer_typed_name,
        "date_first_reported": report.date_first_reported.isoformat() if report.date_first_reported else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


@router.post("/injury-reports")
async def create_injury_report(
    data: InjuryReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new injury report"""
    # Verify employee exists
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    reference = generate_injury_reference(db)

    report = FirstReportOfInjury(
        reference_number=reference,
        employee_id=data.employee_id,
        location_id=data.location_id,
        accident_date=parse_date(data.accident_date),
        accident_time=data.accident_time,
        accident_am_pm=data.accident_am_pm,
        accident_description=data.accident_description,
        injury_type=data.injury_type,
        injury_description=data.injury_description,
        body_part=data.body_part,
        body_part_detail=data.body_part_detail,
        accident_street=data.accident_street,
        accident_city=data.accident_city,
        accident_state=data.accident_state,
        accident_zip=data.accident_zip,
        accident_county=data.accident_county,
        date_employed=parse_date(data.date_employed) or employee.hire_date,
        paid_for_injury_date=data.paid_for_injury_date,
        last_date_worked=parse_date(data.last_date_worked),
        returned_to_work=data.returned_to_work,
        return_to_work_date=parse_date(data.return_to_work_date),
        rate_of_pay=data.rate_of_pay,
        pay_period=data.pay_period,
        hours_per_day=data.hours_per_day,
        hours_per_week=data.hours_per_week,
        days_per_week=data.days_per_week,
        physician_name=data.physician_name,
        physician_address=data.physician_address,
        physician_phone=data.physician_phone,
        hospital_name=data.hospital_name,
        treatment_authorized_by_employer=data.treatment_authorized_by_employer,
        date_first_reported=date.today(),
        status=FormStatus.DRAFT,
        created_by=current_user.id,
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(f"Created injury report {reference} for employee {data.employee_id}")

    return {
        "id": report.id,
        "reference_number": report.reference_number,
        "message": "Injury report created successfully"
    }


@router.put("/injury-reports/{report_id}")
async def update_injury_report(
    report_id: int,
    data: InjuryReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an injury report"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    if report.status == FormStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Cannot edit completed injury report")

    update_data = data.dict(exclude_unset=True)

    # Handle date fields
    date_fields = ['accident_date', 'last_date_worked', 'return_to_work_date', 'last_day_wages_paid']
    for field in date_fields:
        if field in update_data and update_data[field]:
            update_data[field] = parse_date(update_data[field])

    for key, value in update_data.items():
        setattr(report, key, value)

    report.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Injury report updated successfully"}


@router.post("/injury-reports/{report_id}/send-for-signature")
async def send_injury_for_signature(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send injury report for employee signature"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    if report.status not in [FormStatus.DRAFT]:
        raise HTTPException(status_code=400, detail="Report is not in draft status")

    report.status = FormStatus.PENDING_EMPLOYEE_SIGNATURE
    report.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Injury report sent for employee signature"}


@router.post("/injury-reports/{report_id}/employee-sign")
async def employee_sign_injury(
    report_id: int,
    data: SignatureSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Employee signs injury report"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    if report.status != FormStatus.PENDING_EMPLOYEE_SIGNATURE:
        raise HTTPException(status_code=400, detail="Report is not pending employee signature")

    report.employee_signature = data.signature
    report.employee_signature_date = datetime.utcnow()
    report.employee_typed_name = data.typed_name
    report.employee_signature_ip = get_client_ip(request)
    report.employee_signature_user_agent = request.headers.get("User-Agent", "")[:500]
    report.status = FormStatus.PENDING_SUPERVISOR_SIGNATURE
    report.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Employee signature recorded"}


@router.post("/injury-reports/{report_id}/employer-sign")
async def employer_sign_injury(
    report_id: int,
    data: SignatureSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Employer signs injury report (completes the form)"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    if report.status != FormStatus.PENDING_SUPERVISOR_SIGNATURE:
        raise HTTPException(status_code=400, detail="Report is not pending employer signature")

    report.employer_signature = data.signature
    report.employer_signature_date = datetime.utcnow()
    report.employer_typed_name = data.typed_name
    report.employer_signature_ip = get_client_ip(request)
    report.employer_signature_user_agent = request.headers.get("User-Agent", "")[:500]
    report.employer_signer_id = current_user.id
    report.status = FormStatus.COMPLETED
    report.updated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Injury report {report.reference_number} completed")

    # Send email notification
    try:
        employee = report.employee
        location = db.query(Location).filter(Location.id == report.location_id).first()

        send_injury_report_notification(
            employee_name=f"{employee.first_name} {employee.last_name}" if employee else "Unknown",
            employee_number=employee.employee_number if employee else "N/A",
            reference_number=report.reference_number,
            accident_date=report.accident_date.isoformat() if report.accident_date else "N/A",
            injury_type=report.injury_type or "N/A",
            body_part=report.body_part or "N/A",
            accident_description=report.accident_description or "No description provided",
            location_name=location.name if location else "N/A",
            completed_by=current_user.full_name
        )
    except Exception as e:
        logger.error(f"Failed to send injury report email notification: {e}")

    return {"message": "Injury report completed"}


@router.delete("/corrective-actions/{action_id}")
async def delete_corrective_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a draft corrective action"""
    action = db.query(CorrectiveAction).filter(CorrectiveAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    if action.status != FormStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft forms can be deleted")

    db.delete(action)
    db.commit()

    return {"message": "Corrective action deleted"}


@router.delete("/injury-reports/{report_id}")
async def delete_injury_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a draft injury report"""
    report = db.query(FirstReportOfInjury).filter(FirstReportOfInjury.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Injury report not found")

    if report.status != FormStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft forms can be deleted")

    db.delete(report)
    db.commit()

    return {"message": "Injury report deleted"}
