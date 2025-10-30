# HR System - Human Resources Management

## Overview

The HR System is an employee information management platform that serves as the central employee database for the entire restaurant management system. It provides employee profile management, organizational structure tracking, document storage, and user authentication data to the Portal.

## Status: Production Ready (Core Features) ✅

**Note:** This is an employee information management system. It does NOT include scheduling, time tracking, or payroll features.

## Purpose

- Employee profile management
- Department and position tracking
- User account management for Portal authentication
- Employee document storage with expiration tracking
- Emergency contact management
- Role-based access control
- Audit logging for data access

## Technology Stack

- **Framework:** Django 4.2 (Python)
- **Database:** PostgreSQL 15
- **Task Queue:** Celery with Redis
- **Frontend:** Bootstrap 5, jQuery
- **Authentication:** Django auth + Portal integration

## Features

### ✅ IMPLEMENTED

**Employee Management:**
- ✅ Employee profiles with personal information (encrypted)
  - Name, email, phone, address
  - Social Security Number (encrypted)
  - Date of birth
  - Employment status (Active, On Leave, Terminated)
  - Hire date and termination date
- ✅ Department assignments with hierarchical structure
- ✅ Job titles and positions with multiple position support per employee
- ✅ Emergency contacts (name, phone, relationship - encrypted)
- ✅ Employee search and filtering by department, status, position
- ✅ Active/inactive employee lists

**User Account Management (Portal Integration):**
- ✅ User accounts linked to employees
- ✅ Username and password authentication (bcrypt hashed)
- ✅ Role-based access control with permissions
- ✅ Admin designation and system flags
- ✅ Location-based access restrictions
- ✅ Active/inactive status management
- ✅ Portal SSO integration for seamless login
- ✅ Centralized password change with sync to all systems

**Document Management:**
- ✅ Employee document upload and storage
- ✅ Document types: Food Handler Certificate, Background Check, I-9, W-4, Performance Reviews, etc.
- ✅ Document expiration tracking and alerts
- ✅ Document status workflow (Pending, Approved, Expired, Rejected)
- ✅ Secure file storage at `/app/documents/`
- ✅ Document download and retrieval

**Department & Position Management:**
- ✅ Department creation and management
- ✅ Position definition with pay rate ranges
- ✅ Employee-position linking (many-to-many)
- ✅ Organizational structure tracking

**Security & Compliance:**
- ✅ Field-level encryption for sensitive data (SSN, emergency contacts)
- ✅ Audit logging for all employee data access and modifications
- ✅ Audit trail UI for compliance tracking
- ✅ Role-based permissions with granular access control
- ✅ Session management with timeout warnings

**Email Integration:**
- ✅ Email settings configuration (SMTP)
- ✅ Email templates for notifications
- ✅ Admin-only email configuration access

### ❌ NOT IMPLEMENTED

**Time & Attendance:**
- ❌ Time clock (clock in/out) - Not implemented
- ❌ Attendance tracking - Not implemented
- ❌ Timesheet management - Not implemented
- ❌ Break time tracking - Not implemented

**Scheduling:**
- ❌ Shift scheduling - Not implemented
- ❌ Employee availability tracking - Not implemented
- ❌ Schedule templates - Not implemented
- ❌ Shift swaps - Not implemented
- ❌ Schedule publishing - Not implemented

**Payroll:**
- ❌ Payroll calculation - Not implemented
- ❌ Overtime calculation - Not implemented
- ❌ Payroll processing - Not implemented
- ❌ Tax calculations - Not implemented
- ❌ Pay stub generation - Not implemented
- ❌ Direct deposit - Not implemented
- Note: Pay rate fields exist in Position/Employee models but no processing

**Benefits & Leave:**
- ❌ Benefits management - Not implemented
- ❌ PTO/vacation tracking - Not implemented
- ❌ Sick leave tracking - Not implemented
- ❌ Holiday management - Not implemented

**Performance Management:**
- ❌ Performance review system - Not implemented
- Note: Performance reviews can be uploaded as documents only

**Reporting:**
- ❌ Labor cost reports - Not implemented
- ❌ Attendance reports - Not implemented
- ❌ Schedule coverage reports - Not implemented
- ❌ W-2 generation - Not implemented
- ❌ Pay stub printing - Not implemented
- Note: Basic employee roster available via UI

**Other Features:**
- ❌ New hire onboarding workflows - Not implemented
- ❌ Exit interviews - Not implemented
- ❌ Equipment tracking - Not implemented
- ❌ Goal setting and tracking - Not implemented
- ❌ Disciplinary actions tracking - Not implemented
- ❌ Training and certifications - Not implemented (can upload as documents)

