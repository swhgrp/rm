"""
Settings API endpoints for system configuration
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
from integration_hub.db.database import get_db
from integration_hub.models.system_setting import SystemSetting
from integration_hub.services.email_monitor import EmailMonitorService
from integration_hub.services.email_scheduler import get_email_scheduler
import imaplib
import ssl
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SettingUpdate(BaseModel):
    """Model for updating a single setting"""
    category: str
    key: str
    value: Optional[str] = None
    is_encrypted: bool = False


class BulkSettingsUpdate(BaseModel):
    """Model for bulk settings update"""
    settings: List[SettingUpdate]


class EmailTestRequest(BaseModel):
    """Model for testing email connection"""
    email_address: str
    imap_username: str
    email_password: str
    imap_host: str
    imap_port: int
    use_ssl: bool


@router.get("/")
def get_settings(
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all settings or filter by category
    """
    query = db.query(SystemSetting).filter(SystemSetting.is_active == True)

    if category:
        query = query.filter(SystemSetting.category == category)

    settings = query.all()

    # Convert to dict format for frontend
    result = {}
    for setting in settings:
        key = f"{setting.category}.{setting.key}"
        result[key] = {
            "value": setting.value,
            "is_encrypted": setting.is_encrypted,
            "description": setting.description
        }

    return result


