"""
Email service for sending invoices and other AR communications

Supports PDF attachments and HTML email templates
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import List, Optional
from io import BytesIO
from sqlalchemy.orm import Session
import logging

from accounting.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)


class EmailService:
    """Handles email sending for Accounting/AR"""

    def __init__(self, db: Session):
        """
        Initialize email service with settings from database

        Args:
            db: Database session to fetch email settings
        """
        self.db = db
        self._load_settings()

    def _load_settings(self):
        """Load email settings from system_settings table"""
        settings = {}

        # Email settings keys
        setting_keys = [
            'email_smtp_host',
            'email_smtp_port',
            'email_smtp_user',
            'email_smtp_password',
            'email_from_address',
            'email_from_name',
            'email_use_tls'
        ]

        for key in setting_keys:
            setting = self.db.query(SystemSetting).filter(
                SystemSetting.setting_key == key
            ).first()

            if setting:
                settings[key] = setting.setting_value

        # Set defaults if not found
        self.smtp_host = settings.get('email_smtp_host', 'localhost')
        self.smtp_port = int(settings.get('email_smtp_port', '587'))
        self.smtp_user = settings.get('email_smtp_user', '')
        self.smtp_password = settings.get('email_smtp_password', '')
        self.from_address = settings.get('email_from_address', 'accounting@swrestaurantgroup.com')
        self.from_name = settings.get('email_from_name', 'SW Hospitality Group - Accounting')
        self.use_tls = settings.get('email_use_tls', 'true').lower() == 'true'

    def send_invoice_email(
        self,
        to_email: str,
        customer_name: str,
        invoice_number: str,
        invoice_amount: float,
        due_date: str,
        pdf_buffer: Optional[BytesIO] = None,
        cc_emails: Optional[List[str]] = None,
        additional_message: Optional[str] = None
    ) -> bool:
        """
        Send invoice via email with PDF attachment

        Args:
            to_email: Customer email address
            customer_name: Customer name for personalization
            invoice_number: Invoice number
            invoice_amount: Total invoice amount
            due_date: Invoice due date (formatted string)
            pdf_buffer: Optional BytesIO buffer containing PDF
            cc_emails: Optional list of CC email addresses
            additional_message: Optional additional message to include

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = f'Invoice {invoice_number} from {self.from_name}'
            msg['From'] = f'{self.from_name} <{self.from_address}>'
            msg['To'] = to_email

            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)

            # Create HTML email body
            html_body = self._create_invoice_email_html(
                customer_name=customer_name,
                invoice_number=invoice_number,
                invoice_amount=invoice_amount,
                due_date=due_date,
                additional_message=additional_message
            )

            # Attach HTML body
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            # Attach PDF if provided
            if pdf_buffer:
                pdf_buffer.seek(0)  # Reset buffer position
                pdf_attachment = MIMEApplication(pdf_buffer.read(), _subtype='pdf')
                pdf_attachment.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=f'Invoice_{invoice_number}.pdf'
                )
                msg.attach(pdf_attachment)

            # Send email
            all_recipients = [to_email]
            if cc_emails:
                all_recipients.extend(cc_emails)

            self._send_smtp(msg, all_recipients)

            logger.info(f"Invoice {invoice_number} emailed successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send invoice {invoice_number} to {to_email}: {str(e)}")
            return False

    def _create_invoice_email_html(
        self,
        customer_name: str,
        invoice_number: str,
        invoice_amount: float,
        due_date: str,
        additional_message: Optional[str] = None
    ) -> str:
        """Create HTML email body for invoice"""

        additional_msg_html = ""
        if additional_message:
            additional_msg_html = f"<p>{additional_message}</p>"

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background-color: #2563eb;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 5px 5px 0 0;
        }}
        .content {{
            background-color: #f9fafb;
            padding: 30px;
            border: 1px solid #e5e7eb;
            border-top: none;
        }}
        .invoice-details {{
            background-color: white;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #2563eb;
            border-radius: 4px;
        }}
        .invoice-details table {{
            width: 100%;
        }}
        .invoice-details td {{
            padding: 8px 0;
        }}
        .invoice-details td:first-child {{
            font-weight: bold;
            width: 40%;
        }}
        .amount {{
            font-size: 24px;
            color: #2563eb;
            font-weight: bold;
        }}
        .button {{
            display: inline-block;
            background-color: #2563eb;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .footer {{
            background-color: #f3f4f6;
            padding: 20px;
            text-align: center;
            font-size: 12px;
            color: #6b7280;
            border-radius: 0 0 5px 5px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{self.from_name}</h1>
    </div>

    <div class="content">
        <p>Dear {customer_name},</p>

        <p>Thank you for your business! Please find attached invoice <strong>{invoice_number}</strong>.</p>

        {additional_msg_html}

        <div class="invoice-details">
            <table>
                <tr>
                    <td>Invoice Number:</td>
                    <td>{invoice_number}</td>
                </tr>
                <tr>
                    <td>Amount Due:</td>
                    <td class="amount">${invoice_amount:,.2f}</td>
                </tr>
                <tr>
                    <td>Due Date:</td>
                    <td>{due_date}</td>
                </tr>
            </table>
        </div>

        <p>
            <strong>Payment Instructions:</strong><br>
            Please remit payment by the due date to avoid late fees.
            If you have any questions about this invoice, please don't hesitate to contact us.
        </p>

        <p>The invoice PDF is attached to this email for your records.</p>

        <p>
            Best regards,<br>
            <strong>{self.from_name}</strong>
        </p>
    </div>

    <div class="footer">
        <p>This is an automated message. Please do not reply to this email.</p>
        <p>If you have questions, please contact our accounting department.</p>
    </div>
</body>
</html>
        """
        return html

    def _send_smtp(self, msg: MIMEMultipart, recipients: List[str]):
        """Send email via SMTP"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()

            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)

            server.sendmail(self.from_address, recipients, msg.as_string())

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        pdf_buffer: Optional[BytesIO] = None,
        pdf_filename: str = "attachment.pdf",
        cc_emails: Optional[List[str]] = None
    ) -> bool:
        """
        Send a generic HTML email with optional PDF attachment

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            pdf_buffer: Optional PDF file as BytesIO
            pdf_filename: Filename for PDF attachment
            cc_emails: Optional list of CC email addresses

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{self.from_name} <{self.from_address}>"
            msg['To'] = to_email
            msg['Subject'] = subject

            # Add CC if provided
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)

            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))

            # Attach PDF if provided
            if pdf_buffer:
                pdf_buffer.seek(0)
                pdf_attachment = MIMEApplication(pdf_buffer.read(), _subtype='pdf')
                pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
                msg.attach(pdf_attachment)

            # Prepare recipients list
            recipients = [to_email]
            if cc_emails:
                recipients.extend(cc_emails)

            # Send
            self._send_smtp(msg, recipients)
            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def test_connection(self) -> bool:
        """
        Test SMTP connection

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()

                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)

                logger.info("SMTP connection test successful")
                return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {str(e)}")
            return False