## Architecture

### Database Schema

**Implemented Tables:**
- `hr_employee` - Employee profiles and personal information (with encryption)
- `hr_department` - Department hierarchy
- `hr_position` - Job titles and positions
- `hr_employeeposition` - Employee-position associations (many-to-many)
- `hr_user` - User accounts (shared with Portal)
- `hr_role` - User roles for RBAC
- `hr_permission` - Permission definitions
- `hr_userrole` - User-role associations
- `hr_rolepermission` - Role-permission associations
- `hr_document` - Employee document storage
- `hr_auditlog` - Audit trail for data access and modifications
- `hr_emailsettings` - SMTP configuration

**Not Implemented:**
- ❌ Scheduling tables (shifts, schedules, availability)
- ❌ Time tracking tables (time entries, timesheets)
- ❌ Payroll tables (pay periods, payroll runs)
- ❌ PTO/leave tables
- ❌ Benefits tables

### Models

**Implemented Django Models:**
- `Employee` - Core employee profile with encrypted sensitive fields
- `Department` - Organizational units
- `Position` - Job titles with pay rate ranges
- `EmployeePosition` - Links employees to positions
- `User` - Portal authentication and authorization
- `Role` - User roles for access control
- `Permission` - Granular permissions
- `UserRole` - User-role associations
- `RolePermission` - Role-permission associations
- `Document` - Employee documents with expiration tracking
- `AuditLog` - Compliance and security audit trail
- `EmailSettings` - Email configuration

## API Endpoints

### Employee Management

