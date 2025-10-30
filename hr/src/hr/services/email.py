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
        attachment_path: Optional[str] = None
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional)
            attachment_path: Path to file to attach (optional)

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

            # Add attachment if provided
            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename={os.path.basename(attachment_path)}'
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
    def send_new_hire_email(employee_data: dict, created_by: str, position_info: Optional[dict] = None) -> bool:
        """Send notification email when new employee is created."""
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

        if position_info:
            text_content += f"""
POSITION ASSIGNMENT
-------------------
Position: {position_info.get('position', 'Not assigned')}
Location: {position_info.get('location', 'Not assigned')}
Start Date: {position_info.get('start_date', 'N/A')}
"""

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
            text_content=text_content
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
def send_new_hire_notification(employee_data: dict, created_by: str, position_info: Optional[dict] = None) -> bool:
    """Convenience function to send new hire notification"""
    return EmailService.send_new_hire_email(employee_data, created_by, position_info)


def send_termination_notification(
    employee_data: dict,
    processed_by: str,
    position_info: Optional[dict] = None,
    attachment_path: Optional[str] = None
) -> bool:
    """Convenience function to send termination notification"""
    return EmailService.send_termination_email(employee_data, processed_by, position_info, attachment_path)
