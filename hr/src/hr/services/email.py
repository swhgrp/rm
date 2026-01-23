"""
Email service for HR notifications
"""
import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending HR notification emails via SMTP"""

    @staticmethod
    def get_smtp_config():
        """Get SMTP configuration from database or environment variables"""
        from hr.db.database import SessionLocal
        from hr.models.settings import SystemSettings
        from hr.core.encryption import decrypt_value
        
        # Try to get settings from database first
        try:
            db = SessionLocal()
            settings = db.query(SystemSettings).filter(
                SystemSettings.category == "smtp"
            ).all()
            
            if settings:
                config = {}
                for setting in settings:
                    value = decrypt_value(setting.value) if setting.is_encrypted and setting.value else setting.value
                    # Map database keys to config keys
                    key_name = setting.key.replace("smtp_", "")
                    config[key_name] = value
                
                db.close()
                
                # Ensure all required keys exist
                if 'host' in config and 'user' in config:
                    # Convert port to int and use_tls to boolean
                    config['port'] = int(config.get('port', 587))
                    config['use_tls'] = config.get('use_tls', 'true').lower() == 'true'
                    config['hr_recipient'] = config.get('hr_recipient', 'hr@swhgrp.com')
                    return config
            
            db.close()
        except Exception as e:
            logger.warning(f"Could not load SMTP settings from database: {e}")
        
        # Fall back to environment variables
        return {
            'host': os.getenv('SMTP_HOST', 'smtp.gmail.com'),
            'port': int(os.getenv('SMTP_PORT', '587')),
            'user': os.getenv('SMTP_USER', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'from_name': os.getenv('SMTP_FROM_NAME', 'HR System'),
            'from_email': os.getenv('SMTP_FROM_EMAIL', 'hr@swhgrp.com'),
            'use_tls': os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
            'hr_recipient': os.getenv('HR_EMAIL_RECIPIENT', 'hr@swhgrp.com')
        }

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachment_path: Optional[str] = None,
        attachment_paths: Optional[list] = None
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional)
            attachment_path: Path to file to attach (optional, deprecated - use attachment_paths)
            attachment_paths: List of paths to files to attach (optional)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            config = EmailService.get_smtp_config()

            # Skip if SMTP not configured
            if not config['user'] or not config['password']:
                logger.warning(f"SMTP not configured, skipping email to {to_email}")
                logger.info(f"Would have sent: {subject}")
                logger.info(f"Content: {text_content or html_content[:200]}...")
                return False

            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = f"{config['from_name']} <{config['from_email']}>"
            message['To'] = to_email

            # Add plain text version
            if text_content:
                text_part = MIMEText(text_content, 'plain')
                message.attach(text_part)

            # Add HTML version
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            # Collect all attachment paths (support both single and multiple)
            all_attachments = []
            if attachment_path:
                all_attachments.append(attachment_path)
            if attachment_paths:
                all_attachments.extend(attachment_paths)

            # Add attachments if provided
            for att_path in all_attachments:
                if att_path and os.path.exists(att_path):
                    with open(att_path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename={os.path.basename(att_path)}'
                        )
                        message.attach(part)

            # Connect to SMTP server
            if config['use_tls']:
                server = smtplib.SMTP(config['host'], config['port'])
                server.starttls()
            else:
                server = smtplib.SMTP(config['host'], config['port'])

            # Login if credentials provided
            if config['password']:
                server.login(config['user'], config['password'])

            # Send email
            server.send_message(message)
            server.quit()

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_new_hire_email(
        employee_data: dict,
        created_by: str,
        position_info: Optional[dict] = None,
        location_names: Optional[list] = None,
        document_paths: Optional[list] = None
    ) -> bool:
        """
        Send notification email when new employee is created.

        Args:
            employee_data: Dictionary containing employee information
            created_by: Name and email of user who created the employee
            position_info: Dictionary with position, location, start_date (optional but recommended)
            location_names: List of location names the employee is assigned to
            document_paths: List of file paths to attach (ID, SSN docs, etc.)
        """
        config = EmailService.get_smtp_config()

        # Format employee data
        name = f"{employee_data.get('first_name', '')} {employee_data.get('last_name', '')}"
        emp_number = employee_data.get('employee_number', 'N/A')

        subject = f"New Hire: {name} - {emp_number}"

        # Build text content
        text_content = f"""
New Employee Added to HR System

PERSONAL INFORMATION
-------------------
Employee Number: {emp_number}
Name: {name}
Date of Birth: {employee_data.get('date_of_birth') or 'Not provided'}

CONTACT INFORMATION
-------------------
Email: {employee_data.get('email', 'N/A')}
Phone: {employee_data.get('phone_number') or 'Not provided'}
Address: {employee_data.get('street_address') or 'Not provided'}
City: {employee_data.get('city') or ''} {employee_data.get('state') or ''} {employee_data.get('zip_code') or ''}

