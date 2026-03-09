"""
E-Signature Reminder Service

Checks for unsigned signature requests older than 3 days and sends reminders
to the signer, the HR user who requested it, and the HR inbox.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload
from hr.db.database import SessionLocal
from hr.models.esignature import SignatureRequest
from hr.services.email import EmailService
from hr.services.signing_service import get_signing_url

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

REMINDER_AFTER_DAYS = 3


def check_unsigned_requests():
    """Check for pending/sent/viewed signature requests older than 3 days and send reminders."""
    db: Session = SessionLocal()
    try:
        cutoff = datetime.now(_ET) - timedelta(days=REMINDER_AFTER_DAYS)

        # Find requests that are still pending/sent/viewed and were created before cutoff
        unsigned = db.query(SignatureRequest).options(
            joinedload(SignatureRequest.creator)
        ).filter(
            SignatureRequest.status.in_(["pending", "sent", "viewed"]),
            SignatureRequest.created_at < cutoff,
            SignatureRequest.signing_token.isnot(None),
            SignatureRequest.token_expires_at > datetime.now(_ET),
        ).all()

        if not unsigned:
            logger.info("E-sign reminder check: no overdue requests found")
            return

        logger.info(f"E-sign reminder check: {len(unsigned)} overdue request(s) found")

        for req in unsigned:
            # Skip if we already reminded today
            last_reminder = req.signing_data.get("last_reminder_date") if req.signing_data else None
            today_str = datetime.now(_ET).strftime("%Y-%m-%d")
            if last_reminder == today_str:
                continue

            try:
                _send_reminder(req, db)

                # Record that we sent a reminder today
                data = dict(req.signing_data) if req.signing_data else {}
                data["last_reminder_date"] = today_str
                reminder_count = data.get("reminder_count", 0) + 1
                data["reminder_count"] = reminder_count
                req.signing_data = data
                db.commit()

                logger.info(f"Sent reminder #{reminder_count} for request {req.id} ({req.document_title})")

            except Exception as e:
                logger.error(f"Failed to send reminder for request {req.id}: {e}")

    except Exception as e:
        logger.error(f"E-sign reminder check failed: {e}", exc_info=True)
    finally:
        db.close()


def _send_reminder(req: SignatureRequest, db: Session):
    """Send reminder emails for an unsigned request."""
    signing_url = get_signing_url(req.signing_token)
    days_pending = (datetime.now(_ET) - req.created_at.replace(tzinfo=_ET)
                    if req.created_at.tzinfo is None
                    else datetime.now(_ET) - req.created_at.astimezone(_ET)).days

    # 1. Email to signer
    signer_text = f"""Hi {req.signer_name.split()[0] if req.signer_name else 'there'},

This is a reminder that you have a document awaiting your signature:

Document: {req.document_title}

This document was sent {days_pending} days ago and still requires your signature.

Please click the link below to review and sign:
{signing_url}

If you have any questions, please contact HR.

Thank you,
SW Hospitality Group HR
"""
    signer_html = f"""<html><body>
<p>Hi {req.signer_name.split()[0] if req.signer_name else 'there'},</p>
<p>This is a reminder that you have a document awaiting your signature:</p>
<p><strong>Document:</strong> {req.document_title}</p>
<p>This document was sent <strong>{days_pending} days ago</strong> and still requires your signature.</p>
<p><a href="{signing_url}" style="display:inline-block;padding:12px 24px;background-color:#E65100;color:#ffffff;text-decoration:none;border-radius:4px;font-weight:bold;">Review & Sign Document</a></p>
<p style="color:#666;font-size:12px;">Or copy this link: {signing_url}</p>
<p>Thank you,<br>SW Hospitality Group HR</p>
</body></html>"""

    EmailService.send_email(
        to_email=req.signer_email,
        subject=f"Reminder: Signature Required — {req.document_title}",
        html_content=signer_html,
        text_content=signer_text
    )

    # 2. Email to HR + request creator
    hr_text = f"""Signature Reminder — Unsigned Document

The following document has been pending for {days_pending} days:

Document: {req.document_title}
Signer: {req.signer_name} ({req.signer_email})
Sent: {req.created_at.strftime('%m/%d/%Y') if req.created_at else 'N/A'}
Status: {req.status}

The signer has been sent a reminder email.

---
SW Hospitality Group HR System
"""

    hr_html = hr_text.replace('\n', '<br>')
    hr_html = f"<html><body><pre>{hr_html}</pre></body></html>"

    config = EmailService.get_smtp_config()
    hr_recipient = config.get('hr_recipient', 'hr@swhgrp.com')
    recipients = {hr_recipient}

    # Add the creator's email
    if req.creator and hasattr(req.creator, 'email') and req.creator.email:
        recipients.add(req.creator.email)

    for recipient in recipients:
        EmailService.send_email(
            to_email=recipient,
            subject=f"Reminder: Unsigned Document — {req.document_title}",
            html_content=hr_html,
            text_content=hr_text
        )
