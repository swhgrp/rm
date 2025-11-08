"""Task API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from events.core.database import get_db
from events.core.deps import require_auth, require_permission, check_permission
from events.models import Task, TaskChecklistItem, TaskStatus, User
from events.schemas.task import TaskCreate, TaskUpdate, TaskResponse, ChecklistItemCreate, ChecklistItemResponse
from events.services.task_service import TaskService

router = APIRouter()
task_service = TaskService()


@router.get("/all", response_model=List[TaskResponse])
async def list_all_tasks(
    status: Optional[TaskStatus] = None,
    department: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read", "task"))
):
    """
    List all tasks across all events

    - **status**: Filter by task status (optional)
    - **department**: Filter by department (optional)
    - **priority**: Filter by priority (optional)
    """
    from events.models import Event
    from sqlalchemy.orm import joinedload

    query = db.query(Task).options(
        joinedload(Task.event),
        joinedload(Task.assignee),
        joinedload(Task.checklist_items)
    )

    if status:
        query = query.filter(Task.status == status)
    if department:
        query = query.filter(Task.department == department)
    if priority:
        query = query.filter(Task.priority == priority)

    tasks = query.order_by(Task.due_at.asc().nullslast(), Task.priority.desc()).all()

    # Enrich with event and assigned user info
    result = []
    for task in tasks:
        task_dict = {
            "id": task.id,
            "event_id": task.event_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "department": task.department,
            "assigned_to_id": task.assignee_user_id,
            "due_at": task.due_at,
            "completed_at": task.completed_at,
            "created_at": task.created_at,
            "event_title": task.event.title if task.event else None,
            "assigned_to_name": task.assignee.full_name if task.assignee else None,
            "checklist_items": [
                {
                    "id": item.id,
                    "label": item.label,
                    "is_done": item.is_done,
                    "position": item.position
                }
                for item in task.checklist_items
            ] if task.checklist_items else []
        }
        result.append(task_dict)

    return result


@router.get("/events/{event_id}/tasks", response_model=List[TaskResponse])
async def list_tasks_for_event(
    event_id: UUID,
    status: Optional[TaskStatus] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all tasks for an event

    - **event_id**: Event UUID
    - **status**: Filter by task status (optional)
    - **department**: Filter by department (optional)
    """
    query = db.query(Task).filter(Task.event_id == event_id)

    if status:
        query = query.filter(Task.status == status)
    if department:
        query = query.filter(Task.department == department)

    tasks = query.order_by(Task.due_at.asc().nullslast(), Task.priority.desc()).all()
    return tasks


@router.get("/tasks/my-tasks", response_model=List[TaskResponse])
async def list_my_tasks(
    assignee_id: UUID = Query(..., description="User ID of assignee"),
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db)
):
    """
    List tasks assigned to a specific user

    - **assignee_id**: User UUID
    - **status**: Filter by status (optional)
    """
    query = db.query(Task).filter(Task.assignee_user_id == assignee_id)

    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.due_at.asc().nullslast()).all()
    return tasks


@router.get("/tasks/department/{department}", response_model=List[TaskResponse])
async def list_department_tasks(
    department: str,
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db)
):
    """
    List all tasks for a department (for department leads)

    - **department**: Department name (kitchen, bar, av, floor, sales, admin)
    - **status**: Filter by status (optional)
    """
    query = db.query(Task).filter(Task.department == department)

    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(Task.due_at.asc().nullslast()).all()
    return tasks


@router.post("/events/{event_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    event_id: UUID,
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """
    Create new task for event

    - Optionally includes checklist items
    """
    # Permission check: event_manager and admin can create tasks
    if not check_permission(current_user, "create", "task"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create tasks"
        )

    # Verify event_id matches
    if task_data.event_id != event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event ID mismatch"
        )

    # Create task
    task = Task(
        event_id=task_data.event_id,
        title=task_data.title,
        description=task_data.description,
        department=task_data.department,
        priority=task_data.priority,
        assignee_user_id=task_data.assignee_user_id,
        due_at=task_data.due_at,
        status=TaskStatus.TODO
    )

    db.add(task)
    db.flush()  # Get task ID

    # Create checklist items
    if task_data.checklist:
        for idx, label in enumerate(task_data.checklist):
            item = TaskChecklistItem(
                task_id=task.id,
                label=label,
                order_index=idx
            )
            db.add(item)

    db.commit()
    db.refresh(task)

    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: Session = Depends(get_db)
):
    """Get single task by ID"""
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    return task


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("update", "task"))
):
    """
    Update task

    - Can update status, assignee, due date, etc.
    - Automatically sets completed_at when status changes to DONE
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_dict = task_data.dict(exclude_unset=True)

    # Auto-set completed_at when marking done
    if update_dict.get('status') == TaskStatus.DONE and task.status != TaskStatus.DONE:
        update_dict['completed_at'] = datetime.utcnow()

    # Clear completed_at if changing from done to another status
    if update_dict.get('status') and update_dict['status'] != TaskStatus.DONE:
        update_dict['completed_at'] = None

    for field, value in update_dict.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Delete task - admin and event_manager only"""
    # Only admin and event_manager can delete tasks
    if not check_permission(current_user, "delete", "task"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin and event managers can delete tasks"
        )

    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()

    return None


@router.post("/tasks/{task_id}/checklist", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_checklist_item(
    task_id: UUID,
    item_data: ChecklistItemCreate,
    db: Session = Depends(get_db)
):
    """Add checklist item to task"""
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    item = TaskChecklistItem(
        task_id=task_id,
        label=item_data.label,
        order_index=item_data.order_index
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


@router.patch("/checklist/{item_id}/toggle", response_model=ChecklistItemResponse)
async def toggle_checklist_item(
    item_id: UUID,
    done: bool,
    user_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    Toggle checklist item done status

    - **done**: True to mark done, False to mark undone
    - **user_id**: User making the change (optional)
    """
    item = task_service.toggle_checklist_item(db, item_id, done, user_id)

    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    return item


@router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(
    item_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete checklist item"""
    item = db.query(TaskChecklistItem).filter(TaskChecklistItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    db.delete(item)
    db.commit()

    return None
