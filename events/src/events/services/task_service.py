"""Task service"""
from datetime import timedelta
from sqlalchemy.orm import Session
from events.models import Task, TaskChecklistItem, TaskStatus
from uuid import UUID


class TaskService:
    """Service for task management"""

    def generate_tasks_from_template(self, db: Session, event, template):
        """
        Generate tasks from event template

        Args:
            db: Database session
            event: Event object
            template: EventTemplate object with default_tasks_json

        Returns:
            List of created Task objects
        """
        if not template or not template.default_tasks_json:
            return []

        tasks_config = template.default_tasks_json.get('tasks', [])
        created_tasks = []

        for task_config in tasks_config:
            # Calculate due date from offset
            due_at = None
            if task_config.get('due_offset_days') is not None:
                offset = task_config['due_offset_days']
                due_at = event.start_at + timedelta(days=offset)

            task = Task(
                event_id=event.id,
                title=task_config['title'],
                description=task_config.get('description'),
                department=task_config.get('department'),
                status=TaskStatus.TODO,
                priority=task_config.get('priority', 'med'),
                due_at=due_at,
            )
            db.add(task)
            db.flush()  # Get task ID

            # Create checklist items
            for idx, item_label in enumerate(task_config.get('checklist', [])):
                checklist_item = TaskChecklistItem(
                    task_id=task.id,
                    label=item_label,
                    is_done=False,
                    order_index=idx
                )
                db.add(checklist_item)

            created_tasks.append(task)

        db.commit()
        return created_tasks

    def update_task_due_dates_on_event_change(self, db: Session, event, old_start_at):
        """
        Update task due dates when event time changes

        Args:
            db: Database session
            event: Event object with new start time
            old_start_at: Previous start time
        """
        if event.start_at == old_start_at:
            return

        time_diff = event.start_at - old_start_at

        tasks = db.query(Task).filter(
            Task.event_id == event.id,
            Task.status != TaskStatus.DONE,
            Task.due_at.isnot(None)
        ).all()

        for task in tasks:
            task.due_at = task.due_at + time_diff

        db.commit()

    def toggle_checklist_item(self, db: Session, item_id: UUID, done: bool, user_id: UUID = None):
        """
        Toggle checklist item done status

        Args:
            db: Database session
            item_id: Checklist item ID
            done: New done status
            user_id: User making the change
        """
        from datetime import datetime

        item = db.query(TaskChecklistItem).filter(TaskChecklistItem.id == item_id).first()
        if not item:
            return None

        item.is_done = done
        if done:
            item.done_at = datetime.utcnow()
            item.done_by = user_id
        else:
            item.done_at = None
            item.done_by = None

        db.commit()
        return item