EMERGENCY CONTACT
-------------------
Name: {employee_data.get('emergency_contact_name') or 'Not provided'}
Relationship: {employee_data.get('emergency_contact_relationship') or 'Not provided'}
Phone: {employee_data.get('emergency_contact_phone') or 'Not provided'}

EMPLOYMENT DETAILS
-------------------
Hire Date: {employee_data.get('hire_date', 'N/A')}
Employment Status: {employee_data.get('employment_status', 'N/A')}
Employee Type: {employee_data.get('employee_type', 'N/A')}
Starting Pay Rate: ${employee_data.get('starting_pay_rate', 'Not provided')}
"""

        # Include assigned locations
        if location_names and len(location_names) > 0:
            text_content += f"""
ASSIGNED LOCATIONS
-------------------
"""
            for loc_name in location_names:
                text_content += f"- {loc_name}\n"
        else:
            text_content += f"""
ASSIGNED LOCATIONS
-------------------
No locations assigned yet
"""

        # Include position information if available
        if position_info:
            text_content += f"""
POSITION ASSIGNMENT
-------------------
Position: {position_info.get('position', 'Not assigned')}
Location: {position_info.get('location', 'Not assigned')}
Start Date: {position_info.get('start_date', 'N/A')}
"""

        # Add document attachment note
        if document_paths:
            text_content += f"""
ATTACHED DOCUMENTS
-------------------
"""
            for doc_path in document_paths:
                if doc_path and os.path.exists(doc_path):
                    text_content += f"- {os.path.basename(doc_path)}\n"

        text_content += f"""
---
Added by: {created_by}
Date/Time: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
"""

        # HTML version (simple formatting)
        html_content = text_content.replace('\n', '<br>')
        html_content = f"<html><body><pre>{html_content}</pre></body></html>"

        return EmailService.send_email(
            to_email=config['hr_recipient'],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            attachment_paths=document_paths
        )

    @staticmethod
    def send_termination_email(
        employee_data: dict,
        processed_by: str,
        position_info: Optional[dict] = None,
        attachment_path: Optional[str] = None
    ) -> bool:
        """Send notification email when employee is terminated."""
        config = EmailService.get_smtp_config()

        # Format employee data
        name = f"{employee_data.get('first_name', '')} {employee_data.get('last_name', '')}"
        emp_number = employee_data.get('employee_number', 'N/A')

        subject = f"Employee Termination: {name} - {emp_number}"

        # Calculate employment duration
        hire_date = employee_data.get('hire_date')
        term_date = employee_data.get('termination_date')
        duration = "Unknown"
        if hire_date and term_date:
            try:
                from datetime import datetime
                h_date = datetime.fromisoformat(str(hire_date)) if isinstance(hire_date, str) else hire_date
                t_date = datetime.fromisoformat(str(term_date)) if isinstance(term_date, str) else term_date
                days = (t_date - h_date).days
                months = days // 30
                duration = f"{months} months" if months > 0 else f"{days} days"
            except:
                duration = "Unable to calculate"

        # Build text content
        text_content = f"""
Employee Termination Notice

EMPLOYEE INFORMATION
-------------------
Employee Number: {emp_number}
Name: {name}
Email: {employee_data.get('email', 'N/A')}
Phone: {employee_data.get('phone_number') or 'Not provided'}

EMPLOYMENT DETAILS
-------------------
Hire Date: {hire_date}
Termination Date: {term_date}
Employment Duration: {duration}

TERMINATION DETAILS
-------------------
Type of Termination: {employee_data.get('termination_type', 'Not specified')}
Reason: {employee_data.get('termination_reason', 'Not provided')}

Final Decision Date: {employee_data.get('final_decision_date') or 'Not provided'}
Authorized By: {employee_data.get('authorized_by', 'Not specified')}

Supporting Documentation: {'Attached' if attachment_path else 'None uploaded'}
"""

        if position_info:
            text_content += f"""
POSITION AT TERMINATION
-------------------
Position: {position_info.get('position', 'Unknown')}
Location: {position_info.get('location', 'Unknown')}
"""

        text_content += f"""
