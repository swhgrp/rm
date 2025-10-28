# Event Planning Microsystem

## Status: Foundation Complete - Implementation In Progress

A comprehensive event planning system with calendar, task management, document generation, email notifications, and role-based access control.

## What's Built

### ✅ Complete
- **Database Schema**: All 10+ models with relationships (users, roles, events, tasks, documents, emails, templates, audit logs)
- **Alembic Migrations**: Database migration framework configured
- **Docker Setup**: Dockerfile with PDF generation dependencies (WeasyPrint)
- **Core Configuration**: Settings, database, base models

### 🔄 Remaining Implementation

#### 1. Pydantic Schemas (src/events/schemas/)
- `user.py` - UserCreate, UserResponse, RoleResponse
- `event.py` - EventCreate, EventUpdate, EventResponse, EventPackageResponse
- `task.py` - TaskCreate, TaskUpdate, TaskResponse
- `document.py` - DocumentResponse, EmailCreate
- `template.py` - EventTemplateCreate, TemplateResponse
- `intake.py` - PublicIntakeRequest, PublicIntakeResponse

#### 2. Core Services (src/events/services/)
- **auth_service.py**: JWT tokens, SSO integration, RBAC checks
- **hr_sync_service.py**: Nightly HR user sync, role mapping
- **email_service.py**: SMTP/SendGrid, templating, queue management
- **pdf_service.py**: WeasyPrint HTML→PDF, S3 upload
- **notification_service.py**: Rule evaluation, email routing
- **task_service.py**: Auto-task generation from templates, due date calculation

#### 3. API Endpoints (src/events/api/)
- **public.py**: POST /public/beo-intake (hCaptcha validation)
- **events.py**: CRUD events, calendar views, status transitions
- **tasks.py**: Task CRUD, checklist management, assignment
- **documents.py**: PDF rendering, versioning, signed URLs
- **emails.py**: Send emails, list history
- **templates.py**: Template CRUD, preview
- **users.py**: User management, role assignment
- **admin.py**: HR sync trigger, notification rules

#### 4. Main FastAPI App (src/events/main.py)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from events.api import public, events, tasks, documents, emails, templates, users, admin

app = FastAPI(title="SW Hospitality Events")

# Include routers
app.include_router(public.router, prefix="/public", tags=["public"])
app.include_router(events.router, prefix="/events", tags=["events"])
# ... etc
```

#### 5. UI Templates (src/events/templates/)
- **admin/**
  - `calendar.html` - Month/week/day calendar with FullCalendar.js
  - `event_detail.html` - Event drawer with tabs (details, tasks, docs, emails)
  - `event_form.html` - Create/edit event form
  - `tasks.html` - Kanban board by department
  - `templates.html` - Template manager
  - `users.html` - User/role management
- **public/**
  - `intake_form.html` - Public BEO intake with hCaptcha
- **documents/**
  - `beo_template.html` - BEO PDF template
  - `summary_template.html` - Event summary template
- **emails/**
  - `client_confirmation.html`
  - `internal_update.html`
  - `task_assignment.html`

#### 6. Docker Compose Integration
Add to `/opt/restaurant-system/docker-compose.yml`:
```yaml
events-db:
  image: postgres:15
  environment:
    POSTGRES_USER: events_user
    POSTGRES_PASSWORD: events_password
    POSTGRES_DB: events_db
  volumes:
    - events-db-data:/var/lib/postgresql/data

events-redis:
  image: redis:7-alpine

events-app:
  build: ./events
  ports:
    - "8005:8000"
  depends_on:
    - events-db
    - events-redis
  env_file:
    - ./events/.env
  volumes:
    - ./events:/app

volumes:
  events-db-data:
