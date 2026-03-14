"""
Background Scheduler Service for Automated Tasks

This module handles scheduled background tasks like automatic POS sync for DSS creation.
Uses APScheduler to run periodic tasks.
"""

import logging
import os
import uuid
from datetime import datetime, date, timedelta, time as time_type, timezone
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
                # Pass db session so we can check if yesterday's DSS already exists
                if not should_sync_now(config, db):
                    logger.debug(
                        f"Skipping area {config.area_id} - not sync time yet or already synced. "
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


def should_sync_now(config: POSConfiguration, db: Session = None) -> bool:
    """
    Determine if a POS configuration should be synced now.

    Syncs if:
    1. We're within the configured sync window (30 min after sync_time), OR
    2. Yesterday's DSS doesn't exist (catch-up mechanism)

    Args:
        config: POSConfiguration object
        db: Database session (optional, used to check if yesterday's DSS exists)

    Returns:
        True if sync should happen now, False otherwise
    """
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).date()

    # First, check if yesterday's DSS already exists - if so, no need to sync
    if db:
        from accounting.models.daily_sales_summary import DailySalesSummary
        existing_dss = db.query(DailySalesSummary).filter(
            DailySalesSummary.area_id == config.area_id,
            DailySalesSummary.business_date == yesterday,
            DailySalesSummary.imported_from_pos == True  # Only check POS entries, not manual
        ).first()

        if existing_dss:
            logger.debug(f"Area {config.area_id} already has DSS for {yesterday}, skipping auto-sync")
            return False

        # If yesterday's DSS doesn't exist, sync regardless of time window (catch-up)
        logger.info(f"Area {config.area_id} missing DSS for {yesterday}, triggering catch-up sync")
        return True

    # Fallback when no db session: use time window logic
    # Parse sync_time (format: "HH:MM")
    try:
        sync_hour, sync_minute = map(int, config.sync_time.split(':'))
        configured_sync_time = time_type(sync_hour, sync_minute)
    except (ValueError, AttributeError):
        # Default to 3 AM if parsing fails
        configured_sync_time = time_type(3, 0)
        logger.warning(f"Invalid sync_time '{config.sync_time}' for area {config.area_id}, using default 03:00")

    # Check if we're within 30 minutes of the configured sync time
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

    # Check if we already synced within the sync window today
    if config.last_sync_date:
        last_sync = config.last_sync_date
        sync_time_today = datetime.combine(now.date(), configured_sync_time)
        if last_sync >= sync_time_today:
            logger.debug(f"Area {config.area_id} already synced after {sync_time_today}")
            return False

    logger.info(f"Area {config.area_id} is due for sync (sync_time={config.sync_time}, now={current_time}, target_date={yesterday})")
    return True


async def catchup_missed_syncs():
    """
    On startup, check for any missed days and sync them.
    This handles cases where the container was down during the normal sync window.
    """
    logger.info("Checking for missed POS syncs on startup...")
    db: Session = SessionLocal()

    try:
        from accounting.models.daily_sales_summary import DailySalesSummary

        # Get all configurations with auto-sync enabled
        configs = db.query(POSConfiguration).filter(
            POSConfiguration.auto_sync_enabled == True,
            POSConfiguration.is_active == True
        ).all()

        if not configs:
            logger.info("No POS configurations with auto-sync enabled")
            return

        today = date.today()
        system_user_id = 1
        total_synced = 0

        for config in configs:
            try:
                # Find the last date we have DSS data for this area
                last_dss = db.query(DailySalesSummary).filter(
                    DailySalesSummary.area_id == config.area_id
                ).order_by(DailySalesSummary.business_date.desc()).first()

                if last_dss:
                    last_date = last_dss.business_date
                else:
                    # If no DSS, start from 7 days ago
                    last_date = today - timedelta(days=7)

                # Calculate days to catch up (from last_date + 1 to yesterday)
                yesterday = today - timedelta(days=1)
                start_catchup = last_date + timedelta(days=1)

                if start_catchup > yesterday:
                    logger.debug(f"Area {config.area_id}: No missed days to catch up (last DSS: {last_date})")
                    continue

                days_missed = (yesterday - last_date).days
                if days_missed > 0:
                    logger.info(f"Area {config.area_id}: Catching up {days_missed} missed day(s) from {start_catchup} to {yesterday}")

                    sync_service = POSSyncService(db)
                    result = await sync_service.sync_location(
                        area_id=config.area_id,
                        start_date=start_catchup,
                        end_date=yesterday,
                        user_id=system_user_id
                    )

                    synced = result.get('synced_count', 0)
                    total_synced += synced
                    logger.info(f"Area {config.area_id}: Caught up {synced} days")

            except Exception as e:
                logger.error(f"Error catching up area {config.area_id}: {str(e)}", exc_info=True)
                continue

        if total_synced > 0:
            logger.info(f"Startup catchup complete: synced {total_synced} total days across all locations")
        else:
            logger.info("Startup catchup: No missed days found")

    except Exception as e:
        logger.error(f"Error in startup catchup: {str(e)}", exc_info=True)
    finally:
        db.close()