@router.post("/bulk")
def save_settings(
    bulk_update: BulkSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Save multiple settings at once
    """
    updated_count = 0
    created_count = 0

    for setting_data in bulk_update.settings:
        # Check if setting exists
        existing = db.query(SystemSetting).filter(
            SystemSetting.category == setting_data.category,
            SystemSetting.key == setting_data.key
        ).first()

        if existing:
            # Update existing setting
            existing.value = setting_data.value
            existing.is_encrypted = setting_data.is_encrypted
            existing.updated_by = None  # No auth tracking for now
            updated_count += 1
        else:
            # Create new setting
            new_setting = SystemSetting(
                category=setting_data.category,
                key=setting_data.key,
                value=setting_data.value,
                is_encrypted=setting_data.is_encrypted,
                updated_by=None  # No auth tracking for now
            )
            db.add(new_setting)
            created_count += 1

    db.commit()

    return {
        "success": True,
        "updated": updated_count,
        "created": created_count,
        "total": updated_count + created_count
    }


@router.post("/test-email")
def test_email_connection(
    test_request: EmailTestRequest
):
    """
    Test IMAP email connection with provided credentials
    """
    try:
        # Create SSL context
        if test_request.use_ssl:
            context = ssl.create_default_context()
            mail = imaplib.IMAP4_SSL(
                test_request.imap_host,
                test_request.imap_port,
                ssl_context=context
            )
        else:
            mail = imaplib.IMAP4(
                test_request.imap_host,
                test_request.imap_port
            )

        # Attempt login (use username, not email address)
        mail.login(test_request.imap_username, test_request.email_password)

        # Try to select INBOX to verify full access
        status, messages = mail.select("INBOX")

        if status != "OK":
            raise Exception("Could not access INBOX")

        # Get mailbox info
        message_count = int(messages[0])

        # Logout
        mail.logout()

        return {
            "success": True,
            "message": f"Connection successful! Found {message_count} messages in INBOX.",
            "details": {
                "server": test_request.imap_host,
                "port": test_request.imap_port,
                "ssl": test_request.use_ssl,
                "inbox_count": message_count
            }
        }

    except imaplib.IMAP4.error as e:
        return {
            "success": False,
            "message": f"IMAP error: {str(e)}",
            "error_type": "authentication"
        }

    except ssl.SSLError as e:
        return {
            "success": False,
            "message": f"SSL error: {str(e)}",
            "error_type": "ssl"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "error_type": "connection"
        }


@router.post("/check-email")
def check_email_now(db: Session = Depends(get_db)):
    """
    Manually trigger email check for new invoices.
    Connects to configured email account, checks for unread emails with PDF attachments,
    and creates invoice records for any new invoices found.
    """
    try:
        # Create email monitor service
        monitor = EmailMonitorService(db)

        # Process unread emails
        stats = monitor.process_unread_emails()

        return {
            "success": True,
            "message": f"Email check completed. Processed {stats['processed']} new invoices.",
            "stats": {
                "emails_checked": stats['checked'],
                "invoices_processed": stats['processed'],
                "duplicates_skipped": stats['duplicates'],
                "errors": stats['errors']
            }
        }

    except ValueError as e:
        # Typically missing email configuration
        logger.error(f"Configuration error checking email: {str(e)}")
        return {
            "success": False,
            "message": f"Configuration error: {str(e)}",
            "error_type": "configuration"
        }

    except Exception as e:
        logger.error(f"Error checking email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check email: {str(e)}"
        )


@router.get("/scheduler-status")
def get_scheduler_status():
    """
    Get the current status of the email scheduler.
    Returns information about whether it's running and when the next check will occur.
    """
    try:
        scheduler = get_email_scheduler()
        status = scheduler.get_status()
        return {
            "success": True,
            **status
        }
    except Exception as e:
        logger.error(f"Error getting scheduler status: {str(e)}")
        return {
            "success": False,
            "running": False,
            "error": str(e)
        }


# ============================================================================
# VENDOR PARSING RULES
# ============================================================================

class VendorParsingRuleCreate(BaseModel):
    """Model for creating/updating a vendor parsing rule"""
    vendor_id: int
    quantity_column: Optional[str] = None
    item_code_column: Optional[str] = None
    price_column: Optional[str] = None
    pack_size_format: Optional[str] = None
    date_format: Optional[str] = None
    ai_instructions: Optional[str] = None
    post_parse_rules: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


@router.get("/vendor-parsing-rules")
def get_vendor_parsing_rules(
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get all vendor parsing rules or filter by vendor_id.
    Returns rules with vendor name for display.
    """
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule
    from integration_hub.models.vendor import Vendor

    query = db.query(VendorParsingRule).join(Vendor)

    if vendor_id:
        query = query.filter(VendorParsingRule.vendor_id == vendor_id)

    rules = query.order_by(Vendor.name).all()

    return [rule.to_dict() for rule in rules]


@router.get("/vendor-parsing-rules/{rule_id}")
def get_vendor_parsing_rule(
    rule_id: int,
    db: Session = Depends(get_db)
):
    """Get a single vendor parsing rule by ID"""
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule

    rule = db.query(VendorParsingRule).filter(VendorParsingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Parsing rule not found")

    return rule.to_dict()


@router.post("/vendor-parsing-rules")
def create_vendor_parsing_rule(
    rule_data: VendorParsingRuleCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new vendor parsing rule.
    Only one rule is allowed per vendor.
    """
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule
    from integration_hub.models.vendor import Vendor

    # Verify vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == rule_data.vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Check if rule already exists for this vendor
    existing = db.query(VendorParsingRule).filter(
        VendorParsingRule.vendor_id == rule_data.vendor_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"A parsing rule already exists for vendor '{vendor.name}'. Use PUT to update."
        )

    # Create new rule
    rule = VendorParsingRule(
        vendor_id=rule_data.vendor_id,
        quantity_column=rule_data.quantity_column,
        item_code_column=rule_data.item_code_column,
        price_column=rule_data.price_column,
        pack_size_format=rule_data.pack_size_format,
        date_format=rule_data.date_format,
        ai_instructions=rule_data.ai_instructions,
        post_parse_rules=rule_data.post_parse_rules,
        notes=rule_data.notes,
        is_active=rule_data.is_active
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(f"Created parsing rule for vendor {vendor.name} (ID: {rule.id})")

    return rule.to_dict()


@router.put("/vendor-parsing-rules/{rule_id}")
def update_vendor_parsing_rule(
    rule_id: int,
    rule_data: VendorParsingRuleCreate,
    db: Session = Depends(get_db)
):
    """Update an existing vendor parsing rule"""
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule

    rule = db.query(VendorParsingRule).filter(VendorParsingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Parsing rule not found")

    # Update fields
    rule.quantity_column = rule_data.quantity_column
    rule.item_code_column = rule_data.item_code_column
    rule.price_column = rule_data.price_column
    rule.pack_size_format = rule_data.pack_size_format
    rule.date_format = rule_data.date_format
    rule.ai_instructions = rule_data.ai_instructions
    rule.post_parse_rules = rule_data.post_parse_rules
    rule.notes = rule_data.notes
    rule.is_active = rule_data.is_active

    db.commit()
    db.refresh(rule)

    logger.info(f"Updated parsing rule {rule_id} for vendor {rule.vendor.name}")

    return rule.to_dict()


@router.delete("/vendor-parsing-rules/{rule_id}")
def delete_vendor_parsing_rule(
    rule_id: int,
    db: Session = Depends(get_db)
):
    """Delete a vendor parsing rule"""
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule

    rule = db.query(VendorParsingRule).filter(VendorParsingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Parsing rule not found")

    vendor_name = rule.vendor.name if rule.vendor else "Unknown"
    db.delete(rule)
    db.commit()

    logger.info(f"Deleted parsing rule {rule_id} for vendor {vendor_name}")

    return {"success": True, "message": f"Parsing rule for {vendor_name} deleted"}


@router.get("/vendors-without-rules")
def get_vendors_without_parsing_rules(db: Session = Depends(get_db)):
    """
    Get list of vendors that don't have parsing rules configured.
    Useful for the UI to show which vendors need rules.
    """
    from integration_hub.models.vendor import Vendor
    from integration_hub.models.vendor_parsing_rule import VendorParsingRule
    from sqlalchemy import not_, exists

    # Subquery to find vendors with rules
    has_rule = db.query(VendorParsingRule.vendor_id).filter(
        VendorParsingRule.vendor_id == Vendor.id
    ).exists()

    # Get vendors without rules
    vendors = db.query(Vendor).filter(
        Vendor.is_active == True,
        ~has_rule
    ).order_by(Vendor.name).all()

    return [
        {"id": v.id, "name": v.name}
        for v in vendors
    ]
