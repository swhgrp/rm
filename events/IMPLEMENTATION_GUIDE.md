# Event Planning System - Implementation Guide

## Current Status

✅ **Complete (40% of project)**:
- Full database schema (10+ models)
- Alembic migrations framework
- Core configuration & Docker setup
- Example implementations:
  - Event API endpoint with CRUD operations
  - Auth service with RBAC logic
  - Email service with templating
  - Pydantic schemas for events

🔄 **Remaining (60% to complete)**:
This guide provides exact steps to complete the implementation.

---

## Phase 1: Complete Core Services (Week 1)

### 1.1 HR Sync Service
Create `src/events/services/hr_sync_service.py`:

```python
import httpx
from sqlalchemy.orm import Session
from events.core.config import settings
from events.models import User, Role
import logging

logger = logging.getLogger(__name__)

class HRSyncService:
    async def sync_users(self, db: Session):
        """Sync users from HR system"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.HR_API_URL}/users",
                headers={"Authorization": f"Bearer {settings.HR_API_KEY}"}
            )
            hr_users = response.json()

        for hr_user in hr_users:
            user = db.query(User).filter(User.email == hr_user['email']).first()

            if not user:
                # Create new user
                user = User(
                    email=hr_user['email'],
                    full_name=hr_user['full_name'],
                    department=hr_user['department'],
                    is_active=hr_user['is_active'],
                    source='hr'
                )
                db.add(user)
                logger.info(f"Created user {user.email} from HR")
            else:
                # Update existing
                user.full_name = hr_user['full_name']
                user.department = hr_user['department']
                user.is_active = hr_user['is_active']
                logger.info(f"Updated user {user.email} from HR")

            # Assign default role based on department
            self._assign_default_role(db, user, hr_user)

        db.commit()

    def _assign_default_role(self, db: Session, user: User, hr_user: dict):
        """Assign default role based on department"""
        # Skip if user has local role overrides
        if user.source == 'local':
            return

        # Map department to role
        department_role_map = {
            'Sales': 'event_manager',
            'Kitchen': 'staff',
            'Bar': 'staff',
            'AV': 'staff',
            'Floor': 'staff',
            'Accounting': 'read_only',
        }

        role_code = department_role_map.get(hr_user['department'], 'staff')

        # Check for department lead flag
        if hr_user.get('is_dept_lead'):
            role_code = 'dept_lead'

        role = db.query(Role).filter(Role.code == role_code).first()
        if role and role not in user.roles:
            user.roles.append(role)
```

**Background Job** - Create `src/events/jobs/hr_sync.py`:
```python
from celery import Celery
from events.core.database import SessionLocal
from events.services.hr_sync_service import HRSyncService

app = Celery('events', broker=settings.REDIS_URL)

@app.task
def sync_hr_users_task():
    db = SessionLocal()
    try:
        sync_service = HRSyncService()
        sync_service.sync_users(db)
    finally:
        db.close()

# Schedule: Run daily at 2 AM
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        sync_hr_users_task.s(),
    )
```

### 1.2 PDF Generation Service
Create `src/events/services/pdf_service.py`:

```python
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader
import boto3
from events.core.config import settings
from events.models import Document, DocumentType
from uuid import uuid4

class PDFService:
    def __init__(self):
        self.jinja_env = Environment(
            loader=FileSystemLoader("src/events/templates/documents")
        )
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
        )

    async def generate_beo(self, event, db):
        """Generate BEO PDF"""
        template = self.jinja_env.get_template("beo_template.html")
        html_content = template.render(
            event=event,
            client=event.client,
            venue=event.venue,
            menu=event.menu_json,
            requirements=event.requirements_json,
        )

        # Convert HTML to PDF
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Upload to S3
        filename = f"beo/{event.id}/{uuid4()}.pdf"
        self.s3_client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=filename,
            Body=pdf_bytes,
            ContentType='application/pdf'
        )

        storage_url = f"{settings.S3_ENDPOINT}/{settings.S3_BUCKET}/{filename}"

        # Create document record
        doc = Document(
            event_id=event.id,
            doc_type=DocumentType.BEO,
            version=self._get_next_version(db, event.id, DocumentType.BEO),
            storage_url=storage_url,
            render_params_json={'generated_at': str(event.updated_at)}
        )
        db.add(doc)
        db.commit()

        return doc

    def _get_next_version(self, db, event_id, doc_type):
        """Get next version number for document"""
        max_version = db.query(func.max(Document.version)).filter(
            Document.event_id == event_id,
            Document.doc_type == doc_type
        ).scalar()
        return (max_version or 0) + 1
```