---
Processed by: {processed_by}
Date/Time: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
"""

        # HTML version (simple formatting)
        html_content = text_content.replace('\n', '<br>')
        html_content = f"<html><body><pre>{html_content}</pre></body></html>"

        return EmailService.send_email(
            to_email=config['hr_recipient'],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            attachment_path=attachment_path
        )


# Convenience functions
def send_new_hire_notification(
    employee_data: dict,
    created_by: str,
    position_info: Optional[dict] = None,
    location_names: Optional[list] = None,
    document_paths: Optional[list] = None
) -> bool:
    """Convenience function to send new hire notification"""
    return EmailService.send_new_hire_email(employee_data, created_by, position_info, location_names, document_paths)


def send_termination_notification(
    employee_data: dict,
    processed_by: str,
    position_info: Optional[dict] = None,
    attachment_path: Optional[str] = None
) -> bool:
    """Convenience function to send termination notification"""
    return EmailService.send_termination_email(employee_data, processed_by, position_info, attachment_path)


class FormNotificationService:
    """Service for sending form completion notifications"""

    @staticmethod
    def send_corrective_action_email(
        employee_name: str,
        employee_number: str,
        reference_number: str,
        disciplinary_level: str,
        subject: str,
        incident_date: str,
        incident_description: str,
        location_name: str,
        supervisor_name: str,
        completed_by: str
    ) -> bool:
        """
        Send notification email when corrective action is completed.

        Args:
            employee_name: Full name of the employee
            employee_number: Employee number
            reference_number: CA reference number (e.g., CA-2026-0001)
            disciplinary_level: Level of disciplinary action
            subject: Subject/reason for corrective action
            incident_date: Date of incident
            incident_description: Description of the incident
            location_name: Location where employee works
            supervisor_name: Name of supervisor who issued the action
            completed_by: Name of user who completed the form
        """
        config = EmailService.get_smtp_config()

        subject_line = f"Corrective Action Completed: {employee_name} - {reference_number}"

        # Format disciplinary level for display
        level_display = disciplinary_level.replace("_", " ").title() if disciplinary_level else "N/A"
        subject_display = subject.replace("_", " ").title() if subject else "N/A"

        text_content = f"""
Corrective Action Form Completed

REFERENCE INFORMATION
-------------------
Reference Number: {reference_number}
Location: {location_name}

EMPLOYEE INFORMATION
-------------------
Employee Name: {employee_name}
Employee Number: {employee_number}

DISCIPLINARY ACTION
-------------------
Disciplinary Level: {level_display}
Subject: {subject_display}
Incident Date: {incident_date}

INCIDENT DESCRIPTION
-------------------
{incident_description}

---
Supervisor: {supervisor_name}
Completed by: {completed_by}
Date/Time: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
"""

        html_content = text_content.replace('\n', '<br>')
        html_content = f"<html><body><pre>{html_content}</pre></body></html>"

        return EmailService.send_email(
            to_email=config['hr_recipient'],
            subject=subject_line,
            html_content=html_content,
            text_content=text_content
        )

    @staticmethod
    def send_injury_report_email(
        employee_name: str,
        employee_number: str,
        reference_number: str,
        accident_date: str,
        injury_type: str,
        body_part: str,
        accident_description: str,
        location_name: str,
        completed_by: str
    ) -> bool:
        """
        Send notification email when injury report is completed.

        Args:
            employee_name: Full name of the employee
            employee_number: Employee number
            reference_number: Injury reference number (e.g., INJ-2026-0001)
            accident_date: Date of accident/injury
            injury_type: Type of injury
            body_part: Body part affected
            accident_description: Description of the accident
            location_name: Location where accident occurred
            completed_by: Name of user who completed the form
        """
        config = EmailService.get_smtp_config()

        subject_line = f"Injury Report Completed: {employee_name} - {reference_number}"

        # Format injury type and body part for display
        injury_display = injury_type.replace("_", " ").title() if injury_type else "N/A"
        body_part_display = body_part.replace("_", " ").title() if body_part else "N/A"

        text_content = f"""
First Report of Injury Completed

REFERENCE INFORMATION
-------------------
Reference Number: {reference_number}
Location: {location_name}

EMPLOYEE INFORMATION
-------------------
Employee Name: {employee_name}
Employee Number: {employee_number}

INJURY DETAILS
-------------------
Date of Injury: {accident_date}
Type of Injury: {injury_display}
Body Part Affected: {body_part_display}

ACCIDENT DESCRIPTION
-------------------
{accident_description}

---
Completed by: {completed_by}
Date/Time: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

IMPORTANT: Please review this injury report and ensure all required workers' compensation procedures are followed.
"""

        html_content = text_content.replace('\n', '<br>')
        html_content = f"<html><body><pre>{html_content}</pre></body></html>"

        return EmailService.send_email(
            to_email=config['hr_recipient'],
            subject=subject_line,
            html_content=html_content,
            text_content=text_content
        )


# Convenience functions for form notifications
def send_corrective_action_notification(
    employee_name: str,
    employee_number: str,
    reference_number: str,
    disciplinary_level: str,
    subject: str,
    incident_date: str,
    incident_description: str,
    location_name: str,
    supervisor_name: str,
    completed_by: str
) -> bool:
    """Convenience function to send corrective action notification"""
    return FormNotificationService.send_corrective_action_email(
        employee_name, employee_number, reference_number,
        disciplinary_level, subject, incident_date, incident_description,
        location_name, supervisor_name, completed_by
    )


def send_injury_report_notification(
    employee_name: str,
    employee_number: str,
    reference_number: str,
    accident_date: str,
    injury_type: str,
    body_part: str,
    accident_description: str,
    location_name: str,
    completed_by: str
) -> bool:
    """Convenience function to send injury report notification"""
    return FormNotificationService.send_injury_report_email(
        employee_name, employee_number, reference_number,
        accident_date, injury_type, body_part, accident_description,
        location_name, completed_by
    )
