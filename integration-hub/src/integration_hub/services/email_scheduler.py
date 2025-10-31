"""
Background Email Scheduler Service

Automatically checks for new invoice emails on a configurable schedule.
Uses APScheduler for background task scheduling.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from integration_hub.db.database import SessionLocal
from integration_hub.services.email_monitor import EmailMonitorService

logger = logging.getLogger(__name__)


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

    def start(self):
        """Start the background scheduler"""
        if self.is_running:
            logger.warning("Email scheduler is already running")
            return

        try:
            # Add job with interval trigger
            self.scheduler.add_job(
                func=self._check_emails,
                trigger=IntervalTrigger(minutes=self.check_interval),
                id='email_check_job',
                name='Check for new invoice emails',
                replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True

            logger.info(f"Email scheduler started - checking every {self.check_interval} minutes")

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
        """Get scheduler status and next run time"""
        if not self.is_running:
            return {
                "running": False,
                "interval_minutes": self.check_interval,
                "next_run": None
            }

        try:
            job = self.scheduler.get_job('email_check_job')
            next_run = job.next_run_time if job else None

            return {
                "running": True,
                "interval_minutes": self.check_interval,
                "next_run": next_run.isoformat() if next_run else None
            }

        except Exception as e:
            logger.error(f"Error getting scheduler status: {str(e)}")
            return {
                "running": self.is_running,
                "interval_minutes": self.check_interval,
                "next_run": None,
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