### 1.3 Task Service
Create `src/events/services/task_service.py`:

```python
from datetime import timedelta
from events.models import Task, TaskChecklistItem, TaskStatus
from sqlalchemy.orm import Session

class TaskService:
    def generate_tasks_from_template(self, db: Session, event, template):
        """Generate tasks from event template"""
        if not template or not template.default_tasks_json:
            return []

        tasks_config = template.default_tasks_json.get('tasks', [])
        created_tasks = []

        for task_config in tasks_config:
            # Calculate due date from offset
            due_at = None
            if task_config.get('due_offset_days'):
                offset = task_config['due_offset_days']
                due_at = event.start_at + timedelta(days=offset)

            task = Task(
                event_id=event.id,
                title=task_config['title'],
                department=task_config.get('department'),
                status=TaskStatus.TODO,
                priority=task_config.get('priority', 'med'),
                due_at=due_at,
            )
            db.add(task)
            db.flush()  # Get task ID

            # Create checklist items
            for item_label in task_config.get('checklist', []):
                checklist_item = TaskChecklistItem(
                    task_id=task.id,
                    label=item_label,
                    is_done=False
                )
                db.add(checklist_item)

            created_tasks.append(task)

        db.commit()
        return created_tasks

    def update_task_due_dates_on_event_change(self, db: Session, event, old_start_at):
        """Update task due dates when event time changes"""
        if event.start_at == old_start_at:
            return

        time_diff = event.start_at - old_start_at

        tasks = db.query(Task).filter(
            Task.event_id == event.id,
            Task.status != TaskStatus.DONE
        ).all()

        for task in tasks:
            if task.due_at:
                task.due_at = task.due_at + time_diff

        db.commit()
```

---

## Phase 2: Complete API Endpoints (Week 2)

### 2.1 Public Intake Endpoint
Create `src/events/api/public.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx
from events.core.database import get_db
from events.core.config import settings
from events.models import Client, Event, EventTemplate
from events.services.task_service import TaskService
from events.services.email_service import EmailService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class PublicIntakeRequest(BaseModel):
    hcaptcha_token: str
    eventTemplateKey: str
    client: dict  # {name, email, phone, org}
    event: dict   # {title, date, start_at, end_at, guest_count, ...}

@router.post("/beo-intake")
async def public_beo_intake(
    data: PublicIntakeRequest,
    db: Session = Depends(get_db)
):
    """Public BEO intake form submission"""

    # Verify hCaptcha
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://hcaptcha.com/siteverify",
            data={
                'secret': settings.HCAPTCHA_SECRET,
                'response': data.hcaptcha_token
            }
        )
        captcha_result = response.json()

        if not captcha_result.get('success'):
            raise HTTPException(status_code=400, detail="Invalid captcha")

    # Find or create client
    client_data = data.client
    client = db.query(Client).filter(Client.email == client_data['email']).first()

    if not client:
        client = Client(**client_data)
        db.add(client)
        db.commit()
        db.refresh(client)

    # Get event template
    template = db.query(EventTemplate).filter(
        EventTemplate.name == data.eventTemplateKey
    ).first()

    # Create event
    event_data = data.event
    event = Event(
        **event_data,
        client_id=client.id,
        status=EventStatus.PENDING
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Generate tasks from template
    task_service = TaskService()
    task_service.generate_tasks_from_template(db, event, template)

    # Send confirmation email
    email_service = EmailService()
    await email_service.send_notification_by_rule(
        db, event, trigger='on_created', template=template
    )

    return {
        "success": True,
        "event_id": str(event.id),
        "message": "Your event request has been submitted!"
    }
```

