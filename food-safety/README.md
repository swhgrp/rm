# Food Safety & Compliance Service

A FastAPI microservice for managing food safety compliance, temperature monitoring, daily checklists, incident tracking, and health inspections.

## Overview

This service provides comprehensive food safety management including:
- **Temperature Logging** - Manual and automated equipment temperature monitoring with threshold alerts
- **Daily Checklists** - Customizable food safety checklists by location, type, and shift
- **Incident Management** - Track food safety incidents with auto-generated incident numbers (INC-YYYY-NNNN)
- **Inspection Records** - Health inspection tracking with corrective actions
- **HACCP Plans** - Critical control point management per location
- **Reports & Exports** - Comprehensive compliance reports with CSV/PDF export
- **User Permissions** - Role-based access control (users from HR, permissions managed here)

## Architecture

- **Framework**: FastAPI with async support
- **Database**: PostgreSQL 15 with async SQLAlchemy ORM
- **Migrations**: Alembic
- **Port**: 8007 (service), 5440 (database)
- **Container**: food-safety-service, food-safety-postgres

## Directory Structure

```
food-safety/
├── src/
│   └── food_safety/
│       ├── __init__.py
│       ├── main.py              # FastAPI application
│       ├── config.py            # Configuration settings
│       ├── database.py          # Database connection
│       ├── models/              # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── users.py         # User permissions
│       │   ├── locations.py     # Locations & equipment
│       │   ├── temperatures.py  # Temperature logs
│       │   ├── checklists.py    # Checklist definitions & submissions
│       │   ├── incidents.py     # Incident tracking
│       │   └── inspections.py   # Inspection records
│       ├── routers/             # API endpoints
│       │   ├── __init__.py
│       │   ├── dashboard.py     # Dashboard & summary stats
│       │   ├── users.py         # User permission management
│       │   ├── temperatures.py  # Temperature logging
│       │   ├── checklists.py    # Checklist management
│       │   ├── incidents.py     # Incident management
│       │   ├── inspections.py   # Inspection records
│       │   ├── haccp.py         # HACCP plan management
│       │   └── reports.py       # Compliance reports & exports
│       └── services/            # Business logic
│           ├── __init__.py
│           ├── alerts.py        # Email alert service
│           └── hr_client.py     # HR service integration
├── alembic/                     # Database migrations
├── tests/                       # Test suite
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Database Schema

### Core Tables

- **user_permissions** - Maps HR users to food safety roles
- **locations** - Restaurant locations (synced from inventory)
- **equipment** - Temperature-monitored equipment
- **shifts** - Configurable shifts per location

### Temperature Monitoring

- **temperature_logs** - Individual temperature readings
- **temperature_thresholds** - Min/max thresholds per equipment type

### Checklists

- **checklist_templates** - Reusable checklist definitions
- **checklist_items** - Individual items within templates
- **checklist_submissions** - Completed checklist instances
- **checklist_responses** - Responses to individual items
- **manager_signoffs** - Required sign-offs (configurable per checklist type)

### Incidents & Inspections

- **incidents** - Food safety incident records (INC-YYYY-NNNN)
- **corrective_actions** - Actions taken to resolve issues
- **inspections** - Health inspection records
- **inspection_violations** - Violations found during inspections

### HACCP

- **haccp_plans** - HACCP plan definitions per location
- **critical_control_points** - CCPs within each plan

## API Endpoints

### Dashboard
- `GET /api/dashboard` - Summary statistics and alerts

### Users & Permissions
- `GET /api/users` - List users with permissions
- `POST /api/users/{hr_user_id}/permissions` - Set user permissions
- `DELETE /api/users/{hr_user_id}/permissions` - Remove user access

### Temperature Logging
- `GET /api/temperatures` - List temperature logs
- `POST /api/temperatures` - Log temperature reading
- `GET /api/temperatures/equipment/{id}` - Equipment temperature history
- `GET /api/temperatures/alerts` - Active temperature alerts

### Checklists
- `GET /api/checklists/templates` - List checklist templates
- `POST /api/checklists/templates` - Create template
- `GET /api/checklists/submissions` - List submissions
- `POST /api/checklists/submissions` - Submit completed checklist
- `POST /api/checklists/submissions/{id}/signoff` - Manager sign-off

### Incidents
- `GET /api/incidents` - List incidents
- `POST /api/incidents` - Create incident (auto-generates INC number)
- `GET /api/incidents/{id}` - Get incident details
- `PUT /api/incidents/{id}` - Update incident
- `POST /api/incidents/{id}/corrective-actions` - Add corrective action

### Inspections
- `GET /api/inspections` - List inspections
- `POST /api/inspections` - Record inspection
- `POST /api/inspections/{id}/violations` - Add violation (auto-creates corrective action)

### HACCP
- `GET /api/haccp/plans` - List HACCP plans
- `POST /api/haccp/plans` - Create plan
- `GET /api/haccp/plans/{id}/ccps` - List critical control points

### Reports
- `GET /api/reports/temperature` - Temperature log report with summary, trends, details
- `GET /api/reports/temperature/export/csv` - Export temperature report as CSV
- `GET /api/reports/temperature/export/pdf` - Export temperature report as PDF
- `GET /api/reports/checklist` - Checklist compliance report
- `GET /api/reports/checklist/export/csv` - Export checklist report as CSV
- `GET /api/reports/checklist/export/pdf` - Export checklist report as PDF
- `GET /api/reports/inspection` - Inspection results report
- `GET /api/reports/inspection/export/csv` - Export inspection report as CSV
- `GET /api/reports/inspection/export/pdf` - Export inspection report as PDF
- `GET /api/reports/incident` - Incident summary report
- `GET /api/reports/incident/export/csv` - Export incident report as CSV
- `GET /api/reports/incident/export/pdf` - Export incident report as PDF

## User Roles

| Role | Description |
|------|-------------|
| `admin` | Full access to all features and settings |
| `manager` | Can sign off checklists, manage incidents, view reports |
| `supervisor` | Can log temperatures, complete checklists, create incidents |
| `staff` | Can log temperatures and complete assigned checklists |
| `readonly` | View-only access to dashboards and reports |

## Alerts

Email alerts are sent for:
- Temperature readings outside thresholds
- Overdue checklists
- New incidents requiring attention
- Upcoming inspection deadlines

Push notifications planned for future release.

## Configuration

Environment variables:
```
DATABASE_URL=postgresql+asyncpg://food_safety:password@food-safety-postgres:5432/food_safety
HR_SERVICE_URL=http://hr-app:8000
SMTP_HOST=smtp.example.com
SMTP_PORT=587
ALERT_EMAIL_FROM=foodsafety@example.com
```

## Development

```bash
# Start services
cd food-safety
docker-compose up -d

# Run migrations
docker exec food-safety-service alembic upgrade head

# View logs
docker logs -f food-safety-service
```

## Integration

- **HR Service** - Fetches employee list for user permissions
- **Inventory Service** - Syncs location data
- **Portal** - Web UI at /portal/food-safety/

## Implementation Phases

1. **Phase 1: Core Daily Operations**
   - Temperature logging
   - Daily checklists
   - Basic dashboard

2. **Phase 2: Incident Management**
   - Incident tracking
   - Corrective actions
   - Manager sign-offs

3. **Phase 3: Compliance & Reporting**
   - Inspection records
   - HACCP management
   - Reporting and exports
