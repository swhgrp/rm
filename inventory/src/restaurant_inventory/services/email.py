"""
Email service for sending notifications
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from restaurant_inventory.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via SMTP"""

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional, will strip HTML if not provided)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            message['To'] = to_email

            # Add plain text version
            if text_content:
                text_part = MIMEText(text_content, 'plain')
                message.attach(text_part)

            # Add HTML version
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            # Connect to SMTP server (10 second timeout)
            if settings.SMTP_USE_TLS:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5)
                server.starttls()
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5)

            # Login if credentials provided
            if settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            # Send email
            server.send_message(message)
            server.quit()

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_user_invitation(
        to_email: str,
        full_name: str,
        username: str,
        setup_url: str
    ) -> bool:
        """
        Send invitation email to new user with password setup link.

        Args:
            to_email: User's email address
            full_name: User's full name
            username: User's username
            setup_url: URL for password setup

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Welcome to SW Hospitality Group Inventory System"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background-color: #0d1117;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .content {{
            background-color: white;
            padding: 30px;
            margin-top: 20px;
            border-radius: 5px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 30px;
            background-color: #0d6efd;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .button:hover {{
            background-color: #0b5ed7;
        }}
        .info-box {{
            background-color: #e7f3ff;
            border-left: 4px solid #0d6efd;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            text-align: center;
            margin-top: 20px;
            font-size: 12px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SW Hospitality Group</h1>
            <p>Restaurant Inventory Management System</p>
        </div>
        <div class="content">
            <h2>Welcome, {full_name}!</h2>
            <p>You've been invited to join the SW Hospitality Group Inventory Management System.</p>

            <div class="info-box">
                <strong>Your Username:</strong> {username}
            </div>

            <p>To activate your account and set your password, please click the button below:</p>

            <div style="text-align: center;">
                <a href="{setup_url}" class="button">Set Up My Account</a>
            </div>

            <p><strong>Important:</strong> This invitation link will expire in 24 hours for security reasons.</p>

            <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #0d6efd;">{setup_url}</p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">

            <p>If you didn't expect this invitation, please disregard this email or contact your system administrator.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 SW Hospitality Group. All rights reserved.</p>
            <p>This is an automated message, please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Welcome to SW Hospitality Group Inventory System!

Hello {full_name},

You've been invited to join the SW Hospitality Group Inventory Management System.

Your Username: {username}

To activate your account and set your password, please visit this link:
{setup_url}

Important: This invitation link will expire in 24 hours for security reasons.

If you didn't expect this invitation, please disregard this email or contact your system administrator.

---
© 2025 SW Hospitality Group. All rights reserved.
This is an automated message, please do not reply to this email.
"""

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    @staticmethod
    def send_password_reset(
        to_email: str,
        full_name: str,
        reset_url: str
    ) -> bool:
        """
        Send password reset email to user.

        Args:
            to_email: User's email address
            full_name: User's full name
            reset_url: URL for password reset

        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Password Reset Request - SW Hospitality Group"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background-color: #0d1117;
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .content {{
            background-color: white;
            padding: 30px;
            margin-top: 20px;
            border-radius: 5px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 30px;
            background-color: #dc3545;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .button:hover {{
            background-color: #bb2d3b;
        }}
        .footer {{
            text-align: center;
            margin-top: 20px;
            font-size: 12px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SW Hospitality Group</h1>
            <p>Password Reset Request</p>
        </div>
        <div class="content">
            <h2>Hello, {full_name}</h2>
            <p>We received a request to reset your password for the Inventory Management System.</p>

            <p>To reset your password, please click the button below:</p>

            <div style="text-align: center;">
                <a href="{reset_url}" class="button">Reset My Password</a>
            </div>

            <p><strong>Important:</strong> This reset link will expire in 24 hours for security reasons.</p>

            <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #dc3545;">{reset_url}</p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">

            <p><strong>If you didn't request a password reset, please ignore this email.</strong> Your password will remain unchanged.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 SW Hospitality Group. All rights reserved.</p>
            <p>This is an automated message, please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""
Password Reset Request

Hello {full_name},

We received a request to reset your password for the SW Hospitality Group Inventory Management System.

To reset your password, please visit this link:
{reset_url}

Important: This reset link will expire in 24 hours for security reasons.

If you didn't request a password reset, please ignore this email. Your password will remain unchanged.

---
© 2025 SW Hospitality Group. All rights reserved.
This is an automated message, please do not reply to this email.
"""

        return EmailService.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