### 2.2 Task API
Create `src/events/api/tasks.py` - Follow pattern from `events.py` example.

```python
@router.get("/events/{event_id}/tasks")
async def list_tasks_for_event(event_id: UUID, db: Session = Depends(get_db)):
    """List all tasks for an event"""

@router.post("/events/{event_id}/tasks")
async def create_task(event_id: UUID, task_data: TaskCreate, db: Session = Depends(get_db)):
    """Create new task for event"""

@router.patch("/tasks/{task_id}")
async def update_task(task_id: UUID, task_data: TaskUpdate, db: Session = Depends(get_db)):
    """Update task"""

@router.post("/tasks/{task_id}/checklist")
async def add_checklist_item(task_id: UUID, label: str, db: Session = Depends(get_db)):
    """Add checklist item to task"""

@router.patch("/checklist/{item_id}/toggle")
async def toggle_checklist_item(item_id: UUID, done: bool, db: Session = Depends(get_db)):
    """Toggle checklist item done status"""
```

### 2.3 Document API
Create `src/events/api/documents.py`:

```python
@router.post("/events/{event_id}/documents:render")
async def render_document(
    event_id: UUID,
    doc_type: DocumentType,
    db: Session = Depends(get_db)
):
    """Render and store document"""
    event = db.query(Event).filter(Event.id == event_id).first()
    pdf_service = PDFService()

    if doc_type == DocumentType.BEO:
        doc = await pdf_service.generate_beo(event, db)
    # ... add other doc types

    return {"document_id": str(doc.id), "url": doc.storage_url}

@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: UUID, db: Session = Depends(get_db)):
    """Get signed URL for document download"""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    # Generate signed URL (temporary access)
    return {"url": doc.storage_url + "?signature=..."}
```

---

## Phase 3: Admin UI (Week 3)

### 3.1 Calendar View
Create `src/events/templates/admin/calendar.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.9/main.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.9/main.min.js"></script>
</head>
<body>
    <div id="calendar"></div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var calendar = new FullCalendar.Calendar(document.getElementById('calendar'), {
                initialView: 'dayGridMonth',
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,timeGridDay'
                },
                events: async function(info, successCallback) {
                    const response = await fetch(`/api/events/calendar?start=${info.startStr}&end=${info.endStr}`);
                    const events = await response.json();
                    successCallback(events.map(e => ({
                        id: e.id,
                        title: e.title,
                        start: e.start_at,
                        end: e.end_at,
                        color: getColorByStatus(e.status)
                    })));
                },
                eventClick: function(info) {
                    showEventDetail(info.event.id);
                }
            });
            calendar.render();
        });

        function getColorByStatus(status) {
            const colors = {
                'draft': '#6c757d',
                'pending': '#ffc107',
                'confirmed': '#28a745',
                'closed': '#17a2b8',
                'canceled': '#dc3545'
            };
            return colors[status] || '#007bff';
        }

        function showEventDetail(eventId) {
            // Open drawer/modal with event details
            fetch(`/api/events/${eventId}`)
                .then(r => r.json())
                .then(event => {
                    document.getElementById('event-drawer').innerHTML = renderEventDetails(event);
                    // Show drawer
                });
        }
    </script>
</body>
</html>
```

### 3.2 Event Form
Create `src/events/templates/admin/event_form.html` - Standard HTML form with:
- Client selection/creation
- Venue dropdown
- Date/time pickers
- Guest count
- Menu builder (JSON textarea for now, can enhance later)
- Requirements textarea
- Package selection

### 3.3 Task Board
Create `src/events/templates/admin/tasks.html` - Kanban board with columns for:
- Todo
- In Progress
- Blocked
- Done

Use drag-and-drop (e.g., SortableJS) to move tasks between columns.

---

