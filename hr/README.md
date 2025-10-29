# HR System - Human Resources Management

## Overview

The HR System is a comprehensive human resources management platform for employee administration, scheduling, time tracking, and payroll integration. It serves as the central employee database for the entire restaurant management system and provides user authentication data to the Portal.

## Status: 85% Production Ready 🔄

## Purpose

- Employee profile management
- Department and position tracking
- Shift scheduling and availability
- Time clock and attendance tracking
- Payroll calculation and export
- User account management for Portal authentication
- Employee document storage
- Emergency contact management

## Technology Stack

- **Framework:** Django 4.2 (Python)
- **Database:** PostgreSQL 15
- **Task Queue:** Celery with Redis
- **Frontend:** Bootstrap 5, jQuery
- **Authentication:** Django auth + Portal integration

## Features

### ✅ Implemented (85%)

**Employee Management:**
- [x] Employee profiles with personal information
- [x] Department assignments
- [x] Job titles and positions
- [x] Employment status tracking
- [x] Hire date and termination date
- [x] Emergency contacts
- [x] Document upload and storage
- [x] Employee search and filtering
- [x] Active/inactive employee lists

**User Account Management:**
- [x] User accounts linked to employees
- [x] Username and password (bcrypt hashed)
- [x] System permission flags (shared with Portal)
- [x] Active/inactive status
- [x] Admin designation
- [x] Integration with Portal SSO

**Scheduling:**
- [x] Shift creation and assignment
- [x] Department-based schedules
- [x] Weekly schedule views
- [x] Availability tracking
- [x] Schedule templates
- [x] Shift swaps (partial)
- [x] Schedule publishing

**Time Tracking:**
- [x] Clock in/out functionality
- [x] Time entry records
- [x] Manual time adjustments
- [x] Overtime calculation
- [x] Break time tracking
- [x] Timesheet approval workflow

**Payroll (Partial - 50%):**
- [x] Pay rate management
- [x] Hour calculations from time entries
- [x] Regular vs overtime hours
- [x] Payroll period definition
- [x] Export timesheet data
- [ ] Direct payroll processing ❌
- [ ] Tax calculations ❌
- [ ] Direct deposit management ❌
- [ ] Pay stub generation ❌

**Reporting:**
- [x] Employee roster reports
- [x] Attendance reports
- [x] Schedule coverage reports
- [x] Timesheet summaries
- [x] Department headcount
- [x] Labor cost reports

### ❌ Missing (15%)

**Benefits Management:**
- [ ] Health insurance enrollment
- [ ] PTO/vacation tracking and accrual
- [ ] Sick leave tracking
- [ ] Holiday management
- [ ] 401k enrollment
- [ ] Benefits cost calculation

**Advanced Payroll:**
- [ ] Full payroll processing
- [ ] Tax withholding calculations
- [ ] Direct deposit file generation
- [ ] W-2 generation
- [ ] Pay stub printing

**Performance Management:**
- [ ] Performance reviews
- [ ] Goal setting and tracking
- [ ] Disciplinary actions
- [ ] Training and certifications

**Onboarding/Offboarding:**
- [ ] New hire onboarding workflows
- [ ] I-9 and W-4 form management
- [ ] Exit interviews
- [ ] Equipment tracking

## Architecture

### Database Schema

**Core Tables:**
- `employees` - Employee profiles and personal information
- `departments` - Department hierarchy
- `positions` - Job titles and positions
- `users` - User accounts (shared with Portal)
- `emergency_contacts` - Emergency contact information
- `employee_documents` - Document storage

**Scheduling Tables:**
- `shifts` - Shift definitions
- `schedules` - Schedule assignments
- `availability` - Employee availability
- `shift_swaps` - Shift swap requests
- `schedule_templates` - Reusable schedules

**Time Tracking Tables:**
- `time_entries` - Clock in/out records
- `time_adjustments` - Manual corrections
- `time_off_requests` - PTO requests
- `timesheet_approvals` - Approval workflow

**Payroll Tables:**
- `pay_rates` - Employee pay rates
- `pay_periods` - Payroll period definitions
- `payroll_runs` - Payroll processing records

### Models

**Key Django Models (53 Python files total):**
- Employee
- Department
- Position
- User (for Portal authentication)
- EmergencyContact
- EmployeeDocument
- Shift, Schedule, Availability
- TimeEntry, TimeAdjustment
- PayRate, PayPeriod, PayrollRun

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

### Scheduling

