"""
IMAP Email Monitor Service

Monitors configured email inbox for new invoice emails with PDF and CSV attachments.
Extracts files, generates hash for deduplication, and creates invoice records.
"""

import imaplib
import email
import ssl
import hashlib
import logging
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from integration_hub.models.system_setting import SystemSetting
from integration_hub.models.hub_invoice import HubInvoice
from integration_hub.db.database import SessionLocal

logger = logging.getLogger(__name__)


class EmailMonitorService:
    """Service for monitoring email inbox and processing invoice attachments"""

    # Supported attachment file types
    SUPPORTED_EXTENSIONS = ('.pdf', '.csv')

    def __init__(self, db: Session):
        self.db = db
        self.settings = self._load_settings()
        self.storage_path = Path("/app/uploads")
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _load_settings(self) -> dict:
        """Load email settings from database"""
        settings_query = self.db.query(SystemSetting).filter(
            SystemSetting.is_active == True,
            SystemSetting.category == 'email'
        ).all()

        settings = {}
        for setting in settings_query:
            settings[setting.key] = setting.value

        return settings

    def _get_setting(self, key: str, default: any = None) -> any:
        """Get a specific setting value"""
        return self.settings.get(key, default)

    def connect(self) -> imaplib.IMAP4_SSL:
        """Connect to IMAP server"""
        email_address = self._get_setting('email_address')
        imap_username = self._get_setting('imap_username')
        password = self._get_setting('email_password')
        imap_server = self._get_setting('imap_host', 'imap.gmail.com')
        imap_port = int(self._get_setting('imap_port', '993'))
        use_ssl = self._get_setting('use_ssl', 'true').lower() == 'true'

        # Use imap_username if provided, otherwise fall back to email_address
        username = imap_username if imap_username else email_address

        if not username or not password:
            raise ValueError("Email address and password must be configured in settings")

        logger.info(f"Connecting to {imap_server}:{imap_port} (SSL: {use_ssl})")

        if use_ssl:
            context = ssl.create_default_context()
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, ssl_context=context)
        else:
            mail = imaplib.IMAP4(imap_server, imap_port)

        mail.login(username, password)
        logger.info(f"Successfully logged in as {username}")

        return mail

    def _calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content for deduplication"""
        return hashlib.sha256(file_content).hexdigest()

    def _is_duplicate_invoice(self, file_hash: str) -> bool:
        """Check if invoice with this hash already exists"""
        existing = self.db.query(HubInvoice).filter(
            HubInvoice.invoice_hash == file_hash
        ).first()
        return existing is not None

    def _save_file(self, file_content: bytes, filename: str, file_hash: str) -> Path:
        """Save file to disk with hash-based naming"""
        # Use hash as filename to avoid duplicates
        safe_filename = f"{file_hash[:16]}_{filename}"
        file_path = self.storage_path / safe_filename

        with open(file_path, 'wb') as f:
            f.write(file_content)

        logger.info(f"Saved file to {file_path}")
        return file_path

    def _decode_email_subject(self, subject) -> str:
        """Decode email subject handling various encodings"""
        if subject is None:
            return "No Subject"

        decoded_parts = decode_header(subject)
        subject_text = ""

        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                subject_text += content.decode(encoding or 'utf-8', errors='replace')
            else:
                subject_text += content

        return subject_text

    def _extract_attachments(self, msg: email.message.Message) -> List[Tuple[str, bytes]]:
        """Extract all supported attachments (PDF, CSV) from email message"""
        attachments = []

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if filename and filename.lower().endswith(self.SUPPORTED_EXTENSIONS):
                file_content = part.get_payload(decode=True)
                if file_content:
                    file_type = 'CSV' if filename.lower().endswith('.csv') else 'PDF'
                    logger.info(f"Found {file_type} attachment: {filename} ({len(file_content)} bytes)")
                    attachments.append((filename, file_content))

        return attachments

    def _create_invoice_record(
        self,
        filename: str,
        file_path: Path,
        file_hash: str,
        email_subject: str,
        email_from: str,
        email_date: datetime
    ) -> HubInvoice:
        """Create invoice database record"""
        # Determine file type for status
        is_csv = filename.lower().endswith('.csv')
        initial_status = 'pending_csv' if is_csv else 'pending'

        invoice = HubInvoice(
            invoice_number=None,  # Will be extracted by OCR/parsing
            invoice_date=email_date,
            vendor_name=None,  # Will be extracted by OCR/parsing
            total_amount=0.0,  # Will be extracted by OCR/parsing
            status=initial_status,  # Needs processing
            source='email',
            source_filename=filename,
            pdf_path=str(file_path),  # Also used for CSV path
            invoice_hash=file_hash,
            email_subject=email_subject,
            email_from=email_from,
            email_received_at=email_date
        )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        logger.info(f"Created invoice record ID {invoice.id} for {filename}")
        return invoice

    def process_unread_emails(self) -> dict:
        """
        Check inbox for unread emails and process PDF attachments

        Returns dict with statistics: {
            'checked': int,
            'processed': int,
            'duplicates': int,
            'errors': int
        }
        """
        stats = {
            'checked': 0,
            'processed': 0,
            'duplicates': 0,
            'errors': 0
        }

        mail = None

        try:
            mail = self.connect()

            # Select inbox
            status, messages = mail.select("INBOX")
            if status != "OK":
                logger.error(f"Failed to select INBOX: {status}")
                return stats

            # Search for unread emails
            # Emails will be marked as read after processing to prevent re-processing
            status, message_ids = mail.search(None, "UNSEEN")
            if status != "OK":
                logger.error(f"Failed to search for unread emails: {status}")
                return stats

            message_id_list = message_ids[0].split()
            stats['checked'] = len(message_id_list)

            logger.info(f"Found {stats['checked']} unread emails")

            for msg_id in message_id_list:
                try:
                    # Fetch email
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        logger.error(f"Failed to fetch message {msg_id}")
                        stats['errors'] += 1
                        continue

                    # Parse email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Get email metadata
                    email_from = msg.get("From", "Unknown")
                    email_subject = self._decode_email_subject(msg.get("Subject"))
                    email_date_str = msg.get("Date")
                    email_date = datetime.now()  # Fallback

                    if email_date_str:
                        try:
                            email_date = email.utils.parsedate_to_datetime(email_date_str)
                        except:
                            pass

                    logger.info(f"Processing email from {email_from}: {email_subject}")

                    # Extract PDF and CSV attachments
                    attachments = self._extract_attachments(msg)

                    if not attachments:
                        logger.info(f"No supported attachments (PDF/CSV) found in email {msg_id}")
                        continue

                    # Process each attachment
                    for filename, file_content in attachments:
                        try:
                            # Calculate hash
                            file_hash = self._calculate_file_hash(file_content)

                            # Check for duplicates
                            if self._is_duplicate_invoice(file_hash):
                                logger.warning(f"Duplicate invoice detected: {filename} (hash: {file_hash[:16]}...)")
                                stats['duplicates'] += 1
                                continue

                            # Save file (PDF or CSV)
                            file_path = self._save_file(file_content, filename, file_hash)

                            # Create invoice record
                            invoice = self._create_invoice_record(
                                filename=filename,
                                file_path=file_path,
                                file_hash=file_hash,
                                email_subject=email_subject,
                                email_from=email_from,
                                email_date=email_date
                            )

                            # Auto-parse the invoice
                            is_csv = filename.lower().endswith('.csv')
                            if is_csv:
                                # Parse CSV invoices
                                try:
                                    from integration_hub.services.csv_invoice_parser import get_csv_parser
                                    csv_parser = get_csv_parser(self.db)
                                    parse_result = csv_parser.process_hub_invoice(invoice.id)
                                    if parse_result['success']:
                                        logger.info(f"Auto-parsed CSV invoice {invoice.id}: {parse_result['message']}")
                                    else:
                                        logger.warning(f"Failed to auto-parse CSV invoice {invoice.id}: {parse_result['message']}")
                                except Exception as e:
                                    logger.error(f"Error auto-parsing CSV invoice {invoice.id}: {str(e)}")
                                    # Don't fail the email processing if parsing fails
                            else:
                                # Parse PDF invoices with OCR
                                try:
                                    from integration_hub.services.invoice_parser import get_invoice_parser
                                    parser = get_invoice_parser()
                                    parse_result = parser.parse_and_save(invoice.id, self.db)
                                    if parse_result['success']:
                                        logger.info(f"Auto-parsed invoice {invoice.id}: {parse_result['message']}")
                                    else:
                                        logger.warning(f"Failed to auto-parse invoice {invoice.id}: {parse_result['message']}")
                                except Exception as e:
                                    logger.error(f"Error auto-parsing invoice {invoice.id}: {str(e)}")
                                    # Don't fail the email processing if parsing fails

                            stats['processed'] += 1

                        except Exception as e:
                            logger.error(f"Error processing attachment {filename}: {str(e)}")
                            stats['errors'] += 1

                    # Mark email as read after processing all attachments
                    try:
                        mail.store(msg_id, '+FLAGS', '\\Seen')
                        logger.debug(f"Marked email {msg_id} as read")
                    except Exception as e:
                        logger.warning(f"Failed to mark email {msg_id} as read: {str(e)}")

                except Exception as e:
                    logger.error(f"Error processing email {msg_id}: {str(e)}")
                    stats['errors'] += 1

        except Exception as e:
            logger.error(f"Error in email monitor: {str(e)}")
            stats['errors'] += 1

        finally:
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except:
                    pass

        logger.info(f"Email processing complete. Stats: {stats}")
        return stats


def get_email_monitor_service() -> EmailMonitorService:
    """Get email monitor service instance"""
    db = SessionLocal()
    return EmailMonitorService(db)
