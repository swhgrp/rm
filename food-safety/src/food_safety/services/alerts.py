"""Email alert service for Food Safety"""
import logging
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from food_safety.config import settings

logger = logging.getLogger(__name__)


async def send_email_alert(
    subject: str,
    body: str,
    recipients: Optional[List[str]] = None,
    html_body: Optional[str] = None
):
    """Send an email alert

    Args:
        subject: Email subject
        body: Plain text body
        recipients: List of email addresses (defaults to ALERT_EMAIL_TO)
        html_body: Optional HTML body
    """
    if not settings.SMTP_HOST:
        logger.warning("SMTP not configured, skipping email alert")
        return

    to_addresses = recipients or [settings.ALERT_EMAIL_TO]
    if not to_addresses or not to_addresses[0]:
        logger.warning("No recipients configured for email alerts")
        return

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = settings.ALERT_EMAIL_FROM
        message["To"] = ", ".join(to_addresses)

        # Add plain text
        message.attach(MIMEText(body, "plain"))

        # Add HTML if provided
        if html_body:
            message.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER if settings.SMTP_USER else None,
            password=settings.SMTP_PASSWORD if settings.SMTP_PASSWORD else None,
            start_tls=True if settings.SMTP_USER else False,
        )

        logger.info(f"Email alert sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")


async def send_temperature_alert(
    equipment_name: str,
    location_name: str,
    temperature: float,
    min_threshold: float,
    max_threshold: float,
    temp_unit: str = "F"
):
    """Send a temperature violation alert"""
    subject = f"[ALERT] Temperature Violation - {equipment_name}"

    body = f"""
Temperature Alert
=================

Equipment: {equipment_name}
Location: {location_name}
Temperature: {temperature}°{temp_unit}
Acceptable Range: {min_threshold}°{temp_unit} - {max_threshold}°{temp_unit}

Please investigate and take corrective action immediately.

This is an automated alert from the Food Safety System.
"""

    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
<h2 style="color: #d32f2f;">Temperature Alert</h2>
<table style="border-collapse: collapse; margin: 20px 0;">
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Equipment:</strong></td>
    <td style="padding: 8px; border: 1px solid #ddd;">{equipment_name}</td></tr>
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Location:</strong></td>
    <td style="padding: 8px; border: 1px solid #ddd;">{location_name}</td></tr>
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Temperature:</strong></td>
    <td style="padding: 8px; border: 1px solid #ddd; color: #d32f2f; font-weight: bold;">{temperature}°{temp_unit}</td></tr>
<tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Acceptable Range:</strong></td>
    <td style="padding: 8px; border: 1px solid #ddd;">{min_threshold}°{temp_unit} - {max_threshold}°{temp_unit}</td></tr>
</table>
<p><strong>Please investigate and take corrective action immediately.</strong></p>
<hr>
<p style="color: #666; font-size: 12px;">This is an automated alert from the Food Safety System.</p>
</body>
</html>
"""

    await send_email_alert(subject, body, html_body=html_body)


async def send_incident_alert(
    incident_number: str,
    incident_type: str,
    title: str,
    location_name: str,
    severity: str,
    description: str
):
    """Send a new incident alert"""
    subject = f"[INCIDENT] {incident_number} - {title}"

    body = f"""
New Food Safety Incident
========================

Incident Number: {incident_number}
Type: {incident_type}
Title: {title}
Location: {location_name}
Severity: {severity.upper()}

Description:
{description}

Please log in to the Food Safety system to review and take action.

This is an automated alert from the Food Safety System.
"""

    await send_email_alert(subject, body)