## Phase 4: Email Templates (Week 4)

Create in `src/events/templates/emails/`:

### client_confirmation.html
```html
<!DOCTYPE html>
<html>
<body>
    <h1>Event Confirmation</h1>
    <p>Dear {{ client.name }},</p>
    <p>Thank you for choosing SW Hospitality for your {{ event.event_type }}!</p>

    <h2>Event Details</h2>
    <ul>
        <li><strong>Event:</strong> {{ event.title }}</li>
        <li><strong>Date:</strong> {{ event.start_at|date }}</li>
        <li><strong>Time:</strong> {{ event.start_at|time }} - {{ event.end_at|time }}</li>
        <li><strong>Venue:</strong> {{ venue.name }}</li>
        <li><strong>Guests:</strong> {{ event.guest_count }}</li>
    </ul>

    <p>We will be in touch soon with your Banquet Event Order (BEO).</p>

    <p>Best regards,<br>SW Hospitality Events Team</p>
</body>
</html>
```

### internal_update.html
```html
<!DOCTYPE html>
<html>
<body>
    <h1>Event Update Notification</h1>
    <p>Event <strong>{{ event.title }}</strong> has been updated.</p>

    <h2>Details</h2>
    <ul>
        <li><strong>Date:</strong> {{ event.start_at|date }}</li>
        <li><strong>Time:</strong> {{ event.start_at|time }} - {{ event.end_at|time }}</li>
        <li><strong>Venue:</strong> {{ venue.name }}</li>
        <li><strong>Guests:</strong> {{ event.guest_count }}</li>
    </ul>

    <p>Please review tasks assigned to your department.</p>
    <a href="{{ app_url }}/events/{{ event.id }}">View Event Details</a>
</body>
</html>
```

---

## Phase 5: Integration & Testing (Week 5)

### 5.1 Update main.py
```python
from events.api import public, events, tasks, documents, emails, templates, users, admin

app.include_router(public.router, prefix="/public", tags=["public"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
```

### 5.2 Add to Docker Compose
See README.md section on Docker Compose integration.

### 5.3 Write Tests
Create `tests/test_events.py`:

```python
def test_create_event(client, db):
    response = client.post("/api/events/", json={
        "title": "Test Event",
        "event_type": "Wedding",
        "start_at": "2026-01-01T16:00:00Z",
        "end_at": "2026-01-01T22:00:00Z",
        "guest_count": 100,
        "venue_id": str(venue.id),
        "client_id": str(client_record.id)
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Event"
```

Create `tests/test_public_intake.py` - Test public form submission.

Create `tests/test_rbac.py` - Test permission checks for each role.

---

## Deployment Checklist

- [ ] Set all environment variables in `.env`
- [ ] Configure S3 bucket for document storage
- [ ] Set up SMTP/SendGrid credentials
- [ ] Configure hCaptcha keys
- [ ] Set up HR API credentials
- [ ] Run database migrations: `alembic upgrade head`
- [ ] Seed initial data (roles, venues, templates)
- [ ] Configure nginx reverse proxy
- [ ] Set up SSL certificates
- [ ] Configure Celery for background jobs
- [ ] Set up monitoring and logging

---

## Estimated Effort

- **Phase 1 (Services)**: 1 week
- **Phase 2 (APIs)**: 1 week
- **Phase 3 (UI)**: 1 week
- **Phase 4 (Templates)**: 3 days
- **Phase 5 (Integration/Testing)**: 4 days

**Total**: ~4 weeks for experienced FastAPI developer

---

## Support Resources

- FastAPI docs: https://fastapi.tiangolo.com/
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- WeasyPrint docs: https://doc.courtbouillon.org/weasyprint/
- FullCalendar docs: https://fullcalendar.io/docs
- Celery docs: https://docs.celeryq.dev/

## Questions?

Refer to example implementations in:
- `src/events/api/events.py` - Complete CRUD API
- `src/events/services/auth_service.py` - RBAC logic
- `src/events/services/email_service.py` - Email templating
