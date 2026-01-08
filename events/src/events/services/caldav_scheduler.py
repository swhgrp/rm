"""CalDAV sync scheduler for periodic bidirectional sync"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from events.core.database import SessionLocal
from events.models import User
from events.services.caldav_sync_service import CalDAVSyncService
from events.core.config import settings

logger = logging.getLogger(__name__)


class CalDAVScheduler:
    """Scheduler for periodic CalDAV sync operations"""

    def __init__(self):
        self.sync_service = CalDAVSyncService()
        self.running = False

    async def start(self):
        """Start the scheduler background task"""
        if not settings.CALDAV_ENABLED:
            logger.info("CalDAV sync is disabled, scheduler not starting")
            return

        self.running = True
        logger.info("CalDAV scheduler started")
        asyncio.create_task(self._sync_loop())

    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("CalDAV scheduler stopped")

    async def _sync_loop(self):
        """Main sync loop - runs every 15 minutes"""
        while self.running:
            try:
                await self._run_sync()
            except Exception as e:
                logger.error(f"Error in CalDAV sync loop: {e}")

            # Wait 15 minutes before next sync
            await asyncio.sleep(15 * 60)

    async def _run_sync(self):
        """Run sync for all active users"""
        logger.info("Starting periodic CalDAV sync")
        db = SessionLocal()

        try:
            # Get all active users
            users = db.query(User).filter(User.is_active == True).all()

            for user in users:
                try:
                    # Pull changes from CalDAV for each user
                    results = self.sync_service.pull_caldav_changes(db, user.email)
                    if results['updated'] > 0 or results['deleted'] > 0:
                        logger.info(f"CalDAV sync for {user.email}: {results}")
                except Exception as e:
                    logger.error(f"Failed to sync CalDAV for user {user.email}: {e}")

            logger.info("Periodic CalDAV sync complete")

        except Exception as e:
            logger.error(f"Error during CalDAV sync: {e}")
        finally:
            db.close()


# Global scheduler instance
caldav_scheduler = CalDAVScheduler()
