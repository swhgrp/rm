"""Notification Service for Forms"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from forms.config import settings

logger = logging.getLogger(__name__)

# Email templates directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
EMAIL_TEMPLATES_DIR = BASE_DIR / "templates" / "email"


class NotificationService:
    """Service for sending notifications (email, in-app)."""

    def __init__(self):
        self.template_env = None
        if EMAIL_TEMPLATES_DIR.exists():
            self.template_env = Environment(
                loader=FileSystemLoader(str(EMAIL_TEMPLATES_DIR)),
                autoescape=True
            )

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: str = None
    ) -> bool:
        """
        Send an email notification.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional)

        Returns:
            True if sent successfully
        """
        if not settings.SMTP_HOST:
            logger.warning("SMTP not configured, skipping email send")
            return False

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = settings.SMTP_FROM
            message["To"] = to_email

            if body_text:
                message.attach(MIMEText(body_text, "plain"))
            message.attach(MIMEText(body_html, "html"))

            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True
            )

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    async def send_signature_request(
        self,
        to_email: str,
        employee_name: str,
        form_name: str,
        reference_number: str,
        signature_link: str,
        requester_name: str = None
    ) -> bool:
        """
        Send signature request notification.

        Args:
            to_email: Recipient email
            employee_name: Name of person who needs to sign
            form_name: Name of the form
            reference_number: Form reference number
            signature_link: Link to sign the form
            requester_name: Name of person requesting signature

        Returns:
            True if sent successfully
        """
        subject = f"Signature Required: {form_name} ({reference_number})"

        context = {
            "employee_name": employee_name,
            "form_name": form_name,
            "reference_number": reference_number,
            "signature_link": signature_link,
            "requester_name": requester_name,
            "company_name": "SW Hospitality Group"
        }

        body_html = self._render_template("signature_request.html", context)

        return await self.send_email(to_email, subject, body_html)

    async def send_workflow_assignment(
        self,
        to_email: str,
        employee_name: str,
        form_name: str,
        reference_number: str,
        step_name: str,
        action_required: str,
        review_link: str
    ) -> bool:
        """
        Send workflow assignment notification.

        Args:
            to_email: Recipient email
            employee_name: Name of assigned employee
            form_name: Name of the form
            reference_number: Form reference number
            step_name: Workflow step name
            action_required: What action is needed
            review_link: Link to review the form

        Returns:
            True if sent successfully
        """
        subject = f"Action Required: {form_name} - {step_name}"

        context = {
            "employee_name": employee_name,
            "form_name": form_name,
            "reference_number": reference_number,
            "step_name": step_name,
            "action_required": action_required,
            "review_link": review_link,
            "company_name": "SW Hospitality Group"
        }

        body_html = self._render_template("workflow_assignment.html", context)

        return await self.send_email(to_email, subject, body_html)

    async def send_daily_digest(
        self,
        to_email: str,
        employee_name: str,
        pending_signatures: List[Dict[str, Any]],
        pending_reviews: List[Dict[str, Any]],
        recent_submissions: List[Dict[str, Any]]
    ) -> bool:
        """
        Send daily digest email.

        Args:
            to_email: Recipient email
            employee_name: Employee name
            pending_signatures: List of pending signature requests
            pending_reviews: List of pending workflow tasks
            recent_submissions: Recent submissions

        Returns:
            True if sent successfully
        """
        subject = f"Forms Daily Digest - {datetime.now().strftime('%B %d, %Y')}"

        context = {
            "employee_name": employee_name,
            "pending_signatures": pending_signatures,
            "pending_reviews": pending_reviews,
            "recent_submissions": recent_submissions,
            "date": datetime.now().strftime("%B %d, %Y"),
            "company_name": "SW Hospitality Group"
        }

        body_html = self._render_template("digest.html", context)

        return await self.send_email(to_email, subject, body_html)

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render an email template."""
        if self.template_env:
            try:
                template = self.template_env.get_template(template_name)
                return template.render(**context)
            except Exception as e:
                logger.warning(f"Failed to render template {template_name}: {e}")

        # Fallback to simple HTML
        return self._simple_html(context)

    def _simple_html(self, context: Dict[str, Any]) -> str:
        """Generate simple HTML fallback."""
        return f"""
        <html>
        <body>
            <h2>{context.get('company_name', 'SW Hospitality Group')}</h2>
            <p>Hello {context.get('employee_name', 'Team Member')},</p>
            <p>You have a notification from the Forms system.</p>
            <p>Reference: {context.get('reference_number', 'N/A')}</p>
        </body>
        </html>
        """


# Singleton instance
_notification_service = None


def get_notification_service() -> NotificationService:
    """Get notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
