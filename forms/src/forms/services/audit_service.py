"""Audit Service for Forms"""
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from forms.models import AuditLog, AuditAction

logger = logging.getLogger(__name__)


class AuditService:
    """Service for logging audit trail events."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: AuditAction,
        employee_id: int = None,
        submission_id: UUID = None,
        template_id: UUID = None,
        details: Dict[str, Any] = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> AuditLog:
        """
        Log an audit event.

        Args:
            action: The action being logged
            employee_id: ID of the employee performing the action
            submission_id: Related submission ID (optional)
            template_id: Related template ID (optional)
            details: Additional details about the action
            ip_address: Client IP address
            user_agent: Client user agent string

        Returns:
            Created AuditLog entry
        """
        log_entry = AuditLog(
            action=action,
            employee_id=employee_id,
            submission_id=submission_id,
            template_id=template_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )

        self.db.add(log_entry)
        await self.db.commit()
        await self.db.refresh(log_entry)

        logger.debug(f"Audit log: {action.value} by employee {employee_id}")

        return log_entry

    async def log_view(
        self,
        submission_id: UUID,
        employee_id: int,
        ip_address: str = None,
        user_agent: str = None
    ) -> AuditLog:
        """Log a form view event."""
        return await self.log(
            action=AuditAction.VIEWED,
            submission_id=submission_id,
            employee_id=employee_id,
            ip_address=ip_address,
            user_agent=user_agent
        )

    async def log_create(
        self,
        submission_id: UUID,
        template_id: UUID,
        employee_id: int,
        details: Dict[str, Any] = None,
        ip_address: str = None
    ) -> AuditLog:
        """Log a form creation event."""
        return await self.log(
            action=AuditAction.CREATED,
            submission_id=submission_id,
            template_id=template_id,
            employee_id=employee_id,
            details=details,
            ip_address=ip_address
        )

    async def log_edit(
        self,
        submission_id: UUID,
        employee_id: int,
        changes: Dict[str, Any] = None,
        ip_address: str = None
    ) -> AuditLog:
        """Log a form edit event."""
        return await self.log(
            action=AuditAction.EDITED,
            submission_id=submission_id,
            employee_id=employee_id,
            details={"changes": changes} if changes else None,
            ip_address=ip_address
        )

    async def log_signature(
        self,
        submission_id: UUID,
        employee_id: int,
        signature_type: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> AuditLog:
        """Log a signature event."""
        return await self.log(
            action=AuditAction.SIGNED,
            submission_id=submission_id,
            employee_id=employee_id,
            details={"signature_type": signature_type},
            ip_address=ip_address,
            user_agent=user_agent
        )

    async def log_status_change(
        self,
        submission_id: UUID,
        employee_id: int,
        old_status: str,
        new_status: str,
        reason: str = None
    ) -> AuditLog:
        """Log a status change event."""
        return await self.log(
            action=AuditAction.STATUS_CHANGED,
            submission_id=submission_id,
            employee_id=employee_id,
            details={
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason
            }
        )

    async def log_export(
        self,
        submission_id: UUID,
        employee_id: int,
        format: str,
        ip_address: str = None
    ) -> AuditLog:
        """Log an export event."""
        return await self.log(
            action=AuditAction.EXPORTED,
            submission_id=submission_id,
            employee_id=employee_id,
            details={"format": format},
            ip_address=ip_address
        )

    async def log_print(
        self,
        submission_id: UUID,
        employee_id: int,
        ip_address: str = None
    ) -> AuditLog:
        """Log a print event."""
        return await self.log(
            action=AuditAction.PRINTED,
            submission_id=submission_id,
            employee_id=employee_id,
            ip_address=ip_address
        )

    async def log_archive(
        self,
        submission_id: UUID,
        employee_id: int,
        reason: str = None
    ) -> AuditLog:
        """Log an archive event."""
        return await self.log(
            action=AuditAction.ARCHIVED,
            submission_id=submission_id,
            employee_id=employee_id,
            details={"reason": reason} if reason else None
        )
