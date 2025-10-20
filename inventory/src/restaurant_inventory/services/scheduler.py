"""
Background Scheduler Service for Automated Tasks

This module handles scheduled background tasks like automatic POS sync.
Uses APScheduler to run periodic tasks.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.models.pos_sale import POSConfiguration
from restaurant_inventory.services.pos_sync import POSSyncService

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
    Periodic task to automatically sync POS data for enabled locations.

    Checks all POS configurations where auto_sync_enabled is True,
    and syncs if enough time has passed since last sync.
    """
    logger.info("Running auto-sync POS task...")
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

        sync_service = POSSyncService(db)
        synced_count = 0

        for config in configs:
            try:
                # Check if sync is due
                if should_sync(config):
                    logger.info(f"Auto-syncing location {config.location_id} ({config.provider})")

                    # Sync last 3 days to catch any missed sales
                    from datetime import date
                    end_date = date.today()
                    start_date = end_date - timedelta(days=3)

                    # Perform sync with inventory deduction enabled
                    synced, skipped, errors = await sync_service.sync_sales(
                        location_id=config.location_id,
                        start_date=start_date,
                        end_date=end_date,
                        deduct_inventory=config.auto_deduct_inventory
                    )

                    logger.info(
                        f"Auto-sync complete for location {config.location_id}: "
                        f"{synced} synced, {skipped} skipped, {len(errors)} errors"
                    )

                    if errors:
                        logger.error(f"Errors during auto-sync for location {config.location_id}: {errors}")

                    synced_count += 1
                else:
                    logger.debug(
                        f"Skipping location {config.location_id} - "
                        f"last sync was {config.last_sync_date}, "
                        f"frequency is {config.sync_frequency_minutes} minutes"
                    )

            except Exception as e:
                logger.error(f"Error auto-syncing location {config.location_id}: {str(e)}")
                logger.error(f"Full traceback:", exc_info=True)
                continue

        if synced_count > 0:
            logger.info(f"Auto-sync task completed: {synced_count} locations synced")
        else:
            logger.debug("Auto-sync task completed: no locations needed syncing")

    except Exception as e:
        logger.error(f"Error in auto-sync task: {str(e)}", exc_info=True)
    finally:
        db.close()


def should_sync(config: POSConfiguration) -> bool:
    """
    Determine if a POS configuration should be synced now.

    Args:
        config: POSConfiguration object

    Returns:
        True if sync is due, False otherwise
    """
    if not config.last_sync_date:
        # Never synced before, sync now
        logger.info(f"Location {config.location_id} has never been synced, will sync now")
        return True

    # Get current time with timezone awareness
    from datetime import timezone as dt_timezone
    now = datetime.now(dt_timezone.utc)

    # Ensure last_sync_date is timezone-aware
    last_sync = config.last_sync_date
    logger.info(f"Location {config.location_id}: last_sync type: {type(last_sync)}, value: {last_sync}, tzinfo: {last_sync.tzinfo if hasattr(last_sync, 'tzinfo') else 'N/A'}")

    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=dt_timezone.utc)
        logger.info(f"Location {config.location_id}: Made last_sync timezone-aware: {last_sync}, tzinfo: {last_sync.tzinfo}")

    # Calculate when next sync should happen
    sync_interval = timedelta(minutes=config.sync_frequency_minutes)
    next_sync_time = last_sync + sync_interval

    logger.info(f"Location {config.location_id}: now type: {type(now)}, tzinfo: {now.tzinfo}")
    logger.info(f"Location {config.location_id}: next_sync_time type: {type(next_sync_time)}, tzinfo: {next_sync_time.tzinfo if hasattr(next_sync_time, 'tzinfo') else 'N/A'}")
    logger.debug(f"Location {config.location_id}: Last sync: {last_sync}, Next sync: {next_sync_time}, Now: {now}")

    # Check if it's time to sync
    return now >= next_sync_time


def start_scheduler():
    """
    Start the background scheduler with all periodic tasks.
    Should be called once at application startup.
    """
    global scheduler

    try:
        scheduler = get_scheduler()

        # Configure APScheduler logging to be more verbose
        import logging as log
        log.getLogger('apscheduler').setLevel(log.INFO)

        # Add auto-sync task - runs every 10 minutes to check if any location needs syncing
        scheduler.add_job(
            auto_sync_pos_task,
            trigger=IntervalTrigger(minutes=10),
            id='auto_sync_pos',
            name='Auto-sync POS data',
            replace_existing=True,
            max_instances=1  # Prevent overlapping executions
        )

        # Start the scheduler
        scheduler.start()
        logger.info("Background scheduler started successfully")
        logger.info("Auto-sync task will run every 10 minutes")
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
