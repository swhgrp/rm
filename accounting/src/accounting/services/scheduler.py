"""
Background Scheduler Service for Automated Tasks

This module handles scheduled background tasks like automatic POS sync for DSS creation.
Uses APScheduler to run periodic tasks.
"""

import logging
from datetime import datetime, date, timedelta, time as time_type
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from accounting.db.database import SessionLocal
from accounting.models.pos import POSConfiguration
from accounting.services.pos_sync_service import POSSyncService

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance"""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def auto_sync_pos_task():
    """
    Periodic task to automatically sync POS data and create DSS entries.

    Runs at configurable times (default 3 AM) for each location.
    Checks all POS configurations where auto_sync_enabled is True,
    syncs the previous day's sales, and creates DSS entries.
    """
    logger.info("Running auto-sync POS task for DSS creation...")
    db: Session = SessionLocal()

    try:
        # Get all configurations with auto-sync enabled
        configs = db.query(POSConfiguration).filter(
            POSConfiguration.auto_sync_enabled == True,
            POSConfiguration.is_active == True
        ).all()

        if not configs:
            logger.debug("No POS configurations with auto-sync enabled")
            return

        synced_count = 0
        error_count = 0

        for config in configs:
            try:
                # Check if it's time to sync (based on configured sync_time)
                if not should_sync_now(config):
                    logger.debug(
                        f"Skipping area {config.area_id} - not sync time yet. "
                        f"Configured sync_time: {config.sync_time}"
                    )
                    continue

                logger.info(f"Auto-syncing POS data for area {config.area_id} ({config.provider})")

                # Create service instance
                sync_service = POSSyncService(db)

                # Sync yesterday's data (the most common use case)
                # Also sync today in case there are late transactions
                yesterday = date.today() - timedelta(days=1)
                today = date.today()

                # Use a system user ID (1 = admin) for auto-created DSS
                # This should be configurable in production
                system_user_id = 1

                result = await sync_service.sync_location(
                    area_id=config.area_id,
                    start_date=yesterday,
                    end_date=today,
                    user_id=system_user_id
                )

                logger.info(
                    f"Auto-sync complete for area {config.area_id}: "
                    f"synced={result.get('synced_count', 0)}, "
                    f"updated={result.get('updated_count', 0)}, "
                    f"errors={result.get('error_count', 0)}"
                )

                if result.get('error_count', 0) > 0:
                    logger.error(f"Errors during auto-sync for area {config.area_id}: {result.get('errors', [])}")

                synced_count += 1

            except Exception as e:
                logger.error(f"Error auto-syncing area {config.area_id}: {str(e)}", exc_info=True)
                error_count += 1
                continue

        logger.info(f"Auto-sync task completed: {synced_count} locations synced, {error_count} errors")

    except Exception as e:
        logger.error(f"Error in auto-sync task: {str(e)}", exc_info=True)
    finally:
        db.close()


def should_sync_now(config: POSConfiguration) -> bool:
    """
    Determine if a POS configuration should be synced now.

    Checks if we're within a reasonable window of the configured sync_time.
    Also checks if we haven't already synced today.

    Args:
        config: POSConfiguration object

    Returns:
        True if sync should happen now, False otherwise
    """
    now = datetime.now()

    # Parse sync_time (format: "HH:MM")
    try:
        sync_hour, sync_minute = map(int, config.sync_time.split(':'))
        configured_sync_time = time_type(sync_hour, sync_minute)
    except (ValueError, AttributeError):
        # Default to 3 AM if parsing fails
        configured_sync_time = time_type(3, 0)
        logger.warning(f"Invalid sync_time '{config.sync_time}' for area {config.area_id}, using default 03:00")

    # Check if we're within 30 minutes of the configured sync time
    # This gives a window for the scheduler which runs every 10 minutes
    current_time = now.time()

    # Convert times to minutes since midnight for comparison
    configured_minutes = configured_sync_time.hour * 60 + configured_sync_time.minute
    current_minutes = current_time.hour * 60 + current_time.minute

    # Allow sync within 30 minutes after configured time
    time_diff = current_minutes - configured_minutes
    if time_diff < 0:
        time_diff += 1440  # Add 24 hours worth of minutes if we wrapped past midnight

    if time_diff > 30:
        return False

    # Check if we already synced today
    if config.last_sync_date:
        last_sync = config.last_sync_date
        if last_sync.date() == now.date():
            logger.debug(f"Area {config.area_id} already synced today at {last_sync}")
            return False

    logger.info(f"Area {config.area_id} is due for sync (sync_time={config.sync_time}, now={current_time})")
    return True


def start_scheduler():
    """
    Start the background scheduler with all periodic tasks.
    Should be called once at application startup.
    """
    global scheduler

    try:
        scheduler = get_scheduler()

        # Configure APScheduler logging
        import logging as log
        log.getLogger('apscheduler').setLevel(log.INFO)

        # Add auto-sync task - runs every 10 minutes to check if any location needs syncing
        # The actual sync only happens at the configured sync_time for each location
        scheduler.add_job(
            auto_sync_pos_task,
            trigger=IntervalTrigger(minutes=10),
            id='auto_sync_pos',
            name='Auto-sync POS data for DSS creation',
            replace_existing=True,
            max_instances=1  # Prevent overlapping executions
        )

        # Start the scheduler
        scheduler.start()
        logger.info("Background scheduler started successfully")
        logger.info("Auto-sync task will check every 10 minutes for locations due for sync")
        logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
        raise


def stop_scheduler():
    """
    Stop the background scheduler.
    Should be called at application shutdown.
    """
    global scheduler

    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Background scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {str(e)}", exc_info=True)
