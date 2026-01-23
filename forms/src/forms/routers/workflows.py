"""Workflows API Router"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from forms.database import get_db
from forms.auth import get_current_user, require_admin
from forms.models import (
    Workflow, WorkflowInstance, WorkflowStepHistory, FormSubmission,
    AuditLog, WorkflowStatus, AuditAction
)
from forms.schemas import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse,
    WorkflowInstanceResponse, WorkflowAdvanceRequest, WorkflowStepHistoryResponse
)

router = APIRouter()


# ==================== Workflow Definitions ====================

@router.get("/", response_model=List[WorkflowResponse])
async def list_workflows(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all workflow definitions."""
    query = select(Workflow)

    if active_only:
        query = query.where(Workflow.is_active == True)

    query = query.order_by(Workflow.name)

    result = await db.execute(query)
    workflows = result.scalars().all()

    return workflows


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get a workflow definition."""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return workflow


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(
    workflow_data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Create a new workflow definition (admin only)."""
    workflow = Workflow(
        name=workflow_data.name,
        description=workflow_data.description,
        steps=[step.model_dump() for step in workflow_data.steps],
        is_active=workflow_data.is_active,
        created_by=user.get("id"),
        updated_by=user.get("id")
    )

    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    workflow_data: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Update a workflow definition (admin only)."""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    update_data = workflow_data.model_dump(exclude_unset=True)

    if "steps" in update_data:
        update_data["steps"] = [step.model_dump() if hasattr(step, 'model_dump') else step for step in update_data["steps"]]

    for key, value in update_data.items():
        setattr(workflow, key, value)

    workflow.updated_by = user.get("id")

    await db.commit()
    await db.refresh(workflow)

    return workflow


# ==================== Workflow Instances ====================

@router.get("/instance/{submission_id}", response_model=WorkflowInstanceResponse)
async def get_workflow_instance(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get workflow instance for a submission."""
    result = await db.execute(
        select(WorkflowInstance)
        .options(selectinload(WorkflowInstance.step_history))
        .where(WorkflowInstance.submission_id == submission_id)
    )
    instance = result.scalar_one_or_none()

    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    return instance


@router.get("/instance/{submission_id}/history", response_model=List[WorkflowStepHistoryResponse])
async def get_workflow_history(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get workflow step history for a submission."""
    # Get instance first
    instance_result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.submission_id == submission_id)
    )
    instance = instance_result.scalar_one_or_none()

    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    result = await db.execute(
        select(WorkflowStepHistory)
        .where(WorkflowStepHistory.workflow_instance_id == instance.id)
        .order_by(WorkflowStepHistory.step_number)
    )
    history = result.scalars().all()

    return history


@router.post("/instance/{submission_id}/advance", response_model=WorkflowInstanceResponse)
async def advance_workflow(
    submission_id: UUID,
    request_data: WorkflowAdvanceRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Advance workflow to next step or complete."""
    # Get instance with workflow
    result = await db.execute(
        select(WorkflowInstance)
        .options(
            selectinload(WorkflowInstance.workflow),
            selectinload(WorkflowInstance.step_history)
        )
        .where(WorkflowInstance.submission_id == submission_id)
    )
    instance = result.scalar_one_or_none()

    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    if instance.status != WorkflowStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Workflow is not in progress")

    # Get current step from workflow definition
    steps = instance.workflow.steps
    current_step_idx = instance.current_step

    if current_step_idx >= len(steps):
        raise HTTPException(status_code=400, detail="No more steps in workflow")

    current_step = steps[current_step_idx]

    # Complete current step history entry
    current_history = await db.execute(
        select(WorkflowStepHistory)
        .where(
            WorkflowStepHistory.workflow_instance_id == instance.id,
            WorkflowStepHistory.step_number == current_step_idx,
            WorkflowStepHistory.completed_at == None
        )
    )
    history_entry = current_history.scalar_one_or_none()

    if history_entry:
        history_entry.action_taken = request_data.action
        history_entry.comments = request_data.comments
        history_entry.completed_at = datetime.utcnow()

    # Log workflow advancement
    sub_result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = sub_result.scalar_one_or_none()

    audit = AuditLog(
        submission_id=submission_id,
        template_id=submission.template_id if submission else None,
        employee_id=user.get("id"),
        action=AuditAction.WORKFLOW_ADVANCED,
        details={
            "from_step": current_step_idx,
            "action": request_data.action,
            "comments": request_data.comments
        }
    )
    db.add(audit)

    # Move to next step or complete
    next_step_idx = current_step_idx + 1

    if next_step_idx >= len(steps):
        # Workflow complete
        instance.status = WorkflowStatus.COMPLETED
        instance.completed_at = datetime.utcnow()

        # Update submission status
        if submission:
            from forms.models import SubmissionStatus
            submission.status = SubmissionStatus.APPROVED
    else:
        # Create next step history entry
        next_step = steps[next_step_idx]
        next_history = WorkflowStepHistory(
            workflow_instance_id=instance.id,
            step_number=next_step_idx,
            assigned_to_employee_id=next_step.get("assignee_employee_id", user.get("id"))
        )
        db.add(next_history)
        instance.current_step = next_step_idx

    await db.commit()
    await db.refresh(instance)

    return instance


@router.post("/instance/{submission_id}/cancel")
async def cancel_workflow(
    submission_id: UUID,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Cancel a workflow (admin only)."""
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.submission_id == submission_id)
    )
    instance = result.scalar_one_or_none()

    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    instance.status = WorkflowStatus.CANCELLED
    instance.completed_at = datetime.utcnow()

    # Log cancellation
    sub_result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = sub_result.scalar_one_or_none()

    audit = AuditLog(
        submission_id=submission_id,
        template_id=submission.template_id if submission else None,
        employee_id=user.get("id"),
        action=AuditAction.STATUS_CHANGED,
        details={"new_status": "cancelled", "reason": reason}
    )
    db.add(audit)

    await db.commit()

    return {"message": "Workflow cancelled"}


@router.get("/my-tasks", response_model=List[dict])
async def get_my_workflow_tasks(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get workflow tasks assigned to current user."""
    # Find step history entries assigned to this user that aren't completed
    result = await db.execute(
        select(WorkflowStepHistory)
        .options(selectinload(WorkflowStepHistory.workflow_instance))
        .where(
            WorkflowStepHistory.assigned_to_employee_id == user.get("id"),
            WorkflowStepHistory.completed_at == None
        )
        .order_by(WorkflowStepHistory.started_at)
    )
    tasks = result.scalars().all()

    response = []
    for task in tasks:
        instance = task.workflow_instance
        if instance and instance.status == WorkflowStatus.IN_PROGRESS:
            response.append({
                "submission_id": str(instance.submission_id),
                "workflow_id": str(instance.workflow_id),
                "step_number": task.step_number,
                "started_at": task.started_at.isoformat() if task.started_at else None
            })

    return response
