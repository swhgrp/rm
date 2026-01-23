"""Background Scheduler Service"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from forms.config import settings
from forms.database import AsyncSessionLocal
from forms.models import (
    FormSubmission, WorkflowInstance, SignatureRequest,
    NotificationPreference, SubmissionStatus, WorkflowStatus
)

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def check_workflow_escalations():
    """Check for workflows that need escalation."""
    logger.debug("Running workflow escalation check")

    async with AsyncSessionLocal() as db:
        try:
            # Find workflows with overdue steps
            overdue_threshold = datetime.utcnow() - timedelta(hours=48)

            result = await db.execute(
                select(WorkflowInstance)
                .where(
                    WorkflowInstance.status == WorkflowStatus.IN_PROGRESS,
                    WorkflowInstance.updated_at < overdue_threshold
                )
            )

            overdue_workflows = result.scalars().all()

            for workflow in overdue_workflows:
                logger.info(f"Workflow {workflow.id} is overdue for escalation")
                # TODO: Implement escalation logic
                # - Check workflow definition for escalation rules
                # - Reassign to escalation target
                # - Send notification

            logger.debug(f"Found {len(overdue_workflows)} overdue workflows")

        except Exception as e:
            logger.error(f"Error in escalation check: {e}")


async def check_signature_expiration():
    """Check for expired signature requests."""
    logger.debug("Running signature expiration check")

    async with AsyncSessionLocal() as db:
        try:
            now = datetime.utcnow()

            # Find expired unfulfilled signature requests
            result = await db.execute(
                select(SignatureRequest)
                .where(
                    SignatureRequest.is_fulfilled == False,
                    SignatureRequest.expires_at < now
                )
            )

            expired = result.scalars().all()

            for request in expired:
                logger.info(f"Signature request {request.id} has expired")
                # TODO: Send notification about expired request

            logger.debug(f"Found {len(expired)} expired signature requests")

        except Exception as e:
            logger.error(f"Error in signature expiration check: {e}")


async def send_daily_digests():
    """Send daily digest emails to users who have opted in."""
    logger.info("Running daily digest job")

    async with AsyncSessionLocal() as db:
        try:
            from forms.services.notification_service import get_notification_service

            # Get users with digest mode enabled
            result = await db.execute(
                select(NotificationPreference)
                .where(
                    NotificationPreference.email_enabled == True,
                    NotificationPreference.digest_mode == True
                )
            )

            preferences = result.scalars().all()

            notification_service = get_notification_service()

            for pref in preferences:
                employee_id = pref.employee_id

                # Get pending signatures for this user
                sig_result = await db.execute(
                    select(SignatureRequest)
                    .where(
                        SignatureRequest.requested_employee_id == employee_id,
                        SignatureRequest.is_fulfilled == False
                    )
                )
                pending_signatures = [
                    {"id": str(s.id), "submission_id": str(s.submission_id)}
                    for s in sig_result.scalars().all()
                ]

                # Get pending workflow tasks
                # (simplified - would need workflow engine)
                pending_reviews = []

                # Get recent submissions
                sub_result = await db.execute(
                    select(FormSubmission)
                    .where(FormSubmission.submitted_by_employee_id == employee_id)
                    .order_by(FormSubmission.created_at.desc())
                    .limit(5)
                )
                recent_submissions = [
                    {
                        "id": str(s.id),
                        "reference_number": s.reference_number,
                        "status": s.status.value
                    }
                    for s in sub_result.scalars().all()
                ]

                if pending_signatures or pending_reviews:
                    # TODO: Get employee email from HR service
                    # await notification_service.send_daily_digest(
                    #     to_email=employee_email,
                    #     employee_name=employee_name,
                    #     pending_signatures=pending_signatures,
                    #     pending_reviews=pending_reviews,
                    #     recent_submissions=recent_submissions
                    # )
                    pass

            logger.info(f"Processed daily digests for {len(preferences)} users")

        except Exception as e:
            logger.error(f"Error sending daily digests: {e}")


async def cleanup_old_drafts():
    """Clean up old draft submissions that were never submitted."""
    logger.debug("Running draft cleanup job")

    async with AsyncSessionLocal() as db:
        try:
            # Delete drafts older than 30 days
            cutoff = datetime.utcnow() - timedelta(days=30)

            result = await db.execute(
                select(FormSubmission)
                .where(
                    FormSubmission.status == SubmissionStatus.DRAFT,
                    FormSubmission.created_at < cutoff
                )
            )

            old_drafts = result.scalars().all()

            for draft in old_drafts:
                logger.info(f"Deleting old draft {draft.id} ({draft.reference_number})")
                await db.delete(draft)

            await db.commit()
            logger.debug(f"Deleted {len(old_drafts)} old drafts")

        except Exception as e:
            logger.error(f"Error in draft cleanup: {e}")


async def apply_retention_policies():
    """Apply data retention policies to archived submissions."""
    logger.info("Running retention policy check")

    async with AsyncSessionLocal() as db:
        try:
            # Get archived submissions past their retention period
            from forms.models import FormTemplate
            from sqlalchemy.orm import selectinload

            result = await db.execute(
                select(FormSubmission)
                .options(selectinload(FormSubmission.template))
                .where(
                    FormSubmission.status == SubmissionStatus.ARCHIVED,
                    FormSubmission.archived_at.isnot(None)
                )
            )

            archived = result.scalars().all()

            for submission in archived:
                template = submission.template
                if template and template.retention_days:
                    retention_cutoff = submission.archived_at + timedelta(days=template.retention_days)

                    if datetime.utcnow() > retention_cutoff:
                        logger.info(f"Deleting submission {submission.id} past retention period")
                        # In production, might want to export/anonymize rather than delete
                        await db.delete(submission)

            await db.commit()

        except Exception as e:
            logger.error(f"Error in retention policy check: {e}")


def start_scheduler():
    """Start the background scheduler."""
    logger.info("Starting Forms scheduler")

    # Escalation check every 15 minutes
    scheduler.add_job(
        check_workflow_escalations,
        IntervalTrigger(minutes=settings.ESCALATION_CHECK_INTERVAL_MINUTES if hasattr(settings, 'ESCALATION_CHECK_INTERVAL_MINUTES') else 15),
        id="escalation_check",
        replace_existing=True
    )

    # Signature expiration check every hour
    scheduler.add_job(
        check_signature_expiration,
        IntervalTrigger(hours=1),
        id="signature_expiration_check",
        replace_existing=True
    )

    # Daily digest at 7 AM
    scheduler.add_job(
        send_daily_digests,
        CronTrigger(hour=settings.DIGEST_HOUR if hasattr(settings, 'DIGEST_HOUR') else 7, minute=0),
        id="daily_digest",
        replace_existing=True
    )

    # Draft cleanup at 2 AM daily
    scheduler.add_job(
        cleanup_old_drafts,
        CronTrigger(hour=2, minute=0),
        id="draft_cleanup",
        replace_existing=True
    )

    # Retention policy check at 3 AM daily
    scheduler.add_job(
        apply_retention_policies,
        CronTrigger(hour=settings.RETENTION_CHECK_HOUR if hasattr(settings, 'RETENTION_CHECK_HOUR') else 3, minute=0),
        id="retention_check",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Forms scheduler started with jobs: " + ", ".join([job.id for job in scheduler.get_jobs()]))


def stop_scheduler():
    """Stop the background scheduler."""
    logger.info("Stopping Forms scheduler")
    scheduler.shutdown(wait=False)