async def nightly_gl_sweep():
    """
    Nightly GL anomaly detection sweep.
    Runs rules engine + AI analysis for each active area, covering the last 7 days.
    """
    from accounting.models.area import Area
    from accounting.gl_review.models import GLAnomalyFlag, STATUS_OPEN, STATUS_SUPERSEDED, STATUS_DISMISSED, STATUS_REVIEWED
    from accounting.gl_review.rules_engine import run_rules_engine
    from accounting.gl_review.ai_analyzer import analyze_flags_with_ai
    from accounting.gl_review.baselines import compute_baselines

    logger.info("Starting nightly GL anomaly sweep...")
    db: Session = SessionLocal()

    try:
        # Retention cleanup: delete closed flags older than 90 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        deleted = (
            db.query(GLAnomalyFlag)
            .filter(
                GLAnomalyFlag.status.in_([STATUS_DISMISSED, STATUS_REVIEWED, STATUS_SUPERSEDED]),
                GLAnomalyFlag.created_at < cutoff,
            )
            .delete(synchronize_session='fetch')
        )
        if deleted:
            db.commit()
            logger.info(f"Retention cleanup: deleted {deleted} old closed flags")

        areas = db.query(Area).filter(Area.is_active == True).all()
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

        for area in areas:
            run_start = datetime.now(timezone.utc)
            run_id = str(uuid.uuid4())
            today = date.today()
            date_from = today - timedelta(days=7)

            try:
                flags = run_rules_engine(db, area.id, date_from, today)

                if has_api_key and flags:
                    period_label = f"{date_from} to {today}"
                    flags = analyze_flags_with_ai(flags, area.id, area.name, period_label)

                for flag_dict in flags:
                    flag = GLAnomalyFlag(
                        area_id=area.id,
                        journal_entry_id=flag_dict.get('journal_entry_id'),
                        journal_entry_line_id=flag_dict.get('journal_entry_line_id'),
                        account_id=flag_dict.get('account_id'),
                        flag_type=flag_dict['flag_type'],
                        severity=flag_dict['severity'],
                        title=flag_dict['title'],
                        detail=flag_dict.get('detail'),
                        flagged_value=flag_dict.get('flagged_value'),
                        expected_range_low=flag_dict.get('expected_range_low'),
                        expected_range_high=flag_dict.get('expected_range_high'),
                        period_date=flag_dict.get('period_date'),
                        status=STATUS_OPEN,
                        ai_reasoning=flag_dict.get('ai_reasoning'),
                        ai_confidence=flag_dict.get('ai_confidence'),
                        run_id=run_id,
                    )
                    db.add(flag)

                db.commit()
                elapsed = (datetime.now(timezone.utc) - run_start).total_seconds()
                logger.info(
                    f"GL sweep for {area.name} (area_id={area.id}): "
                    f"run_id={run_id}, {len(flags)} flags, {elapsed:.1f}s"
                )

            except Exception:
                db.rollback()
                logger.exception(f"GL sweep failed for area {area.name} (area_id={area.id})")

        logger.info("Nightly GL anomaly sweep completed")

    except Exception:
        logger.exception("Error in nightly GL sweep")
    finally:
        db.close()


async def monthly_baseline_rebuild():
    """
    Monthly GL account baseline rebuild.
    Recomputes statistical baselines for all active areas using 12 months of history.
    """
    from accounting.models.area import Area
    from accounting.gl_review.baselines import compute_baselines

    logger.info("Starting monthly GL baseline rebuild...")
    db: Session = SessionLocal()

    try:
        areas = db.query(Area).filter(Area.is_active == True).all()
        total_accounts = 0

        for area in areas:
            try:
                count = compute_baselines(db, area.id, lookback_months=12)
                total_accounts += count
                logger.info(f"Baselines rebuilt for {area.name}: {count} accounts")
            except Exception:
                logger.exception(f"Baseline rebuild failed for area {area.name}")

        logger.info(f"Monthly baseline rebuild completed: {total_accounts} total accounts across {len(areas)} areas")

    except Exception:
        logger.exception("Error in monthly baseline rebuild")
    finally:
        db.close()


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

        # Add startup catchup task - runs once immediately to sync any missed days
        scheduler.add_job(
            catchup_missed_syncs,
            trigger='date',  # Run once immediately
            id='startup_catchup',
            name='Startup catchup for missed POS syncs',
            replace_existing=True
        )

        # Add nightly GL anomaly sweep - runs at 3 AM daily
        scheduler.add_job(
            nightly_gl_sweep,
            trigger=CronTrigger(hour=3, minute=0),
            id='nightly_gl_sweep',
            name='Nightly GL anomaly detection sweep',
            replace_existing=True,
            max_instances=1
        )

        # Add monthly GL baseline rebuild - runs at 4 AM on the 1st of each month
        scheduler.add_job(
            monthly_baseline_rebuild,
            trigger=CronTrigger(day=1, hour=4, minute=0),
            id='monthly_baseline_rebuild',
            name='Monthly GL account baseline rebuild',
            replace_existing=True,
            max_instances=1
        )

        # Start the scheduler
        scheduler.start()
        logger.info("Background scheduler started successfully")
        logger.info("Auto-sync task will check every 10 minutes for locations due for sync")
        logger.info("Startup catchup task will run immediately to sync any missed days")
        logger.info("GL sweep scheduled daily at 3:00 AM, baseline rebuild monthly at 4:00 AM on 1st")
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
