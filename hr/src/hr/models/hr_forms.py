"""HR Forms models - Corrective Action and First Report of Injury"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Date, Enum, Index, JSON
)
from sqlalchemy.orm import relationship
from hr.db.database import Base


class DisciplinaryLevel(str, PyEnum):
    """Disciplinary levels for corrective action"""
    VERBAL = "verbal"
    WRITTEN = "written"
    FINAL_WRITTEN = "final_written"


class FinalWarningType(str, PyEnum):
    """Types of final written warning"""
    WITHOUT_LEAVE = "without_decision_making_leave"
    WITH_LEAVE = "with_decision_making_leave"
    WITH_SUSPENSION = "with_unpaid_suspension"


class CorrectiveActionSubject(str, PyEnum):
    """Subject categories for corrective action"""
    POLICY_VIOLATION = "policy_violation"
    PERFORMANCE = "performance"
    BEHAVIOR_CONDUCT = "behavior_conduct"
    ATTENDANCE = "attendance"


class FormStatus(str, PyEnum):
    """Status of HR forms"""
    DRAFT = "draft"
    PENDING_EMPLOYEE_SIGNATURE = "pending_employee_signature"
    PENDING_SUPERVISOR_SIGNATURE = "pending_supervisor_signature"
    EMPLOYEE_REFUSED = "employee_refused"
    COMPLETED = "completed"


class CorrectiveAction(Base):
    """Employee Corrective Action Notice"""
    __tablename__ = "corrective_actions"

    id = Column(Integer, primary_key=True, index=True)

    # Reference number (CA-YYYY-NNNN)
    reference_number = Column(String(20), nullable=False, unique=True, index=True)

    # Employee being disciplined
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    # Location where incident occurred
    location_id = Column(Integer, nullable=False, index=True)

    # Disciplinary level
    disciplinary_level = Column(Enum(DisciplinaryLevel), nullable=False)
    final_warning_type = Column(Enum(FinalWarningType), nullable=True)  # Only if final_written

    # Subject of corrective action
    subject = Column(Enum(CorrectiveActionSubject), nullable=False)

    # Prior notification history (JSON array of {level, date, subject})
    prior_notifications = Column(JSON, nullable=True)

    # Incident description
    incident_description = Column(Text, nullable=False)
    incident_date = Column(Date, nullable=False)
    incident_time = Column(String(10), nullable=True)
    incident_location = Column(String(200), nullable=True)
    persons_present = Column(Text, nullable=True)
    organizational_impact = Column(Text, nullable=True)

    # Performance Improvement Plan
    improvement_goals = Column(Text, nullable=True)
    training_provided = Column(Text, nullable=True)
    interim_evaluation_needed = Column(Boolean, default=False)
    personal_improvement_input = Column(Text, nullable=True)

    # Outcomes and Consequences
    positive_outcome = Column(Text, default="If you meet the company's and your own performance goals, no further disciplinary action will be taken regarding this issue.")
    negative_outcome = Column(Text, nullable=True)

    # Review
    scheduled_review_date = Column(Date, nullable=True)

    # Employee comments/rebuttal
    employee_comments = Column(Text, nullable=True)

    # Status
    status = Column(Enum(FormStatus), default=FormStatus.DRAFT, nullable=False)

    # Signatures (stored as base64 PNG)
    employee_signature = Column(Text, nullable=True)
    employee_signature_date = Column(DateTime, nullable=True)
    employee_typed_name = Column(String(200), nullable=True)  # Typed name for verification
    employee_signature_ip = Column(String(50), nullable=True)
    employee_signature_user_agent = Column(String(500), nullable=True)

    supervisor_signature = Column(Text, nullable=True)
    supervisor_signature_date = Column(DateTime, nullable=True)
    supervisor_typed_name = Column(String(200), nullable=True)
    supervisor_signature_ip = Column(String(50), nullable=True)
    supervisor_signature_user_agent = Column(String(500), nullable=True)

    witness_name = Column(String(200), nullable=True)  # If employee refuses to sign
    witness_signature = Column(Text, nullable=True)
    witness_date = Column(DateTime, nullable=True)
    witness_conference_time = Column(String(50), nullable=True)
    witness_typed_name = Column(String(200), nullable=True)
    witness_signature_ip = Column(String(50), nullable=True)

    # Supervisor who issued the corrective action
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # PDF document reference (after completion)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    creator = relationship("User", foreign_keys=[created_by])
    document = relationship("Document", foreign_keys=[document_id])

    __table_args__ = (
        Index("ix_corrective_actions_employee", "employee_id"),
        Index("ix_corrective_actions_status", "status"),
        Index("ix_corrective_actions_date", "incident_date"),
    )


class InjuryBodyPart(str, PyEnum):
    """Body parts for injury reporting"""
    HEAD = "head"
    FACE = "face"
    EYE = "eye"
    EAR = "ear"
    NECK = "neck"
    SHOULDER = "shoulder"
    ARM = "arm"
    ELBOW = "elbow"
    WRIST = "wrist"
    HAND = "hand"
    FINGER = "finger"
    CHEST = "chest"
    BACK_UPPER = "back_upper"
    BACK_LOWER = "back_lower"
    ABDOMEN = "abdomen"
    HIP = "hip"
    LEG = "leg"
    KNEE = "knee"
    ANKLE = "ankle"
    FOOT = "foot"
    TOE = "toe"
    MULTIPLE = "multiple"
    OTHER = "other"


class InjuryType(str, PyEnum):
    """Types of injuries"""
    CUT_LACERATION = "cut_laceration"
    BURN = "burn"
    SPRAIN_STRAIN = "sprain_strain"
    FRACTURE = "fracture"
    CONTUSION_BRUISE = "contusion_bruise"
    PUNCTURE = "puncture"
    AMPUTATION = "amputation"
    CRUSH = "crush"
    FOREIGN_BODY = "foreign_body"
    CHEMICAL_EXPOSURE = "chemical_exposure"
    RESPIRATORY = "respiratory"
    HEAT_COLD = "heat_cold"
    ELECTRIC_SHOCK = "electric_shock"
    SLIP_FALL = "slip_fall"
    REPETITIVE_MOTION = "repetitive_motion"
    OTHER = "other"


class FirstReportOfInjury(Base):
    """Florida First Report of Injury or Illness (DWC-1)"""
    __tablename__ = "first_report_of_injury"

    id = Column(Integer, primary_key=True, index=True)

    # Reference number (INJ-YYYY-NNNN)
    reference_number = Column(String(20), nullable=False, unique=True, index=True)

    # Employee Information
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    # Accident details
    accident_date = Column(Date, nullable=False, index=True)
    accident_time = Column(String(10), nullable=True)
    accident_am_pm = Column(String(2), nullable=True)  # AM or PM

    # Employee's description of accident
    accident_description = Column(Text, nullable=False)

    # Injury details
    injury_type = Column(Enum(InjuryType), nullable=False)
    injury_description = Column(String(500), nullable=True)  # Free text for specifics
    body_part = Column(Enum(InjuryBodyPart), nullable=False)
    body_part_detail = Column(String(200), nullable=True)  # e.g., "left index finger"

    # Employer Information (location where injury occurred)
    location_id = Column(Integer, nullable=False, index=True)

    # Place of accident (may differ from employer location)
    accident_street = Column(String(200), nullable=True)
    accident_city = Column(String(100), nullable=True)
    accident_state = Column(String(50), nullable=True)
    accident_zip = Column(String(20), nullable=True)
    accident_county = Column(String(100), nullable=True)

    # Employment details at time of injury
    date_employed = Column(Date, nullable=True)
    paid_for_injury_date = Column(Boolean, default=False)
    last_date_worked = Column(Date, nullable=True)
    returned_to_work = Column(Boolean, default=False)
    return_to_work_date = Column(Date, nullable=True)

    # Rate of pay
    rate_of_pay = Column(String(20), nullable=True)
    pay_period = Column(String(10), nullable=True)  # HR, DAY, WK, MO
    hours_per_day = Column(String(10), nullable=True)
    hours_per_week = Column(String(10), nullable=True)
    days_per_week = Column(String(10), nullable=True)

    # Medical treatment
    physician_name = Column(String(200), nullable=True)
    physician_address = Column(Text, nullable=True)
    physician_phone = Column(String(50), nullable=True)
    hospital_name = Column(String(200), nullable=True)
    treatment_authorized_by_employer = Column(Boolean, default=True)

    # Does employer agree with description?
    employer_agrees_with_description = Column(Boolean, default=True)
    employer_disagreement_notes = Column(Text, nullable=True)

    # Wages continuation
    will_continue_wages = Column(Boolean, default=False)
    last_day_wages_paid = Column(Date, nullable=True)

    # Death (if applicable)
    date_of_death = Column(Date, nullable=True)

    # Status
    status = Column(Enum(FormStatus), default=FormStatus.DRAFT, nullable=False)

    # Signatures
    employee_signature = Column(Text, nullable=True)
    employee_signature_date = Column(DateTime, nullable=True)
    employee_typed_name = Column(String(200), nullable=True)
    employee_signature_ip = Column(String(50), nullable=True)
    employee_signature_user_agent = Column(String(500), nullable=True)

    employer_signature = Column(Text, nullable=True)
    employer_signature_date = Column(DateTime, nullable=True)
    employer_typed_name = Column(String(200), nullable=True)
    employer_signature_ip = Column(String(50), nullable=True)
    employer_signature_user_agent = Column(String(500), nullable=True)
    employer_signer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Date first reported
    date_first_reported = Column(Date, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # PDF document reference (after completion)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    employer_signer = relationship("User", foreign_keys=[employer_signer_id])
    creator = relationship("User", foreign_keys=[created_by])
    document = relationship("Document", foreign_keys=[document_id])

    __table_args__ = (
        Index("ix_first_report_injury_employee", "employee_id"),
        Index("ix_first_report_injury_status", "status"),
        Index("ix_first_report_injury_date", "accident_date"),
    )