**GET /hr/api/schedules/**
- Get schedules
- Query params: `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&department=X`

**POST /hr/api/schedules/**
- Create schedule

**GET /hr/api/schedules/{id}/publish/**
- Publish schedule to employees

**POST /hr/api/shift-swaps/**
- Request shift swap

**PATCH /hr/api/shift-swaps/{id}/approve/**
- Approve/deny shift swap

### Time Tracking

**POST /hr/api/time-entries/clock-in/**
- Clock in employee

**POST /hr/api/time-entries/clock-out/**
- Clock out employee

**GET /hr/api/time-entries/**
- Get time entries
- Query params: `?employee=X&pay_period=X`

**POST /hr/api/time-adjustments/**
- Create manual time adjustment

**PATCH /hr/api/timesheets/{id}/approve/**
- Approve timesheet

### Users (Portal Integration)

**GET /hr/api/users/**
- List all users (for Portal)

**POST /hr/api/users/**
- Create user account

**PATCH /hr/api/users/{id}/permissions/**
- Update user system permissions

**GET /hr/health**
- Health check

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
5. Set hire date and pay rate
6. Save

### Creating a User Account

1. Go to HR admin or use API
2. Create user linked to employee
3. Set username and password
4. Configure system permissions
5. User can now login via Portal

### Scheduling Employees

1. Navigate to Schedules section
2. Select date range and department
3. Click "Create Schedule"
4. Assign shifts to employees
5. Review and publish schedule
6. Employees receive notifications

### Time Clock

1. Employee goes to time clock page
2. Enters employee ID or scans badge
3. Clicks "Clock In"
4. System records time entry
5. At end of shift, clicks "Clock Out"
6. Manager reviews and approves timesheets

### Running Payroll

1. Navigate to Payroll section
2. Select pay period
3. Review time entries for all employees
4. Make any necessary adjustments
5. Calculate totals (regular + overtime)
6. Export to payroll processor
7. Record payroll run

## File Structure

```
hr/
├── src/
│   └── hr/
│       ├── models/              # 13 model files
│       │   ├── employee.py
│       │   ├── department.py
│       │   ├── user.py
│       │   ├── schedule.py
│       │   ├── time_entry.py
│       │   └── payroll.py
│       ├── api/                 # 12 API route files
│       │   ├── employees.py
│       │   ├── schedules.py
│       │   ├── time_entries.py
│       │   ├── users.py
│       │   └── payroll.py
│       ├── services/            # 2 service files
│       │   ├── scheduling_service.py
│       │   └── payroll_service.py
│       ├── templates/           # 13 HTML templates
│       │   ├── employees/
│       │   ├── schedules/
│       │   ├── time_clock/
│       │   └── payroll/
│       ├── static/              # CSS, JS, images
│       ├── core/                # Settings, config
│       ├── main.py              # Django application
│       └── __init__.py
├── migrations/                  # Database migrations
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Integration with Other Systems

### Portal Integration

HR system provides user authentication data:
- User accounts
- System permissions
- Employee linkage

Portal reads from HR database `users` table for authentication.

### Accounting Integration

HR system can export:
- Labor costs by department
- Payroll expenses
- Employee reimbursements

### Events Integration (Future)

- Employee scheduling for events
- Event staff assignment
- Labor cost tracking per event

### Inventory Integration (Future)

- Manager scheduling for inventory counts
- Department head access control

## Troubleshooting

### Issue: Can't clock in
**Solution:**
- Verify employee is active
- Check time clock is enabled for location
- Ensure no open clock-in record exists

### Issue: Timesheet not calculating correctly
**Solution:**
- Check pay period dates
- Verify time entries are approved
- Review overtime calculation rules

### Issue: Schedule conflicts
**Solution:**
- Check employee availability
- Review shift overlap rules
- Verify department assignments

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

- Password hashing with bcrypt
- CSRF protection
- SQL injection prevention (Django ORM)
- XSS protection
- Secure session management
- Role-based access control
- Audit logging (partial)

## Future Enhancements

### Short-Term
- [ ] Complete benefits management
- [ ] PTO tracking and accrual
- [ ] Performance review system
- [ ] Training/certification tracking

### Medium-Term
- [ ] Full payroll processing
- [ ] Direct deposit integration
- [ ] Mobile app for time clock
- [ ] Employee self-service portal
- [ ] Automated shift bidding

### Long-Term
- [ ] AI-powered scheduling optimization
- [ ] Predictive labor cost forecasting
- [ ] Integration with benefits providers
- [ ] Background check integration
- [ ] Applicant tracking system (ATS)

## Support

For issues or questions:
- Check logs: `docker compose logs hr-app`
- Django admin: https://rm.swhgrp.com/hr/admin/
- Health check: https://rm.swhgrp.com/hr/health
- Contact: Development Team

## License

Proprietary - SW Hospitality Group Internal Use Only
