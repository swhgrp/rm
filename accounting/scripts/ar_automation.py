#!/usr/bin/env python3
"""
AR Automation Script

Processes recurring invoices and sends payment reminders.
Run this script daily via cron.
"""
import sys
import os
from pathlib import Path

# Add the src directory to the Python path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

import logging
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from accounting.core.config import settings
from accounting.services.recurring_invoice_service import RecurringInvoiceService
from accounting.services.payment_reminder_service import PaymentReminderService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/accounting/ar_automation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main automation routine"""
    logger.info("=" * 80)
    logger.info("AR Automation Started")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 80)

    try:
        # Create database connection
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        try:
            # Process Recurring Invoices
            logger.info("-" * 80)
            logger.info("Processing Recurring Invoices...")
            logger.info("-" * 80)

            recurring_service = RecurringInvoiceService(db)
            generated_invoices = recurring_service.process_due_invoices()

            logger.info(f"Recurring invoices processed: {len(generated_invoices)} invoices generated")

            for invoice in generated_invoices:
                logger.info(f"  - Generated: {invoice.invoice_number} for customer {invoice.customer_id}, Amount: ${invoice.total_amount}")

            # Process Payment Reminders
            logger.info("-" * 80)
            logger.info("Processing Payment Reminders...")
            logger.info("-" * 80)

            reminder_service = PaymentReminderService(db)
            reminder_stats = reminder_service.process_overdue_invoices()

            logger.info(f"Payment reminders processed:")
            logger.info(f"  - Enabled: {reminder_stats['enabled']}")
            logger.info(f"  - Invoices Processed: {reminder_stats['processed']}")
            logger.info(f"  - Reminders Sent: {reminder_stats['reminders_sent']}")
            logger.info(f"  - Skipped: {reminder_stats.get('skipped', 0)}")
            logger.info(f"  - Errors: {reminder_stats['errors']}")

            # Summary
            logger.info("=" * 80)
            logger.info("AR Automation Completed Successfully")
            logger.info(f"Summary:")
            logger.info(f"  - {len(generated_invoices)} recurring invoices generated")
            logger.info(f"  - {reminder_stats['reminders_sent']} payment reminders sent")
            logger.info("=" * 80)

            db.close()
            return 0

        except Exception as e:
            logger.error(f"Error during automation: {str(e)}", exc_info=True)
            db.rollback()
            db.close()
            return 1

    except Exception as e:
        logger.error(f"Failed to initialize automation: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