**GET /hr/api/employees/**
- List all employees
- Query params: `?department=X&status=active`

**GET /hr/api/employees/{id}/**
- Get employee details

**POST /hr/api/employees/**
- Create new employee

**PUT /hr/api/employees/{id}/**
- Update employee

**DELETE /hr/api/employees/{id}/**
- Deactivate employee

### Department Management

**GET /hr/api/departments/**
- List all departments

**POST /hr/api/departments/**
- Create new department

**PUT /hr/api/departments/{id}/**
- Update department

### Position Management

**GET /hr/api/positions/**
- List all positions

**POST /hr/api/positions/**
- Create new position

**PUT /hr/api/positions/{id}/**
- Update position

### Document Management

**GET /hr/api/documents/**
- List employee documents
- Query params: `?employee_id=X&status=pending`

**POST /hr/api/documents/**
- Upload employee document

**GET /hr/api/documents/{id}/**
- Get document details

**PATCH /hr/api/documents/{id}/approve/**
- Approve/reject document

**GET /hr/api/documents/{id}/download/**
- Download document file

### Users (Portal Integration)

**GET /hr/api/users/**
- List all users (for Portal)

**POST /hr/api/users/**
- Create user account

**PUT /hr/api/users/{id}/**
- Update user account

**PATCH /hr/api/users/{id}/permissions/**
- Update user system permissions

**POST /hr/api/auth/sync-password**
- Sync password from Portal (internal use)

### Audit Logs

**GET /hr/api/audit-logs/**
- List audit log entries
- Query params: `?user_id=X&action=view&start_date=YYYY-MM-DD`

### Health Check

**GET /hr/health**
- System health check

## Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://hr_user:password@hr-db:5432/hr_db

# Django Settings
SECRET_KEY=your-django-secret-key
DEBUG=False
ALLOWED_HOSTS=rm.swhgrp.com,hr-app

# Celery (Background Jobs)
CELERY_BROKER_URL=redis://hr-redis:6379/0
CELERY_RESULT_BACKEND=redis://hr-redis:6379/0

# Email (for notifications)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-app-password

# Portal Integration
PORTAL_URL=https://rm.swhgrp.com/portal
PORTAL_SECRET_KEY=same-as-portal-secret

# File Storage
MEDIA_ROOT=/app/media
MEDIA_URL=/media/

# Timezone
TIME_ZONE=America/New_York
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15
- Redis 7

### Quick Start

1. **Set up environment:**
```bash
cd /opt/restaurant-system/hr
cp .env.example .env
# Edit .env with your configuration
```

2. **Build and start:**
```bash
docker compose up -d hr-app hr-db hr-redis
```

3. **Run migrations:**
```bash
docker compose exec hr-app python manage.py migrate
```

4. **Create superuser:**
```bash
docker compose exec hr-app python manage.py createsuperuser
```

5. **Load initial data (optional):**
```bash
docker compose exec hr-app python manage.py loaddata departments
docker compose exec hr-app python manage.py loaddata positions
```

6. **Access system:**
```
https://rm.swhgrp.com/hr/
```

## Usage

### Adding an Employee

1. Navigate to https://rm.swhgrp.com/hr/employees/
2. Click "Add Employee"
3. Fill in personal information
4. Select department and position
5. Set hire date and employment status
6. Add emergency contacts (optional)
7. Save

### Creating a User Account

1. Go to HR admin or use API
2. Create user linked to employee
3. Set username and password
4. Assign role (Admin, Manager, Employee)
5. Configure system permissions
6. User can now login via Portal

### Managing Employee Documents

1. Navigate to employee profile
2. Click "Documents" tab
3. Click "Upload Document"
4. Select document type (Food Handler Certificate, Background Check, I-9, W-4, etc.)
5. Upload file and set expiration date (if applicable)
6. Document status starts as "Pending"
7. Admin/Manager can approve or reject documents

### Viewing Audit Logs

1. Navigate to Audit Logs section (Admin only)
2. Filter by user, action type, or date range
3. View all employee data access and modifications
4. Export for compliance reporting

## File Structure

```
hr/
├── src/
│   └── hr/
│       ├── models/              # Django models
│       │   ├── employee.py     # Employee profiles
│       │   ├── department.py   # Departments and positions
│       │   ├── user.py         # User accounts and RBAC
│       │   ├── document.py     # Employee documents
│       │   ├── audit.py        # Audit logging
│       │   └── email.py        # Email settings
│       ├── api/                 # API routes
│       │   ├── employees.py    # Employee endpoints
│       │   ├── departments.py  # Department endpoints
│       │   ├── documents.py    # Document endpoints
│       │   ├── users.py        # User endpoints
│       │   ├── audit.py        # Audit log endpoints
│       │   └── auth.py         # Authentication/SSO
│       ├── templates/           # Django HTML templates
│       │   ├── base.html       # Base template with sidebar
│       │   ├── dashboard.html  # HR dashboard
│       │   ├── employees/      # Employee management pages
│       │   ├── documents/      # Document management pages
│       │   ├── audit/          # Audit log pages
│       │   └── settings/       # Email settings pages
│       ├── static/              # CSS, JS, images
│       │   ├── css/
│       │   ├── js/
│       │   └── images/
│       ├── core/                # Django settings
│       │   ├── settings.py
│       │   ├── urls.py
│       │   └── wsgi.py
│       ├── manage.py            # Django management
│       └── __init__.py
├── migrations/                  # Database migrations
├── documents/                   # Uploaded employee documents
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Integration with Other Systems

### Portal Integration

HR system is the **master source** for user authentication:
- User accounts stored in HR database
- System permissions and roles managed in HR
- Employee profiles linked to user accounts
- Portal reads from HR database for SSO authentication
- Centralized password changes sync to all systems

**SSO Flow:**
1. User logs into Portal with HR credentials
2. Portal validates against HR database
3. Portal generates JWT token
4. User clicks system link (Inventory, Accounting, Events, etc.)
5. System validates token with Portal and creates/updates local user via JIT provisioning

### Password Synchronization

When a user changes their password via Portal:
- HR database is updated first (master)
- Portal syncs password to all microservices:
  - Inventory System
  - Accounting System
  - Events System
  - Integration Hub
  - Files System
- Uses internal service authentication with `X-Portal-Auth` header
- Gracefully handles systems where user hasn't logged in yet (JIT)

### Accounting Integration (Planned)

Potential future integration:
- Export employee cost data by department
- Employee reimbursement tracking

### Events Integration (Planned)

Potential future integration:
- Event staff assignment based on employee data
- Access control for event management

### Inventory Integration (Planned)

Potential future integration:
- Department head access control
- Manager assignments for inventory operations

## Troubleshooting

### Issue: Can't login via Portal
**Solution:**
- Verify employee has an active user account in HR system
- Check user is marked as `is_active=True`
- Ensure correct username and password
- Check HR database connection

### Issue: User can't access certain systems
**Solution:**
- Verify user role and permissions in HR system
- Check system-specific access flags
- Ensure user has logged into system at least once (JIT provisioning)
- Check location-based access restrictions if configured

### Issue: Document upload fails
**Solution:**
- Verify file size is within limits
- Check supported file types (PDF, JPG, PNG, DOCX)
- Ensure `/app/documents/` directory has write permissions
- Check available disk space

### Issue: Password change not syncing
**Solution:**
- Check Portal service is running
- Verify `PORTAL_SECRET_KEY` matches across all systems
- Review Portal logs for sync errors
- Systems where user hasn't logged in yet will sync on first login (JIT)

### Issue: Encrypted fields showing garbled data
**Solution:**
- Verify `FIELD_ENCRYPTION_KEY` environment variable is set
- Check encryption key hasn't changed (data encrypted with old key)
- Review Django cryptography library installation

### Issue: Audit logs not recording
**Solution:**
- Check Celery worker is running
- Verify Redis connection for task queue
- Review application logs for errors
- Ensure audit logging middleware is enabled

## Development

### Running Locally

```bash
cd /opt/restaurant-system/hr

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/hr/health
```

### Logs
```bash
docker compose logs -f hr-app
```

### Celery Tasks
```bash
docker compose logs -f hr-celery-worker
```

## Dependencies

Key packages (see requirements.txt for complete list):
- Django 4.2
- djangorestframework
- psycopg2-binary
- celery
- redis
- pillow (image handling)
- reportlab (PDF generation)
- openpyxl (Excel export)

## Security

**Authentication & Authorization:**
- Password hashing with bcrypt (via Django's default hasher)
- Role-based access control (RBAC) with granular permissions
- User session management with timeout warnings
- SSO integration with Portal via JWT tokens
- Location-based access restrictions

**Data Protection:**
- Field-level encryption for sensitive data:
  - Social Security Numbers (SSN)
  - Emergency contact information
  - Other PII as configured
- Environment variable for encryption key (`FIELD_ENCRYPTION_KEY`)
- Django cryptography library

**Application Security:**
- CSRF protection (Django built-in)
- SQL injection prevention (Django ORM parameterized queries)
- XSS protection (Django template auto-escaping)
- Secure session cookies (HttpOnly, Secure flags)
- Content Security Policy headers

**Audit & Compliance:**
- Comprehensive audit logging for all employee data access
- Tracks: user, action (view/create/update/delete), timestamp, IP address
- Audit log UI for compliance reporting
- Document expiration tracking and alerts

**Network Security:**
- Internal service authentication with `X-Portal-Auth` header
- All inter-service communication on private Docker network
- Public access via Nginx reverse proxy with HTTPS
- Rate limiting on authentication endpoints

## Future Enhancements

### Potential Feature Additions

**Employee Management Enhancements:**
- [ ] Performance review system (digital reviews, ratings, goals)
- [ ] Training and certification tracking (beyond document uploads)
- [ ] Disciplinary action tracking
- [ ] Exit interview management
- [ ] New hire onboarding workflows
- [ ] Equipment checkout tracking

**Time & Attendance (Not Currently Implemented):**
- [ ] Time clock system (clock in/out)
- [ ] Timesheet management and approval
- [ ] Attendance tracking and reporting
- [ ] Break time tracking
- [ ] Overtime calculation

**Scheduling (Not Currently Implemented):**
- [ ] Shift scheduling and templates
- [ ] Employee availability management
- [ ] Schedule publishing and notifications
- [ ] Shift swap requests and approvals
- [ ] Coverage reporting
- [ ] AI-powered scheduling optimization

**Payroll (Not Currently Implemented):**
- [ ] Payroll calculation and processing
- [ ] Pay stub generation
- [ ] Direct deposit integration
- [ ] Tax calculations and reporting
- [ ] W-2 generation
- [ ] Labor cost analytics

**Benefits & Leave (Not Currently Implemented):**
- [ ] Benefits enrollment and management
- [ ] PTO/vacation accrual and tracking
- [ ] Sick leave management
- [ ] Holiday calendar
- [ ] Leave request workflow

**Reporting & Analytics:**
- [ ] Headcount and turnover reports
- [ ] Labor cost analysis by department
- [ ] Document expiration dashboard improvements
- [ ] Custom report builder
- [ ] Data export to Excel/PDF

**Integration Enhancements:**
- [ ] Background check API integration
- [ ] Benefits provider integration
- [ ] Applicant tracking system (ATS)
- [ ] Payroll processor integration
- [ ] Employee self-service mobile app

## Support

For issues or questions:
- Check logs: `docker compose logs hr-app`
- Django admin: https://rm.swhgrp.com/hr/admin/
- Health check: https://rm.swhgrp.com/hr/health
- Contact: Development Team

## License

Proprietary - SW Hospitality Group Internal Use Only