```

#### 7. Nginx Routing
Add to nginx config:
```nginx
location /events/ {
    proxy_pass http://events-app:8000/;
}
```

## Quick Start (Once Implementation Complete)

### 1. Configure Environment
```bash
cd /opt/restaurant-system/events
cp .env.example .env
# Edit .env with your credentials
```

### 2. Build and Start
```bash
docker compose up events-db events-redis events-app -d
```

### 3. Run Migrations
```bash
docker compose exec events-app alembic upgrade head
```

### 4. Seed Data
```bash
docker compose exec events-app python -m events.scripts.seed_data
```

### 5. Access
- Admin UI: https://rm.swhgrp.com/events/
- Public Intake: https://rm.swhgrp.com/events/public/intake
- API Docs: https://rm.swhgrp.com/events/docs

## Database Schema

### Core Entities
- **events**: Event master records with status, timing, guest count
- **clients**: Client contact information
- **venues**: Venue/room definitions
- **event_packages**: Reusable pricing packages
- **event_templates**: Form schemas, auto-tasks, email rules

### Task Management
- **tasks**: Tasks with status, priority, department, assignee
- **task_checklist_items**: Sub-tasks with completion tracking

### Documents & Communication
- **documents**: Versioned PDFs with S3 storage
- **emails**: Email history with status tracking
- **notification_rules**: Automated email routing rules

### Security & Audit
- **users**: SSO-synced users from HR system
- **roles**: RBAC roles (admin, event_manager, dept_lead, staff, read_only)
- **user_roles**: User-role assignments
- **audit_logs**: Full audit trail with before/after diffs

## RBAC Permissions

| Role | Create Event | Edit Financials | Assign Tasks | View All | Confirm Event |
|------|-------------|----------------|--------------|----------|---------------|
| admin | ✅ | ✅ | ✅ | ✅ | ✅ |
| event_manager | ✅ | ✅ | ✅ | ✅ | ✅ |
| dept_lead | ❌ | Totals Only | Own Dept Only | ✅ | ❌ |
| staff | ❌ | ❌ | Own Tasks | Assigned Only | ❌ |
| read_only | ❌ | ❌ | ❌ | ✅ | ❌ |

## Integration Points

### HR System
- Nightly sync: `/api/admin/hr-sync:run`
- Maps departments to default roles
- Preserves local role overrides
- Disables users when HR marks inactive

### Accounting System (Future)
- Revenue/deposit tracking
- Invoice generation
- Payment reconciliation

### Inventory System (Future)
- F&B projections from menu_json
- Equipment availability
- Cost estimation

## Next Implementation Steps

1. **Week 1**: Create Pydantic schemas + core services (auth, email, PDF)
2. **Week 2**: Build API endpoints + public intake form
3. **Week 3**: Admin UI (calendar, event forms, task management)
4. **Week 4**: Document generation + email notifications
5. **Week 5**: HR sync + RBAC enforcement + testing

## Testing Scenarios

### Public Intake
1. Submit BEO via public link → Event created with draft status
2. Tasks auto-generated from template
3. Confirmation email queued to client

### Event Management
1. Manager confirms event → Status changes, PDFs generated
2. Notifications sent to kitchen/bar/AV departments
3. Tasks due dates calculated from event start time

### RBAC
1. Staff cannot view financials_json
2. Dept lead sees task summary for own department
3. Manager can edit all fields

### HR Sync
1. New employee in HR → Auto-created with default role
2. Employee department change → Role updated if mapped
3. Employee deactivated → User.is_active = false

## File Structure
```
events/
├── src/events/
│   ├── api/          # FastAPI routes
│   ├── core/         # Config, database
│   ├── models/       # SQLAlchemy models ✅
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   ├── templates/    # HTML templates
│   └── static/       # CSS, JS
├── alembic/          # Migrations ✅
├── tests/            # Unit + integration tests
├── requirements.txt  # Dependencies ✅
├── Dockerfile        # Container ✅
└── .env.example      # Config template ✅
```

## Development

### Run Locally
```bash
cd events
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn events.main:app --reload
```

### Create Migration
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Run Tests
```bash
pytest tests/ -v
```

## Support

This is a foundational build. The complete implementation requires:
- ~40-50 API endpoints
- ~15 HTML templates
- ~8 core services
- Integration with existing HR/Accounting systems
- Comprehensive test coverage

**Estimated effort**: 3-4 weeks for full implementation by an experienced FastAPI developer.

## License

Proprietary - Internal Use Only
