"""Workflow Engine Service"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from forms.models import (
    Workflow, WorkflowInstance, WorkflowStepHistory, FormSubmission,
    WorkflowStatus, SubmissionStatus
)

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Service for managing form workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_workflow(
        self,
        submission_id: UUID,
        workflow_id: UUID,
        initial_data: Dict[str, Any] = None
    ) -> WorkflowInstance:
        """
        Start a workflow for a submission.

        Args:
            submission_id: Form submission ID
            workflow_id: Workflow definition ID
            initial_data: Initial data for condition evaluation

        Returns:
            Created WorkflowInstance
        """
        # Get workflow definition
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if not workflow.is_active:
            raise ValueError(f"Workflow {workflow_id} is not active")

        # Check if workflow instance already exists
        existing = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.submission_id == submission_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Workflow already exists for submission {submission_id}")

        # Create workflow instance
        instance = WorkflowInstance(
            workflow_id=workflow_id,
            submission_id=submission_id,
            current_step=0,
            status=WorkflowStatus.IN_PROGRESS
        )
        self.db.add(instance)
        await self.db.flush()

        # Determine first step assignee
        steps = workflow.steps
        if steps and len(steps) > 0:
            first_step = steps[0]
            assignee_id = await self._resolve_assignee(
                submission_id,
                first_step,
                initial_data
            )

            # Create first step history
            step_history = WorkflowStepHistory(
                workflow_instance_id=instance.id,
                step_number=0,
                assigned_to_employee_id=assignee_id
            )
            self.db.add(step_history)

        await self.db.commit()
        await self.db.refresh(instance)

        logger.info(f"Started workflow {workflow_id} for submission {submission_id}")

        return instance

    async def advance_step(
        self,
        submission_id: UUID,
        action: str,
        comments: str = None,
        performed_by: int = None
    ) -> WorkflowInstance:
        """
        Advance workflow to next step.

        Args:
            submission_id: Form submission ID
            action: Action taken (approve, reject, etc.)
            comments: Optional comments
            performed_by: Employee ID who performed the action

        Returns:
            Updated WorkflowInstance
        """
        # Get instance with workflow
        result = await self.db.execute(
            select(WorkflowInstance)
            .options(selectinload(WorkflowInstance.workflow))
            .where(WorkflowInstance.submission_id == submission_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            raise ValueError(f"No workflow found for submission {submission_id}")

        if instance.status != WorkflowStatus.IN_PROGRESS:
            raise ValueError("Workflow is not in progress")

        # Complete current step
        current_history = await self.db.execute(
            select(WorkflowStepHistory)
            .where(
                WorkflowStepHistory.workflow_instance_id == instance.id,
                WorkflowStepHistory.step_number == instance.current_step,
                WorkflowStepHistory.completed_at == None
            )
        )
        history_entry = current_history.scalar_one_or_none()

        if history_entry:
            history_entry.action_taken = action
            history_entry.comments = comments
            history_entry.completed_at = datetime.utcnow()

        # Check if action is rejection
        if action.lower() in ['reject', 'rejected', 'deny', 'denied']:
            instance.status = WorkflowStatus.CANCELLED
            instance.completed_at = datetime.utcnow()

            # Update submission status
            sub_result = await self.db.execute(
                select(FormSubmission).where(FormSubmission.id == submission_id)
            )
            submission = sub_result.scalar_one_or_none()
            if submission:
                submission.status = SubmissionStatus.REJECTED

            await self.db.commit()
            return instance

        # Move to next step
        steps = instance.workflow.steps
        next_step_idx = instance.current_step + 1

        if next_step_idx >= len(steps):
            # Workflow complete
            instance.status = WorkflowStatus.COMPLETED
            instance.completed_at = datetime.utcnow()

            # Update submission status
            sub_result = await self.db.execute(
                select(FormSubmission).where(FormSubmission.id == submission_id)
            )
            submission = sub_result.scalar_one_or_none()
            if submission:
                submission.status = SubmissionStatus.APPROVED

            logger.info(f"Workflow completed for submission {submission_id}")
        else:
            # Create next step
            next_step = steps[next_step_idx]
            assignee_id = await self._resolve_assignee(
                submission_id,
                next_step,
                None
            )

            next_history = WorkflowStepHistory(
                workflow_instance_id=instance.id,
                step_number=next_step_idx,
                assigned_to_employee_id=assignee_id
            )
            self.db.add(next_history)
            instance.current_step = next_step_idx

            logger.info(f"Workflow advanced to step {next_step_idx} for submission {submission_id}")

        await self.db.commit()
        await self.db.refresh(instance)

        return instance

    async def _resolve_assignee(
        self,
        submission_id: UUID,
        step: Dict[str, Any],
        data: Dict[str, Any] = None
    ) -> int:
        """
        Resolve the assignee for a workflow step.

        Args:
            submission_id: Form submission ID
            step: Step configuration from workflow definition
            data: Submission data for condition evaluation

        Returns:
            Employee ID of the assignee
        """
        assignee_type = step.get("assignee_type")
        assignee_id = step.get("assignee_employee_id")

        if assignee_id:
            return assignee_id

        # Get submission for context
        sub_result = await self.db.execute(
            select(FormSubmission).where(FormSubmission.id == submission_id)
        )
        submission = sub_result.scalar_one_or_none()

        if not submission:
            raise ValueError(f"Submission {submission_id} not found")

        if assignee_type == "submitter":
            return submission.submitted_by_employee_id

        if assignee_type == "submitter_manager":
            # TODO: Look up manager from HR service
            # For now, return submitter
            return submission.submitted_by_employee_id

        if assignee_type == "location_gm":
            # TODO: Look up GM from HR service based on location_id
            return submission.submitted_by_employee_id

        if assignee_type == "hr":
            # TODO: Look up HR employee from HR service
            return submission.submitted_by_employee_id

        # Default to submitter
        return submission.submitted_by_employee_id

    async def get_pending_tasks(self, employee_id: int) -> List[Dict[str, Any]]:
        """
        Get pending workflow tasks for an employee.

        Args:
            employee_id: Employee ID

        Returns:
            List of pending tasks
        """
        result = await self.db.execute(
            select(WorkflowStepHistory)
            .options(
                selectinload(WorkflowStepHistory.workflow_instance)
                .selectinload(WorkflowInstance.workflow)
            )
            .where(
                WorkflowStepHistory.assigned_to_employee_id == employee_id,
                WorkflowStepHistory.completed_at == None
            )
            .order_by(WorkflowStepHistory.started_at)
        )

        tasks = []
        for history in result.scalars().all():
            if history.workflow_instance.status == WorkflowStatus.IN_PROGRESS:
                workflow = history.workflow_instance.workflow
                steps = workflow.steps if workflow else []
                current_step = steps[history.step_number] if history.step_number < len(steps) else {}

                tasks.append({
                    "submission_id": str(history.workflow_instance.submission_id),
                    "workflow_name": workflow.name if workflow else "Unknown",
                    "step_name": current_step.get("name", f"Step {history.step_number + 1}"),
                    "action_required": current_step.get("action_required", "review"),
                    "started_at": history.started_at.isoformat() if history.started_at else None
                })

        return tasks
