"""Email service (example)"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from events.core.config import settings
from events.models import Email, EmailStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Handles email sending and templating"""

    def __init__(self):
        # Setup Jinja2 for email templates
        self.jinja_env = Environment(
            loader=FileSystemLoader("src/events/templates/emails")
        )

    async def send_email(
        self,
        db: Session,
        to_list: List[str],
        subject: str,
        template_key: str,
        variables: Dict[str, Any],
        cc_list: List[str] = None,
        event_id: str = None
    ) -> Email:
        """
        Send an email using template and variables

        Args:
            db: Database session
            to_list: List of recipient emails
            subject: Email subject
            template_key: Template filename (without .html)
            variables: Dict of variables for template
            cc_list: Optional CC list
            event_id: Optional event ID to associate with

        Returns:
            Email: Created email record
        """
        # Render template
        try:
            template = self.jinja_env.get_template(f"{template_key}.html")
            body_html = template.render(**variables)
        except Exception as e:
            logger.error(f"Failed to render template {template_key}: {e}")
            raise

        # Create email record
        email = Email(
            event_id=event_id,
            to_list=to_list,
            cc_list=cc_list or [],
            subject=subject,
            body_html=body_html,
            status=EmailStatus.QUEUED
        )
        db.add(email)
        db.commit()
        db.refresh(email)

        # Send email
        try:
            self._send_smtp(to_list, cc_list or [], subject, body_html)
            email.status = EmailStatus.SENT
            email.sent_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Failed to send email {email.id}: {e}")
            email.status = EmailStatus.FAILED
            email.error_message = str(e)

        db.commit()
        return email

    def _send_smtp(
        self,
        to_list: List[str],
        cc_list: List[str],
        subject: str,
        body_html: str
    ):
        """Send email via SMTP"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
        msg['To'] = ", ".join(to_list)
        if cc_list:
            msg['Cc'] = ", ".join(cc_list)

        # Attach HTML body
        html_part = MIMEText(body_html, 'html')
        msg.attach(html_part)

        # Send via SMTP
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            all_recipients = to_list + cc_list
            server.sendmail(settings.FROM_EMAIL, all_recipients, msg.as_string())

    async def send_notification_by_rule(
        self,
        db: Session,
        event: Any,
        trigger: str,
        template: Any = None
    ):
        """
        Send notification based on event template rules

        Args:
            db: Database session
            event: Event object
            trigger: Trigger name (on_confirmed, on_updated, etc.)
            template: Event template with email_rules_json
        """
        if not template or not template.email_rules_json:
            return

        rules = template.email_rules_json.get(trigger, [])

        for rule in rules:
            to_emails = self._resolve_email_list(rule.get('to'), event)
            cc_emails = self._resolve_email_list(rule.get('cc'), event)

            subject = self._replace_variables(rule.get('subject'), event)
            template_key = rule.get('template_key')

            variables = {
                'event': event,
                'client': event.client,
                'venue': event.venue,
            }

            await self.send_email(
                db=db,
                to_list=to_emails,
                subject=subject,
                template_key=template_key,
                variables=variables,
                cc_list=cc_emails,
                event_id=str(event.id)
            )

    def _resolve_email_list(self, email_spec: str, event: Any) -> List[str]:
        """
        Resolve email specification to actual email list

        Args:
            email_spec: Email spec like "{client.email}", "{location_users}", or "events@swhgrp.com"
            event: Event object

        Returns:
            List of resolved emails
        """
        if not email_spec:
            return []

        # Handle variable substitution
        if '{' in email_spec:
            if 'client.email' in email_spec:
                return [event.client.email]
            elif 'location_users' in email_spec:
                # Get all users with permissions for this event's venue/location
                return self._get_location_user_emails(event)
            # Add more variable handling as needed

        return [email_spec]

    def _get_location_user_emails(self, event: Any) -> List[str]:
        """
        Get emails of all users with permissions for the event's location

        Args:
            event: Event object with venue_id

        Returns:
            List of user email addresses
        """
        from events.models.user import UserLocation, User

        if not event.venue_id:
            logger.warning(f"Event {event.id} has no venue_id, cannot get location users")
            return []

        try:
            # Get all users assigned to this venue/location
            from sqlalchemy import select
            from events.core.database import SessionLocal

            db = SessionLocal()

            # Query users who have this venue in their user_locations
            user_emails = db.query(User.email).join(
                UserLocation, UserLocation.user_id == User.id
            ).filter(
                UserLocation.venue_id == event.venue_id,
                User.is_active == True
            ).distinct().all()

            db.close()

            emails = [email[0] for email in user_emails if email[0]]
            logger.info(f"Found {len(emails)} users for venue {event.venue_id}: {emails}")
            return emails

        except Exception as e:
            logger.error(f"Error getting location user emails: {e}")
            return []

    def _replace_variables(self, text: str, event: Any) -> str:
        """Replace template variables in text"""
        if not text:
            return text

        replacements = {
            '{event.title}': event.title,
            '{event.start_at}': str(event.start_at),
            '{client.name}': event.client.name if event.client else 'N/A',
            '{venue.name}': event.venue.name if event.venue else 'Not assigned',
        }

        for key, value in replacements.items():
            if value:
                text = text.replace(key, str(value))

        return text
