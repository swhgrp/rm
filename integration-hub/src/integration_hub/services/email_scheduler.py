"""
Background Email Scheduler Service

Automatically checks for new invoice emails on a configurable schedule.
Also handles parse retry scheduling for failed invoice parsing.
Uses APScheduler for background task scheduling.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from integration_hub.db.database import SessionLocal
from integration_hub.services.email_monitor import EmailMonitorService

logger = logging.getLogger(__name__)


# Parse retry configuration
PARSE_RETRY_INTERVAL_MINUTES = 2  # Check for parse retries every 2 minutes
PARSE_RETRY_BATCH_SIZE = 5  # Process up to 5 invoices per batch


class EmailScheduler:
    """Background scheduler for automated email checking"""

    def __init__(self, check_interval_minutes: int = 15):
        """
        Initialize email scheduler

        Args:
            check_interval_minutes: How often to check for new emails (default: 15 minutes)
        """
        self.check_interval = check_interval_minutes
        self.scheduler = BackgroundScheduler()
        self.is_running = False

        logger.info(f"Email scheduler initialized with {check_interval_minutes} minute interval")

    def _check_emails(self):
        """Background task to check for new emails"""
        db = SessionLocal()
        try:
            logger.info("Starting scheduled email check...")
            monitor = EmailMonitorService(db)
            stats = monitor.process_unread_emails()

            logger.info(
                f"Scheduled email check complete. "
                f"Checked: {stats['checked']}, "
                f"Processed: {stats['processed']}, "
                f"Duplicates: {stats['duplicates']}, "
                f"Errors: {stats['errors']}"
            )

        except Exception as e:
            logger.error(f"Error in scheduled email check: {str(e)}", exc_info=True)
        finally:
            db.close()

    def _process_parse_retries(self):
        """Background task to process parse retries for failed invoices"""
        db = SessionLocal()
        try:
            from integration_hub.services.parse_retry_service import get_parse_retry_service

            logger.debug("Starting scheduled parse retry check...")
            retry_service = get_parse_retry_service()
            results = retry_service.process_pending_parses(db, batch_size=PARSE_RETRY_BATCH_SIZE)

            if results['processed'] > 0:
                logger.info(
                    f"Parse retry batch complete. "
                    f"Processed: {results['processed']}, "
                    f"Succeeded: {results['succeeded']}, "
                    f"Failed: {results['failed']}, "
                    f"Permanent failures: {results['permanently_failed']}"
                )

        except Exception as e:
            logger.error(f"Error in scheduled parse retry: {str(e)}", exc_info=True)
        finally:
            db.close()

    def start(self):
        """Start the background scheduler"""
        if self.is_running:
            logger.warning("Email scheduler is already running")
            return

        try:
            # Add job for email checking
            self.scheduler.add_job(
                func=self._check_emails,
                trigger=IntervalTrigger(minutes=self.check_interval),
                id='email_check_job',
                name='Check for new invoice emails',
                replace_existing=True
            )

            # Add job for parse retry processing (more frequent than email checks)
            self.scheduler.add_job(
                func=self._process_parse_retries,
                trigger=IntervalTrigger(minutes=PARSE_RETRY_INTERVAL_MINUTES),
                id='parse_retry_job',
                name='Process invoice parse retries',
                replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True

            logger.info(f"Email scheduler started - emails every {self.check_interval} min, parse retries every {PARSE_RETRY_INTERVAL_MINUTES} min")

        except Exception as e:
            logger.error(f"Failed to start email scheduler: {str(e)}", exc_info=True)
            raise

    def stop(self):
        """Stop the background scheduler"""
        if not self.is_running:
            logger.warning("Email scheduler is not running")
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Email scheduler stopped")

        except Exception as e:
            logger.error(f"Error stopping email scheduler: {str(e)}", exc_info=True)
            raise

    def get_status(self) -> dict:
        """Get scheduler status and next run times"""
        if not self.is_running:
            return {
                "running": False,
                "email_check": {
                    "interval_minutes": self.check_interval,
                    "next_run": None
                },
                "parse_retry": {
                    "interval_minutes": PARSE_RETRY_INTERVAL_MINUTES,
                    "next_run": None
                }
            }

        try:
            email_job = self.scheduler.get_job('email_check_job')
            parse_job = self.scheduler.get_job('parse_retry_job')

            email_next = email_job.next_run_time if email_job else None
            parse_next = parse_job.next_run_time if parse_job else None

            return {
                "running": True,
                "email_check": {
                    "interval_minutes": self.check_interval,
                    "next_run": email_next.isoformat() if email_next else None
                },
                "parse_retry": {
                    "interval_minutes": PARSE_RETRY_INTERVAL_MINUTES,
                    "next_run": parse_next.isoformat() if parse_next else None
                }
            }

        except Exception as e:
            logger.error(f"Error getting scheduler status: {str(e)}")
            return {
                "running": self.is_running,
                "error": str(e)
            }


# Global scheduler instance
_scheduler_instance = None


def get_email_scheduler(check_interval_minutes: int = 15) -> EmailScheduler:
    """
    Get or create the global email scheduler instance

    Args:
        check_interval_minutes: How often to check emails (default: 15 minutes)

    Returns:
        EmailScheduler instance
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = EmailScheduler(check_interval_minutes)

    return _scheduler_instance
