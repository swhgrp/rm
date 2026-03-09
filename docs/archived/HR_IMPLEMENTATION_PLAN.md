# HR System - Implementation Plan

**Project**: Restaurant Management System - HR Module
**Version**: 1.0
**Created**: October 15, 2025
**Estimated Duration**: 12 days (2.5 weeks)
**Status**: Planning Complete - Ready to Build

---

## TABLE OF CONTENTS

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Integration Strategy](#integration-strategy)
4. [Implementation Sequence](#implementation-sequence)
5. [Database Schema](#database-schema)
6. [API Endpoints](#api-endpoints)
7. [Testing Checklist](#testing-checklist)
8. [Success Metrics](#success-metrics)

---

## OVERVIEW

### Purpose
Build a comprehensive HR management system as the third microservice in the restaurant management platform, following the established architecture pattern (inventory + accounting).

### Core Features
- Employee management with multi-location support
- Document retention with expiration tracking
- **Scheduling system with shift templates and swap management** (ADDED TO SCOPE)
- Time tracking (Clover POS sync only - no manual entry)
- Payroll preparation and export
- Position and department management
- Compliance and certification tracking
- **Progressive Web App with push notifications for employees** (ADDED TO SCOPE)

### Key Design Decisions

#### ✅ Clover Time Clock Integration
- **Decision**: Pull shift data FROM Clover (one-way sync)
- **Rationale**: Employees already use Clover, avoid duplicate workflows
- **Implementation**: Sync every 15 minutes via Clover Shifts API
- **Endpoint**: `GET /v3/merchants/{mId}/employees/{empId}/shifts`

#### ✅ Inventory User Sync
- **Decision**: Separate databases, API-based linking (not hard FK)
- **Rationale**: Maintain standalone capability for both systems
- **Implementation**: Optional `inventory_user_id` field, nullable
- **Benefit**: Inventory can work without HR, HR can work without Inventory

#### ✅ Microservices Pattern
- **Decision**: Follow existing architecture (separate DB, Docker container)
- **Access**: `https://rm.swhgrp.com/hr/`
- **Database**: PostgreSQL (hr_db)
- **Technology**: Python 3.11 + FastAPI + SQLAlchemy

---

## SYSTEM ARCHITECTURE

### Services Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clover POS                              │
│  (Source of Truth for Time Clock & POS Employees)              │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ API Sync (Every 15 min)
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                         HR Service                               │
│                                                                  │
│  Database: hr_db (PostgreSQL 15)                                │
│  Port: 8000 (internal)                                          │
│  URL: https://rm.swhgrp.com/hr/                                 │
│                                                                  │
│  Employees Table:                                               │
│  ├── employee_number (primary)                                  │
│  ├── clover_employee_id (link to Clover)                       │
│  ├── inventory_user_id (optional link to inventory)            │
│  └── ... other HR data                                          │
│                                                                  │
│  Shifts Table (synced from Clover):                            │
│  ├── employee_id                                                │
│  ├── clover_shift_id                                            │
│  ├── clock_in, clock_out                                        │
│  └── location_id                                                │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ Optional API Sync
                 │ (Create user when employee added)
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Inventory Service                            │
│                    (Can work standalone)                        │
│                                                                  │
│  Users Table:                                                   │
│  ├── id                                                         │
│  ├── username, email                                            │
│  ├── role                                                       │
│  └── ... (no reference to HR)                                   │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 │ Labor Cost Journal Entries
                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Accounting Service                            │
│                                                                  │
│  Receives: Payroll summary for labor cost entries              │
└─────────────────────────────────────────────────────────────────┘
```

### Docker Configuration

```yaml
hr-db:
  image: postgres:15
  container_name: hr-db
  environment:
    POSTGRES_USER: hr_user
    POSTGRES_PASSWORD: HR_Pr0d_2024!
    POSTGRES_DB: hr_db
  volumes:
    - hr_data:/var/lib/postgresql/data
  networks:
    - restaurant-network

hr-app:
  build: ./hr
  container_name: hr-app
  volumes:
    - ./hr/src:/app/src
    - ./hr/documents:/app/documents
  env_file:
    - ./hr/.env
  environment:
    - DATABASE_URL=postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db
    - REDIS_URL=redis://inventory-redis:6379
    - INVENTORY_API_URL=http://inventory-app:8000/api
    - ACCOUNTING_API_URL=http://accounting-app:8000/api
  depends_on:
    hr-db:
      condition: service_healthy
    inventory-redis:
      condition: service_healthy
  networks:
    - restaurant-network
```

### Nginx Routing

```nginx
# In shared/nginx/conf.d/rm.swhgrp.com-http.conf
location /hr/ {
    proxy_pass http://hr-app:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## INTEGRATION STRATEGY

### 1. Clover POS Integration

#### Clover Employees API
```python
# Endpoints to use:
GET /v3/merchants/{merchantId}/employees              # Get all employees
GET /v3/merchants/{merchantId}/employees/{empId}      # Get employee details
GET /v3/merchants/{merchantId}/employees/{empId}/shifts  # Get shifts
```

#### Sync Strategy
- **Frequency**: Every 15 minutes (background scheduler)
- **Direction**: One-way (Clover → HR)
- **Employee Matching**: Match by email, fallback to name
- **Shift Import**: Import all shifts for last 30 days on first sync

#### Employee Sync Logic
```python
# hr/services/clover_sync.py

async def sync_employees_from_clover():
    """
    1. Fetch all employees from Clover
    2. Match existing HR employees by email
    3. Update clover_employee_id if matched
    4. Create new HR employee if not found (optional)
    5. Update sync timestamp
    """
    clover_employees = await clover_client.get_employees()

    for clover_emp in clover_employees['elements']:
        hr_employee = find_by_email(clover_emp['email'])

        if hr_employee:
            hr_employee.clover_employee_id = clover_emp['id']
            hr_employee.clover_synced_at = datetime.utcnow()
        else:
            # Optional: Create new employee
            create_employee_from_clover(clover_emp)
```

#### Shift Sync Logic
```python
async def sync_shifts_from_clover(start_date, end_date):
    """
    1. Get all employees with clover_employee_id
    2. For each employee, fetch shifts from Clover
    3. Check if shift exists (by clover_shift_id)
    4. Create or update shift
    5. Calculate total hours
    """
    employees = get_employees_with_clover_id()

    for employee in employees:
        clover_shifts = await clover_client.get_employee_shifts(
            employee.clover_employee_id,
            start_date,
            end_date
        )

        for clover_shift in clover_shifts['elements']:
            shift = find_by_clover_shift_id(clover_shift['id'])

            if not shift:
                shift = create_shift(
                    employee_id=employee.id,
                    clover_shift_id=clover_shift['id'],
                    clock_in=from_timestamp(clover_shift['inTime']),
                    clock_out=from_timestamp(clover_shift['outTime']),
                )

            shift.total_hours = calculate_hours(shift.clock_in, shift.clock_out)
```

### 2. Inventory User Integration

#### Linking Strategy
- **Field**: `employees.inventory_user_id` (nullable Integer)
- **No Foreign Key**: API reference only, no DB constraint
- **Direction**: HR → Inventory (create users from employees)
- **Trigger**: Checkbox "Create Inventory User Account" when adding employee

#### Sync Logic
```python
# hr/services/inventory_client.py

async def create_inventory_user_from_employee(employee_id: int) -> int:
    """
    1. Get employee details
    2. Call Inventory API to create user
    3. Store returned user_id in employee.inventory_user_id
    4. Return user_id
    """
    employee = get_employee(employee_id)

    # Call inventory API
    response = await httpx.post(
        f"{INVENTORY_API_URL}/users",
        json={
            "username": generate_username(employee.email),
            "email": employee.email,
            "full_name": f"{employee.first_name} {employee.last_name}",
            "role": "Staff"  # Default role
        },
        headers={"Authorization": f"Bearer {INVENTORY_API_KEY}"}
    )

    user_id = response.json()['id']

    # Update employee record
    employee.inventory_user_id = user_id
    employee.inventory_sync_enabled = True
    db.commit()

    return user_id
```

#### Termination Sync
```python
async def deactivate_inventory_user_on_termination(employee_id: int):
    """
    When employee status changes to 'Terminated':
    1. Get employee's inventory_user_id
    2. Call Inventory API to deactivate user
    3. Log the action
    """
    employee = get_employee(employee_id)

    if employee.inventory_user_id:
        await httpx.patch(
            f"{INVENTORY_API_URL}/users/{employee.inventory_user_id}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {INVENTORY_API_KEY}"}
        )
```

### 3. Accounting Integration

#### Labor Cost Entries
```python
# When payroll period is closed, create journal entries

async def create_labor_cost_entries(payroll_period_id: int):
    """
    1. Calculate total labor costs by location
    2. Create journal entry for each location
    3. Debit: Labor Expense (6000)
    4. Credit: Wages Payable (2100)
    """
    period = get_payroll_period(payroll_period_id)
    costs_by_location = calculate_labor_costs(period)

    for location_id, total_cost in costs_by_location.items():
        await httpx.post(
            f"{ACCOUNTING_API_URL}/journal-entries",
            json={
                "date": period.period_end,
                "description": f"Payroll for {period.period_start} to {period.period_end}",
                "entries": [
                    {
                        "account_number": "6000",  # Labor Expense
                        "debit": total_cost,
                        "credit": 0
                    },
                    {
                        "account_number": "2100",  # Wages Payable
                        "debit": 0,
                        "credit": total_cost
                    }
                ]
            }
        )
```

---

## IMPLEMENTATION SEQUENCE

### PHASE 1: FOUNDATION (Days 1-3)

#### Step 1: Project Setup (Day 1 - Morning)

**Tasks:**
1. Create directory structure
   ```bash
   mkdir -p /opt/restaurant-system/hr/src/hr/{api/api_v1/endpoints,core,db,models,schemas,services,templates,static/{css,js}}
   mkdir -p /opt/restaurant-system/hr/alembic/versions
   mkdir -p /opt/restaurant-system/hr/documents
   ```

2. Create Dockerfile
   ```dockerfile
   FROM python:3.11-slim

   WORKDIR /app

   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       postgresql-client \
       && rm -rf /var/lib/apt/lists/*

   # Copy requirements and install Python dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Copy application code
   COPY src/ ./src/
   COPY alembic/ ./alembic/
   COPY alembic.ini .

   # Run migrations and start server
   CMD alembic upgrade head && \
       uvicorn hr.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Create requirements.txt
   ```
   fastapi==0.104.1
   uvicorn[standard]==0.24.0
   sqlalchemy==2.0.23
   alembic==1.12.1
   psycopg2-binary==2.9.9
   pydantic==2.5.0
   pydantic-settings==2.1.0
   python-jose[cryptography]==3.3.0
   passlib[bcrypt]==1.7.4
   python-multipart==0.0.6
   jinja2==3.1.2
   httpx==0.25.2
   redis==5.0.1
   apscheduler==3.10.4
   python-dateutil==2.8.2
   ```

4. Create .env file
   ```bash
   # Database
   DATABASE_URL=postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db
   REDIS_URL=redis://inventory-redis:6379

   # Application
   APP_NAME=SW HR Management
   APP_URL=https://rm.swhgrp.com/hr
   SECRET_KEY=your-secret-key-here-change-in-production

   # Clover Integration (to be added in Phase 4)
   CLOVER_MERCHANT_ID=
   CLOVER_ACCESS_TOKEN=
   CLOVER_ENVIRONMENT=production
   CLOVER_SYNC_ENABLED=false

   # Inventory Integration (to be added in Phase 5)
   INVENTORY_API_URL=http://inventory-app:8000/api
   INVENTORY_API_KEY=
   INVENTORY_SYNC_ENABLED=false

   # Accounting Integration
   ACCOUNTING_API_URL=http://accounting-app:8000/api
   ACCOUNTING_API_KEY=
   ```

5. Update docker-compose.yml
   - Add hr-db service
   - Add hr-app service
   - Add hr_data volume

6. Update Nginx configuration
   - Add `/hr/` location block

**Deliverables:**
- ✅ Directory structure created
- ✅ Dockerfile ready
- ✅ requirements.txt complete
- ✅ .env configured
- ✅ docker-compose.yml updated
- ✅ Nginx routing added

**Test:**
```bash
cd /opt/restaurant-system
docker compose up hr-db -d
docker compose ps  # Verify hr-db is healthy
```

---

#### Step 2: Database Setup (Day 1 - Afternoon)

**Tasks:**

1. Create database configuration
   ```python
   # hr/db/database.py
   from sqlalchemy import create_engine
   from sqlalchemy.ext.declarative import declarative_base
   from sqlalchemy.orm import sessionmaker
   import os

   DATABASE_URL = os.getenv("DATABASE_URL")

   engine = create_engine(DATABASE_URL)
   SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
   Base = declarative_base()

   def get_db():
       db = SessionLocal()
       try:
           yield db
       finally:
           db.close()
   ```

2. Create Employee model
   ```python
   # hr/models/employee.py
   from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime
   from sqlalchemy.sql import func
   from hr.db.database import Base

   class Employee(Base):
       __tablename__ = "employees"

       id = Column(Integer, primary_key=True, index=True)
       employee_number = Column(String, unique=True, nullable=False, index=True)

       # Basic Info
       first_name = Column(String, nullable=False)
       last_name = Column(String, nullable=False)
       middle_name = Column(String, nullable=True)
       email = Column(String, unique=True, nullable=False, index=True)
       phone_number = Column(String)

       # Address
       street_address = Column(String)
       city = Column(String)
       state = Column(String)
       zip_code = Column(String)

       # Emergency Contact
       emergency_contact_name = Column(String)
       emergency_contact_phone = Column(String)
       emergency_contact_relationship = Column(String)

       # Employment Info
       hire_date = Column(Date, nullable=False)
       termination_date = Column(Date, nullable=True)
       employment_status = Column(String, default="Active", nullable=False)  # Active, On Leave, Terminated
       employee_type = Column(String, default="Part-Time")  # Full-Time, Part-Time, Contractor

       # Integration Fields (added later, but defined now for future)
       clover_employee_id = Column(String, unique=True, nullable=True, index=True)
       clover_synced_at = Column(DateTime(timezone=True), nullable=True)
       inventory_user_id = Column(Integer, nullable=True, index=True)
       inventory_sync_enabled = Column(Boolean, default=False)

       # Metadata
       created_at = Column(DateTime(timezone=True), server_default=func.now())
       updated_at = Column(DateTime(timezone=True), onupdate=func.now())
       created_by = Column(Integer, nullable=True)  # User ID who created
   ```

3. Create Position model
   ```python
   # hr/models/position.py
   from sqlalchemy import Column, Integer, String, Boolean, Numeric, Text
   from hr.db.database import Base

   class Position(Base):
       __tablename__ = "positions"

       id = Column(Integer, primary_key=True, index=True)
       title = Column(String, nullable=False, index=True)  # Server, Cook, Manager
       department = Column(String)  # Front of House, Back of House, Management
       description = Column(Text)

       # Pay Range
       hourly_rate_min = Column(Numeric(10, 2))
       hourly_rate_max = Column(Numeric(10, 2))

       # Status
       is_active = Column(Boolean, default=True)
   ```

4. Create EmployeePosition model
   ```python
   # hr/models/employee_position.py
   from sqlalchemy import Column, Integer, String, Date, Boolean, Numeric, ForeignKey
   from sqlalchemy.orm import relationship
   from hr.db.database import Base

   class EmployeePosition(Base):
       __tablename__ = "employee_positions"

       id = Column(Integer, primary_key=True, index=True)
       employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
       position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)

       # Location (API reference, not FK)
       location_id = Column(Integer, nullable=True)

       # Pay Info
       hourly_rate = Column(Numeric(10, 2))
       salary = Column(Numeric(10, 2), nullable=True)

       # Assignment Period
       start_date = Column(Date, nullable=False)
       end_date = Column(Date, nullable=True)

       # Primary Position Flag
       is_primary = Column(Boolean, default=True)

       # Relationships
       employee = relationship("Employee", backref="position_assignments")
       position = relationship("Position", backref="assignments")
   ```

5. Create Alembic configuration
   ```python
   # alembic/env.py
   from logging.config import fileConfig
   from sqlalchemy import engine_from_config, pool
   from alembic import context
   import os
   import sys

   # Add parent directory to path
   sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

   from hr.db.database import Base
   from hr.models.employee import Employee
   from hr.models.position import Position
   from hr.models.employee_position import EmployeePosition

   config = context.config
   config.set_main_option('sqlalchemy.url', os.getenv('DATABASE_URL'))

   target_metadata = Base.metadata

   # ... rest of standard Alembic env.py
   ```

6. Create initial migration
   ```bash
   docker compose exec hr-app alembic revision --autogenerate -m "Initial schema"
   docker compose exec hr-app alembic upgrade head
   ```

**Deliverables:**
- ✅ Database models created
- ✅ Alembic configured
- ✅ Initial migration created
- ✅ Database tables created

**Test:**
```bash
docker compose exec hr-db psql -U hr_user -d hr_db -c "\dt"
# Should show: employees, positions, employee_positions
```

---

#### Step 3: Basic API Endpoints (Day 2)

**Tasks:**

1. Create configuration
   ```python
   # hr/core/config.py
   from pydantic_settings import BaseSettings

   class Settings(BaseSettings):
       APP_NAME: str = "SW HR Management"
       APP_URL: str
       DATABASE_URL: str
       SECRET_KEY: str

       # Integration settings
       CLOVER_MERCHANT_ID: str = ""
       CLOVER_ACCESS_TOKEN: str = ""
       CLOVER_SYNC_ENABLED: bool = False

       INVENTORY_API_URL: str = ""
       INVENTORY_SYNC_ENABLED: bool = False

       class Config:
           env_file = ".env"

   settings = Settings()
   ```

2. Create Pydantic schemas
   ```python
   # hr/schemas/position.py
   from pydantic import BaseModel
   from decimal import Decimal
   from typing import Optional

   class PositionBase(BaseModel):
       title: str
       department: Optional[str] = None
       description: Optional[str] = None
       hourly_rate_min: Optional[Decimal] = None
       hourly_rate_max: Optional[Decimal] = None
       is_active: bool = True

   class PositionCreate(PositionBase):
       pass

   class PositionUpdate(PositionBase):
       pass

   class Position(PositionBase):
       id: int

       class Config:
           from_attributes = True
   ```

   ```python
   # hr/schemas/employee.py
   from pydantic import BaseModel, EmailStr
   from datetime import date
   from typing import Optional

   class EmployeeBase(BaseModel):
       employee_number: str
       first_name: str
       last_name: str
       middle_name: Optional[str] = None
       email: EmailStr
       phone_number: Optional[str] = None
       hire_date: date
       employment_status: str = "Active"
       employee_type: str = "Part-Time"

   class EmployeeCreate(EmployeeBase):
       create_inventory_user: bool = False  # For Phase 5

   class EmployeeUpdate(BaseModel):
       first_name: Optional[str] = None
       last_name: Optional[str] = None
       email: Optional[EmailStr] = None
       phone_number: Optional[str] = None
       employment_status: Optional[str] = None

   class Employee(EmployeeBase):
       id: int
       termination_date: Optional[date] = None
       inventory_user_id: Optional[int] = None

       class Config:
           from_attributes = True
   ```

3. Create API endpoints
   ```python
   # hr/api/api_v1/endpoints/positions.py
   from fastapi import APIRouter, Depends, HTTPException
   from sqlalchemy.orm import Session
   from hr.db.database import get_db
   from hr.schemas.position import Position, PositionCreate, PositionUpdate
   from hr.models.position import Position as PositionModel
   from typing import List

   router = APIRouter()

   @router.post("/", response_model=Position)
   def create_position(position: PositionCreate, db: Session = Depends(get_db)):
       db_position = PositionModel(**position.dict())
       db.add(db_position)
       db.commit()
       db.refresh(db_position)
       return db_position

   @router.get("/", response_model=List[Position])
   def list_positions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
       positions = db.query(PositionModel).offset(skip).limit(limit).all()
       return positions

   @router.get("/{position_id}", response_model=Position)
   def get_position(position_id: int, db: Session = Depends(get_db)):
       position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
       if not position:
           raise HTTPException(status_code=404, detail="Position not found")
       return position

   @router.put("/{position_id}", response_model=Position)
   def update_position(position_id: int, position: PositionUpdate, db: Session = Depends(get_db)):
       db_position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
       if not db_position:
           raise HTTPException(status_code=404, detail="Position not found")

       for key, value in position.dict(exclude_unset=True).items():
           setattr(db_position, key, value)

       db.commit()
       db.refresh(db_position)
       return db_position

   @router.delete("/{position_id}")
   def delete_position(position_id: int, db: Session = Depends(get_db)):
       db_position = db.query(PositionModel).filter(PositionModel.id == position_id).first()
       if not db_position:
           raise HTTPException(status_code=404, detail="Position not found")

       db.delete(db_position)
       db.commit()
       return {"message": "Position deleted"}
   ```

   ```python
   # hr/api/api_v1/endpoints/employees.py
   # Similar CRUD endpoints for employees
   ```

4. Create main application
   ```python
   # hr/main.py
   from fastapi import FastAPI
   from fastapi.staticfiles import StaticFiles
   from fastapi.templating import Jinja2Templates
   from hr.api.api_v1.endpoints import positions, employees
   from hr.core.config import settings

   app = FastAPI(title=settings.APP_NAME)

   # Mount static files
   app.mount("/static", StaticFiles(directory="src/hr/static"), name="static")

   # Templates
   templates = Jinja2Templates(directory="src/hr/templates")

   # API routes
   app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
   app.include_router(employees.router, prefix="/api/employees", tags=["employees"])

   @app.get("/")
   async def root():
       return {"message": "HR Management System"}

   @app.get("/health")
   async def health():
       return {"status": "healthy"}
   ```

**Deliverables:**
- ✅ Position CRUD API complete
- ✅ Employee CRUD API complete
- ✅ Pydantic schemas created
- ✅ Basic validation working

**Test:**
```bash
# Create position
curl -X POST https://rm.swhgrp.com/hr/api/positions \
  -H "Content-Type: application/json" \
  -d '{"title": "Server", "department": "Front of House", "hourly_rate_min": 15.00, "hourly_rate_max": 25.00}'

# List positions
curl https://rm.swhgrp.com/hr/api/positions

# Create employee
curl -X POST https://rm.swhgrp.com/hr/api/employees \
  -H "Content-Type: application/json" \
  -d '{"employee_number": "EMP001", "first_name": "John", "last_name": "Doe", "email": "john@example.com", "hire_date": "2025-01-15"}'
```

---

#### Step 4: Basic UI Templates (Day 3)

**Tasks:**

1. Create base template
   ```html
   <!-- hr/templates/base.html -->
   <!DOCTYPE html>
   <html lang="en" data-theme="dark">
   <head>
       <meta charset="UTF-8">
       <meta name="viewport" content="width=device-width, initial-scale=1.0">
       <base href="/hr/">
       <title>{% block title %}SW HR Management{% endblock %}</title>
       <link rel="stylesheet" href="static/css/style.css">
   </head>
   <body>
       <nav class="navbar">
           <div class="nav-brand">
               <img src="/images/sw-logo.png" alt="SW Logo">
               <h1>HR Management</h1>
           </div>
           <ul class="nav-menu">
               <li><a href="">Dashboard</a></li>
               <li><a href="employees">Employees</a></li>
               <li><a href="positions">Positions</a></li>
               <li><a href="time-clock">Time Clock</a></li>
               <li><a href="documents">Documents</a></li>
               <li><a href="reports">Reports</a></li>
           </ul>
       </nav>

       <main class="container">
           {% block content %}{% endblock %}
       </main>

       <script src="static/js/main.js"></script>
       {% block scripts %}{% endblock %}
   </body>
   </html>
   ```

2. Create positions page
   ```html
   <!-- hr/templates/positions.html -->
   {% extends "base.html" %}

   {% block title %}Positions - SW HR Management{% endblock %}

   {% block content %}
   <div class="page-header">
       <h2>Positions</h2>
       <button onclick="showAddPositionModal()" class="btn btn-primary">Add Position</button>
   </div>

   <table id="positionsTable" class="data-table">
       <thead>
           <tr>
               <th>Title</th>
               <th>Department</th>
               <th>Pay Range</th>
               <th>Status</th>
               <th>Actions</th>
           </tr>
       </thead>
       <tbody>
           <!-- Populated via JavaScript -->
       </tbody>
   </table>

   <!-- Add Position Modal -->
   <div id="addPositionModal" class="modal" style="display: none;">
       <div class="modal-content">
           <h3>Add Position</h3>
           <form id="addPositionForm">
               <label>Title:</label>
               <input type="text" name="title" required>

               <label>Department:</label>
               <select name="department">
                   <option>Front of House</option>
                   <option>Back of House</option>
                   <option>Management</option>
               </select>

               <label>Min Hourly Rate:</label>
               <input type="number" step="0.01" name="hourly_rate_min">

               <label>Max Hourly Rate:</label>
               <input type="number" step="0.01" name="hourly_rate_max">

               <button type="submit" class="btn btn-primary">Save</button>
               <button type="button" onclick="closeModal()" class="btn">Cancel</button>
           </form>
       </div>
   </div>
   {% endblock %}

   {% block scripts %}
   <script src="static/js/positions.js"></script>
   {% endblock %}
   ```

3. Create employees page (similar structure)

4. Create JavaScript for API calls
   ```javascript
   // hr/static/js/positions.js
   async function loadPositions() {
       const response = await fetch('/hr/api/positions');
       const positions = await response.json();

       const tbody = document.querySelector('#positionsTable tbody');
       tbody.innerHTML = '';

       positions.forEach(position => {
           const row = `
               <tr>
                   <td>${position.title}</td>
                   <td>${position.department || '-'}</td>
                   <td>$${position.hourly_rate_min} - $${position.hourly_rate_max}</td>
                   <td>${position.is_active ? 'Active' : 'Inactive'}</td>
                   <td>
                       <button onclick="editPosition(${position.id})">Edit</button>
                       <button onclick="deletePosition(${position.id})">Delete</button>
                   </td>
               </tr>
           `;
           tbody.innerHTML += row;
       });
   }

   document.getElementById('addPositionForm').addEventListener('submit', async (e) => {
       e.preventDefault();
       const formData = new FormData(e.target);
       const data = Object.fromEntries(formData);

       await fetch('/hr/api/positions', {
           method: 'POST',
           headers: {'Content-Type': 'application/json'},
           body: JSON.stringify(data)
       });

       closeModal();
       loadPositions();
   });

   window.addEventListener('load', loadPositions);
   ```

5. Create CSS (copy from inventory, adjust for HR)

**Deliverables:**
- ✅ Base template with navigation
- ✅ Positions page functional
- ✅ Employees page functional
- ✅ Can create/edit via UI
- ✅ Dark mode styling

**Test:**
- Visit `https://rm.swhgrp.com/hr/`
- Navigate to positions page
- Add a new position
- Verify it appears in table

---

### PHASE 2: DOCUMENT MANAGEMENT (Days 4-5)

#### Step 5: Document Upload System (Day 4)

**Tasks:**

1. Create Document model
   ```python
   # hr/models/document.py
   from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text
   from sqlalchemy.orm import relationship
   from sqlalchemy.sql import func
   from hr.db.database import Base

   class Document(Base):
       __tablename__ = "documents"

       id = Column(Integer, primary_key=True, index=True)
       employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

       # Document Info
       document_type = Column(String, nullable=False)  # I-9, W-4, Contract, Certification, etc.
       file_name = Column(String, nullable=False)
       file_path = Column(String, nullable=False)
       file_size = Column(Integer)  # bytes
       mime_type = Column(String)

       # Metadata
       uploaded_by = Column(Integer)  # User ID who uploaded
       uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

       # Expiration Tracking
       expiration_date = Column(Date, nullable=True)
       status = Column(String, default="Current")  # Current, Expired, Archived

       # Notes
       notes = Column(Text)

       # Relationship
       employee = relationship("Employee", backref="documents")
   ```

2. Create document endpoints
   ```python
   # hr/api/api_v1/endpoints/documents.py
   from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
   from fastapi.responses import FileResponse
   from sqlalchemy.orm import Session
   from hr.db.database import get_db
   from hr.models.document import Document
   import os
   import shutil
   from datetime import datetime

   router = APIRouter()

   UPLOAD_DIR = "/app/documents"
   ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png'}
   MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

   @router.post("/employees/{employee_id}/documents")
   async def upload_document(
       employee_id: int,
       file: UploadFile = File(...),
       document_type: str = "Other",
       expiration_date: str = None,
       notes: str = None,
       db: Session = Depends(get_db)
   ):
       # Validate file extension
       file_ext = os.path.splitext(file.filename)[1].lower()
       if file_ext not in ALLOWED_EXTENSIONS:
           raise HTTPException(400, "File type not allowed")

       # Validate file size
       file.file.seek(0, 2)
       file_size = file.file.tell()
       file.file.seek(0)

       if file_size > MAX_FILE_SIZE:
           raise HTTPException(400, "File too large (max 10MB)")

       # Create employee directory
       employee_dir = os.path.join(UPLOAD_DIR, str(employee_id))
       os.makedirs(employee_dir, exist_ok=True)

       # Generate unique filename
       timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
       safe_filename = f"{timestamp}_{file.filename}"
       file_path = os.path.join(employee_dir, safe_filename)

       # Save file
       with open(file_path, "wb") as buffer:
           shutil.copyfileobj(file.file, buffer)

       # Create database record
       document = Document(
           employee_id=employee_id,
           document_type=document_type,
           file_name=file.filename,
           file_path=file_path,
           file_size=file_size,
           mime_type=file.content_type,
           expiration_date=expiration_date,
           notes=notes
       )

       db.add(document)
       db.commit()
       db.refresh(document)

       return document

   @router.get("/employees/{employee_id}/documents")
   def list_documents(employee_id: int, db: Session = Depends(get_db)):
       documents = db.query(Document).filter(Document.employee_id == employee_id).all()
       return documents

   @router.get("/documents/{document_id}/download")
   def download_document(document_id: int, db: Session = Depends(get_db)):
       document = db.query(Document).filter(Document.id == document_id).first()
       if not document:
           raise HTTPException(404, "Document not found")

       if not os.path.exists(document.file_path):
           raise HTTPException(404, "File not found on disk")

       return FileResponse(
           document.file_path,
           filename=document.file_name,
           media_type=document.mime_type
       )

   @router.delete("/documents/{document_id}")
   def delete_document(document_id: int, db: Session = Depends(get_db)):
       document = db.query(Document).filter(Document.id == document_id).first()
       if not document:
           raise HTTPException(404, "Document not found")

       # Delete file from disk
       if os.path.exists(document.file_path):
           os.remove(document.file_path)

       # Delete database record
       db.delete(document)
       db.commit()

       return {"message": "Document deleted"}
   ```

3. Create migration for documents table
   ```bash
   docker compose exec hr-app alembic revision --autogenerate -m "Add documents table"
   docker compose exec hr-app alembic upgrade head
   ```

**Deliverables:**
- ✅ Document model created
- ✅ Upload endpoint working
- ✅ Download endpoint working
- ✅ File validation working
- ✅ Files saved to disk

**Test:**
```bash
# Upload document
curl -X POST https://rm.swhgrp.com/hr/api/employees/1/documents \
  -F "file=@test.pdf" \
  -F "document_type=I-9"

# List documents
curl https://rm.swhgrp.com/hr/api/employees/1/documents

# Download document
curl https://rm.swhgrp.com/hr/api/documents/1/download -o downloaded.pdf
```

---

#### Step 6: Document Management UI (Day 5)

**Tasks:**

1. Add documents section to employee detail page
2. Create upload modal with drag-and-drop
3. Create document list with download/delete buttons
4. Add expiration status badges
5. Create expiration tracking dashboard

**Deliverables:**
- ✅ Upload documents via UI
- ✅ View document list
- ✅ Download documents
- ✅ Delete documents
- ✅ See expiration warnings

**Test:**
- Upload multiple documents for an employee
- Download a document
- Check expiration status display

---

### PHASE 3: TIME TRACKING FOUNDATION (Days 6-7)

#### Step 7: Manual Time Entry (Day 6)

**Tasks:**

1. Create Shift model
   ```python
   # hr/models/shift.py
   from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Text
   from sqlalchemy.orm import relationship
   from hr.db.database import Base

   class Shift(Base):
       __tablename__ = "shifts"

       id = Column(Integer, primary_key=True, index=True)
       employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

       # Shift Times
       clock_in = Column(DateTime(timezone=True), nullable=False)
       clock_out = Column(DateTime(timezone=True), nullable=True)

       # Override Times (for manager adjustments)
       override_in = Column(DateTime(timezone=True), nullable=True)
       override_out = Column(DateTime(timezone=True), nullable=True)

       # Calculated
       total_hours = Column(Numeric(5, 2))
       break_duration = Column(Integer)  # minutes

       # Location
       location_id = Column(Integer)  # API reference

       # Status
       status = Column(String, default="completed")  # completed, no-show, pending

       # Integration (added later)
       clover_shift_id = Column(String, unique=True, nullable=True, index=True)

       # Notes
       notes = Column(Text)

       # Relationship
       employee = relationship("Employee", backref="shifts")
   ```

2. Create shift endpoints
   ```python
   # hr/api/api_v1/endpoints/shifts.py
   from fastapi import APIRouter, Depends
   from sqlalchemy.orm import Session
   from hr.db.database import get_db
   from hr.models.shift import Shift
   from datetime import datetime, timedelta

   router = APIRouter()

   def calculate_hours(clock_in, clock_out, break_duration=0):
       if not clock_out:
           return None
       delta = clock_out - clock_in
       hours = delta.total_seconds() / 3600
       break_hours = break_duration / 60
       return round(hours - break_hours, 2)

   @router.post("/shifts")
   def create_shift(shift_data: dict, db: Session = Depends(get_db)):
       shift = Shift(**shift_data)

       # Calculate hours
       if shift.clock_in and shift.clock_out:
           shift.total_hours = calculate_hours(
               shift.clock_in,
               shift.clock_out,
               shift.break_duration or 0
           )

       db.add(shift)
       db.commit()
       db.refresh(shift)
       return shift

   @router.get("/shifts")
   def list_shifts(
       employee_id: int = None,
       start_date: str = None,
       end_date: str = None,
       db: Session = Depends(get_db)
   ):
       query = db.query(Shift)

       if employee_id:
           query = query.filter(Shift.employee_id == employee_id)

       if start_date:
           query = query.filter(Shift.clock_in >= start_date)

       if end_date:
           query = query.filter(Shift.clock_in <= end_date)

       return query.all()

   @router.get("/employees/{employee_id}/shifts")
   def get_employee_shifts(
       employee_id: int,
       start_date: str = None,
       end_date: str = None,
       db: Session = Depends(get_db)
   ):
       query = db.query(Shift).filter(Shift.employee_id == employee_id)

       if start_date:
           query = query.filter(Shift.clock_in >= start_date)
       if end_date:
           query = query.filter(Shift.clock_in <= end_date)

       return query.all()
   ```

3. Create migration
   ```bash
   docker compose exec hr-app alembic revision --autogenerate -m "Add shifts table"
   docker compose exec hr-app alembic upgrade head
   ```

**Deliverables:**
- ✅ Shift model created
- ✅ Can create manual shifts
- ✅ Hours calculated automatically
- ✅ Can query shifts by date/employee

**Test:**
```bash
# Create shift
curl -X POST https://rm.swhgrp.com/hr/api/shifts \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": 1,
    "clock_in": "2025-10-15T09:00:00Z",
    "clock_out": "2025-10-15T17:00:00Z",
    "break_duration": 30
  }'

# List shifts
curl https://rm.swhgrp.com/hr/api/shifts?employee_id=1
```

---

#### Step 8: Time Tracking UI (Day 7)

**Tasks:**

1. Create time clock page
2. Create timesheet view (weekly/monthly)
3. Add shift entry modal
4. Create hours summary/totals
5. Add CSV export

**Deliverables:**
- ✅ Time clock UI functional
- ✅ Can enter shifts manually
- ✅ View timesheets
- ✅ Calculate weekly hours
- ✅ Export timesheet CSV

**Test:**
- Enter a week of shifts
- View timesheet
- Verify hours calculation
- Export CSV

---

### PHASE 4: CLOVER INTEGRATION (Days 8-10)

#### Step 9: Clover Employee Sync (Day 8)

**Tasks:**

1. Copy Clover client from inventory
   ```python
   # hr/core/clover_client.py
   # Copy from inventory/src/restaurant_inventory/core/clover_client.py
   # Add employee-specific methods

   async def get_employees(self, limit: int = 1000):
       return await self._make_request("GET", "employees", params={"limit": limit})

   async def get_employee(self, employee_id: str):
       return await self._make_request("GET", f"employees/{employee_id}")
   ```

2. Create Clover sync service
   ```python
   # hr/services/clover_sync.py
   from hr.core.clover_client import CloverAPIClient
   from hr.models.employee import Employee
   from hr.db.database import SessionLocal
   from datetime import datetime

   async def sync_employees_from_clover():
       """Sync employees from Clover to HR database"""
       db = SessionLocal()

       try:
           clover = CloverAPIClient(
               merchant_id=settings.CLOVER_MERCHANT_ID,
               access_token=settings.CLOVER_ACCESS_TOKEN,
               environment=settings.CLOVER_ENVIRONMENT
           )

           # Get all Clover employees
           response = await clover.get_employees()
           clover_employees = response.get('elements', [])

           for clover_emp in clover_employees:
               # Try to find existing employee by email
               email = clover_emp.get('email')
               if not email:
                   continue

               hr_employee = db.query(Employee).filter(Employee.email == email).first()

               if hr_employee:
                   # Update existing employee
                   hr_employee.clover_employee_id = clover_emp['id']
                   hr_employee.clover_synced_at = datetime.utcnow()
               else:
                   # Optional: Create new employee from Clover
                   # This can be enabled/disabled via settings
                   if settings.CLOVER_AUTO_CREATE_EMPLOYEES:
                       create_employee_from_clover(clover_emp, db)

           db.commit()
           return {"synced": len(clover_employees)}

       finally:
           db.close()

   def create_employee_from_clover(clover_emp, db):
       """Create HR employee from Clover employee data"""
       employee = Employee(
           employee_number=f"CLV{clover_emp['id'][-6:]}",
           first_name=clover_emp.get('name', '').split()[0],
           last_name=clover_emp.get('name', '').split()[-1] if len(clover_emp.get('name', '').split()) > 1 else '',
           email=clover_emp['email'],
           hire_date=datetime.now().date(),
           clover_employee_id=clover_emp['id'],
           clover_synced_at=datetime.utcnow()
       )
       db.add(employee)
   ```

3. Create sync endpoint
   ```python
   # hr/api/api_v1/endpoints/sync.py
   from fastapi import APIRouter
   from hr.services.clover_sync import sync_employees_from_clover

   router = APIRouter()

   @router.post("/sync/clover/employees")
   async def sync_clover_employees():
       result = await sync_employees_from_clover()
       return result
   ```

4. Add sync button to UI

**Deliverables:**
- ✅ Clover client integrated
- ✅ Employee sync service working
- ✅ Can match Clover employees to HR employees
- ✅ Manual sync button in UI

**Test:**
```bash
# Trigger sync
curl -X POST https://rm.swhgrp.com/hr/api/sync/clover/employees

# Verify employees have clover_employee_id populated
curl https://rm.swhgrp.com/hr/api/employees
```

---

#### Step 10: Clover Shift Sync (Day 9)

**Tasks:**

1. Add shift sync to Clover client
   ```python
   # Add to hr/core/clover_client.py

   async def get_employee_shifts(
       self,
       employee_id: str,
       start_date: Optional[date] = None,
       end_date: Optional[date] = None
   ):
       params = {}

       if start_date:
           start_ms = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
           params["filter"] = f"inTime>={start_ms}"

       return await self._make_request(
           "GET",
           f"employees/{employee_id}/shifts",
           params=params
       )
   ```

2. Create shift sync service
   ```python
   # Add to hr/services/clover_sync.py

   async def sync_shifts_from_clover(start_date=None, end_date=None):
       """Sync shifts from Clover for all linked employees"""
       db = SessionLocal()

       try:
           clover = CloverAPIClient(...)

           # Get all employees with Clover link
           employees = db.query(Employee).filter(
               Employee.clover_employee_id.isnot(None)
           ).all()

           total_synced = 0

           for employee in employees:
               # Get shifts from Clover
               response = await clover.get_employee_shifts(
                   employee.clover_employee_id,
                   start_date,
                   end_date
               )

               clover_shifts = response.get('elements', [])

               for clover_shift in clover_shifts:
                   # Check if shift already exists
                   existing_shift = db.query(Shift).filter(
                       Shift.clover_shift_id == clover_shift['id']
                   ).first()

                   if existing_shift:
                       # Update existing shift
                       update_shift_from_clover(existing_shift, clover_shift)
                   else:
                       # Create new shift
                       create_shift_from_clover(employee.id, clover_shift, db)

                   total_synced += 1

           db.commit()
           return {"synced_shifts": total_synced}

       finally:
           db.close()

   def create_shift_from_clover(employee_id, clover_shift, db):
       """Create HR shift from Clover shift data"""
       clock_in = datetime.fromtimestamp(clover_shift['inTime'] / 1000)
       clock_out = datetime.fromtimestamp(clover_shift['outTime'] / 1000) if clover_shift.get('outTime') else None

       shift = Shift(
           employee_id=employee_id,
           clover_shift_id=clover_shift['id'],
           clock_in=clock_in,
           clock_out=clock_out,
           status='completed' if clock_out else 'pending'
       )

       # Calculate hours
       if clock_out:
           shift.total_hours = calculate_hours(clock_in, clock_out)

       db.add(shift)
   ```

3. Create scheduled task
   ```python
   # hr/services/scheduler.py
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from hr.services.clover_sync import sync_shifts_from_clover
   from datetime import datetime, timedelta

   scheduler = AsyncIOScheduler()

   @scheduler.scheduled_job('interval', minutes=15)
   async def auto_sync_clover_shifts():
       """Auto-sync Clover shifts every 15 minutes"""
       # Sync last 7 days
       end_date = datetime.now().date()
       start_date = end_date - timedelta(days=7)

       await sync_shifts_from_clover(start_date, end_date)

   def start_scheduler():
       scheduler.start()
   ```

4. Start scheduler in main.py
   ```python
   # Add to hr/main.py
   from hr.services.scheduler import start_scheduler
   from hr.core.config import settings

   @app.on_event("startup")
   async def startup_event():
       if settings.CLOVER_SYNC_ENABLED:
           start_scheduler()
   ```

**Deliverables:**
- ✅ Shift sync service working
- ✅ Auto-sync every 15 minutes
- ✅ Manual sync endpoint
- ✅ Clover shifts appear in HR timesheet

**Test:**
```bash
# Manual sync
curl -X POST https://rm.swhgrp.com/hr/api/sync/clover/shifts

# Verify shifts
curl https://rm.swhgrp.com/hr/api/shifts?employee_id=1

# Clock in/out in Clover POS, wait 15 minutes, verify sync
```

---

#### Step 11: Payroll Preparation (Day 10)

**Tasks:**

1. Create PayrollPeriod model
   ```python
   # hr/models/payroll_period.py
   from sqlalchemy import Column, Integer, Date, String, Numeric
   from hr.db.database import Base

   class PayrollPeriod(Base):
       __tablename__ = "payroll_periods"

       id = Column(Integer, primary_key=True)
       period_start = Column(Date, nullable=False)
       period_end = Column(Date, nullable=False)
       pay_date = Column(Date)

       status = Column(String, default="Open")  # Open, Processing, Closed, Paid

       # Calculated totals
       total_hours = Column(Numeric(10, 2))
       total_amount = Column(Numeric(12, 2))
   ```

2. Create payroll calculation service
   ```python
   # hr/services/payroll.py
   from hr.models.shift import Shift
   from hr.models.employee_position import EmployeePosition
   from sqlalchemy import and_

   def calculate_payroll_for_period(period_id, db):
       """Calculate payroll summary for a period"""
       period = db.query(PayrollPeriod).filter(PayrollPeriod.id == period_id).first()

       # Get all shifts in period
       shifts = db.query(Shift).filter(
           and_(
               Shift.clock_in >= period.period_start,
               Shift.clock_in <= period.period_end,
               Shift.clock_out.isnot(None)
           )
       ).all()

       # Group by employee
       employee_hours = {}
       for shift in shifts:
           if shift.employee_id not in employee_hours:
               employee_hours[shift.employee_id] = {
                   'total_hours': 0,
                   'regular_hours': 0,
                   'overtime_hours': 0,
                   'total_pay': 0
               }

           employee_hours[shift.employee_id]['total_hours'] += float(shift.total_hours or 0)

       # Calculate pay for each employee
       payroll_summary = []
       for employee_id, hours_data in employee_hours.items():
           employee = db.query(Employee).filter(Employee.id == employee_id).first()

           # Get employee's current hourly rate
           position_assignment = db.query(EmployeePosition).filter(
               and_(
                   EmployeePosition.employee_id == employee_id,
                   EmployeePosition.is_primary == True,
                   EmployeePosition.end_date.is_(None)
               )
           ).first()

           hourly_rate = float(position_assignment.hourly_rate) if position_assignment else 0

           # Calculate regular and overtime
           total_hours = hours_data['total_hours']
           if total_hours > 40:
               regular_hours = 40
               overtime_hours = total_hours - 40
           else:
               regular_hours = total_hours
               overtime_hours = 0

           # Calculate pay
           regular_pay = regular_hours * hourly_rate
           overtime_pay = overtime_hours * hourly_rate * 1.5
           total_pay = regular_pay + overtime_pay

           payroll_summary.append({
               'employee_id': employee_id,
               'employee_name': f"{employee.first_name} {employee.last_name}",
               'employee_number': employee.employee_number,
               'total_hours': total_hours,
               'regular_hours': regular_hours,
               'overtime_hours': overtime_hours,
               'hourly_rate': hourly_rate,
               'regular_pay': regular_pay,
               'overtime_pay': overtime_pay,
               'total_pay': total_pay
           })

       return payroll_summary
   ```

3. Create payroll export (CSV for ADP/Paychex)
   ```python
   # hr/services/payroll_export.py
   import csv
   from io import StringIO

   def export_payroll_to_csv(payroll_summary):
       """Export payroll summary to CSV format"""
       output = StringIO()
       writer = csv.writer(output)

       # Header
       writer.writerow([
           'Employee Number',
           'Employee Name',
           'Regular Hours',
           'Overtime Hours',
           'Total Hours',
           'Hourly Rate',
           'Regular Pay',
           'Overtime Pay',
           'Total Pay'
       ])

       # Data rows
       for row in payroll_summary:
           writer.writerow([
               row['employee_number'],
               row['employee_name'],
               f"{row['regular_hours']:.2f}",
               f"{row['overtime_hours']:.2f}",
               f"{row['total_hours']:.2f}",
               f"{row['hourly_rate']:.2f}",
               f"{row['regular_pay']:.2f}",
               f"{row['overtime_pay']:.2f}",
               f"{row['total_pay']:.2f}"
           ])

       return output.getvalue()
   ```

4. Create payroll endpoints
   ```python
   # hr/api/api_v1/endpoints/payroll.py
   from fastapi import APIRouter, Depends
   from fastapi.responses import StreamingResponse
   from io import BytesIO

   router = APIRouter()

   @router.post("/payroll/periods")
   def create_payroll_period(period_data: dict, db: Session = Depends(get_db)):
       period = PayrollPeriod(**period_data)
       db.add(period)
       db.commit()
       db.refresh(period)
       return period

   @router.get("/payroll/periods/{period_id}/summary")
   def get_payroll_summary(period_id: int, db: Session = Depends(get_db)):
       summary = calculate_payroll_for_period(period_id, db)
       return summary

   @router.get("/payroll/periods/{period_id}/export")
   def export_payroll(period_id: int, db: Session = Depends(get_db)):
       summary = calculate_payroll_for_period(period_id, db)
       csv_data = export_payroll_to_csv(summary)

       return StreamingResponse(
           iter([csv_data]),
           media_type="text/csv",
           headers={"Content-Disposition": "attachment; filename=payroll_export.csv"}
       )
   ```

**Deliverables:**
- ✅ Payroll period model
- ✅ Calculate hours and pay
- ✅ Overtime calculation (>40 hours)
- ✅ Export to CSV
- ✅ Payroll summary endpoint

**Test:**
```bash
# Create payroll period
curl -X POST https://rm.swhgrp.com/hr/api/payroll/periods \
  -H "Content-Type: application/json" \
  -d '{
    "period_start": "2025-10-01",
    "period_end": "2025-10-15",
    "pay_date": "2025-10-20"
  }'

# Get summary
curl https://rm.swhgrp.com/hr/api/payroll/periods/1/summary

# Export CSV
curl https://rm.swhgrp.com/hr/api/payroll/periods/1/export -o payroll.csv
```

---

### PHASE 5: INVENTORY INTEGRATION (Days 11-12)

#### Step 12: Inventory User Sync (Day 11)

**Tasks:**

1. Create Inventory API client
   ```python
   # hr/services/inventory_client.py
   import httpx
   from hr.core.config import settings

   class InventoryAPIClient:
       def __init__(self):
           self.base_url = settings.INVENTORY_API_URL
           self.api_key = settings.INVENTORY_API_KEY

       async def create_user(self, user_data):
           """Create user in inventory system"""
           async with httpx.AsyncClient() as client:
               response = await client.post(
                   f"{self.base_url}/users",
                   json=user_data,
                   headers={"Authorization": f"Bearer {self.api_key}"}
               )
               response.raise_for_status()
               return response.json()

       async def update_user(self, user_id, user_data):
           """Update user in inventory system"""
           async with httpx.AsyncClient() as client:
               response = await client.patch(
                   f"{self.base_url}/users/{user_id}",
                   json=user_data,
                   headers={"Authorization": f"Bearer {self.api_key}"}
               )
               response.raise_for_status()
               return response.json()

       async def deactivate_user(self, user_id):
           """Deactivate user in inventory system"""
           return await self.update_user(user_id, {"is_active": False})
   ```

2. Create user sync service
   ```python
   # hr/services/inventory_sync.py
   from hr.services.inventory_client import InventoryAPIClient
   from hr.models.employee import Employee

   async def create_inventory_user_from_employee(employee_id, db):
       """Create inventory user account from HR employee"""
       employee = db.query(Employee).filter(Employee.id == employee_id).first()

       if not employee:
           raise ValueError("Employee not found")

       if employee.inventory_user_id:
           raise ValueError("Employee already has inventory user account")

       # Generate username from email
       username = employee.email.split('@')[0]

       # Create user in inventory
       client = InventoryAPIClient()
       user_data = {
           "username": username,
           "email": employee.email,
           "full_name": f"{employee.first_name} {employee.last_name}",
           "role": "Staff"  # Default role
       }

       result = await client.create_user(user_data)

       # Update employee with user_id
       employee.inventory_user_id = result['id']
       employee.inventory_sync_enabled = True
       db.commit()

       return result

   async def sync_employee_termination(employee_id, db):
       """Sync employee termination to inventory (deactivate user)"""
       employee = db.query(Employee).filter(Employee.id == employee_id).first()

       if employee.inventory_user_id:
           client = InventoryAPIClient()
           await client.deactivate_user(employee.inventory_user_id)
   ```

3. Update employee create/update endpoints
   ```python
   # Modify hr/api/api_v1/endpoints/employees.py

   @router.post("/", response_model=Employee)
   async def create_employee(
       employee: EmployeeCreate,
       db: Session = Depends(get_db)
   ):
       # Create employee
       db_employee = Employee(**employee.dict(exclude={'create_inventory_user'}))
       db.add(db_employee)
       db.commit()
       db.refresh(db_employee)

       # Optionally create inventory user
       if employee.create_inventory_user and settings.INVENTORY_SYNC_ENABLED:
           await create_inventory_user_from_employee(db_employee.id, db)
           db.refresh(db_employee)

       return db_employee

   @router.put("/{employee_id}", response_model=Employee)
   async def update_employee(
       employee_id: int,
       employee: EmployeeUpdate,
       db: Session = Depends(get_db)
   ):
       db_employee = db.query(Employee).filter(Employee.id == employee_id).first()

       # Check if being terminated
       if employee.employment_status == "Terminated" and db_employee.employment_status != "Terminated":
           db_employee.termination_date = datetime.now().date()

           # Sync to inventory
           if settings.INVENTORY_SYNC_ENABLED:
               await sync_employee_termination(employee_id, db)

       # Update employee
       for key, value in employee.dict(exclude_unset=True).items():
           setattr(db_employee, key, value)

       db.commit()
       db.refresh(db_employee)
       return db_employee
   ```

4. Add checkbox to employee form UI

**Deliverables:**
- ✅ Inventory API client working
- ✅ Can create inventory users from HR
- ✅ Link stored in employee record
- ✅ Termination syncs to inventory
- ✅ Checkbox in employee form

**Test:**
```bash
# Create employee with inventory user
curl -X POST https://rm.swhgrp.com/hr/api/employees \
  -H "Content-Type: application/json" \
  -d '{
    "employee_number": "EMP002",
    "first_name": "Jane",
    "last_name": "Smith",
    "email": "jane@example.com",
    "hire_date": "2025-10-15",
    "create_inventory_user": true
  }'

# Verify user created in inventory
curl https://rm.swhgrp.com/inventory/api/users

# Terminate employee and verify user deactivated
curl -X PUT https://rm.swhgrp.com/hr/api/employees/2 \
  -H "Content-Type: application/json" \
  -d '{"employment_status": "Terminated"}'
```

---

#### Step 13: Testing & Documentation (Day 12)

**Tasks:**

1. **End-to-End Testing**
   - Create employee → assign position → upload documents
   - Verify Clover employee sync
   - Verify Clover shift sync
   - Create manual shifts → verify hours calculation
   - Create payroll period → export CSV
   - Create employee with inventory user → verify in inventory
   - Terminate employee → verify user deactivated

2. **Update Documentation**

   Create HR_USER_GUIDE.md:
   ```markdown
   # HR System User Guide

   ## Getting Started
   - How to access the HR system
   - Login credentials

   ## Managing Employees
   - Adding new employees
   - Uploading documents
   - Assigning positions
   - Terminating employees

   ## Time Tracking
   - How Clover sync works
   - Manual time entry
   - Viewing timesheets
   - Approving hours

   ## Payroll
   - Creating payroll periods
   - Reviewing hours
   - Exporting for payroll processing

   ## Troubleshooting
   - Common issues
   - Contact information
   ```

   Update OPERATIONS_GUIDE.md:
   ```markdown
   ## HR System Operations

   ### Daily Tasks
   - Review time clock entries
   - Approve timesheets

   ### Weekly Tasks
   - Review Clover sync status
   - Check document expirations

   ### Bi-Weekly Tasks
   - Generate payroll export
   - Submit to payroll provider

   ### Monthly Tasks
   - Review employee status
   - Archive old documents

   ### Commands
   ```bash
   # Check HR service status
   docker compose ps hr-app hr-db

   # View HR logs
   docker compose logs -f hr-app

   # Manual Clover sync
   curl -X POST https://rm.swhgrp.com/hr/api/sync/clover/employees
   curl -X POST https://rm.swhgrp.com/hr/api/sync/clover/shifts

   # Backup HR database
   docker compose exec hr-db pg_dump -U hr_user hr_db > hr_backup.sql
   ```
   ```

   Update ARCHITECTURE.md:
   - Add HR service section
   - Update service diagram
   - Document integration points

   Update README.md:
   - Add HR system to features list
   - Add link to HR_USER_GUIDE.md

3. **Update Monitoring Scripts**

   Add to scripts/health_check.sh:
   ```bash
   # Check HR service
   check_container "hr-app" "HR Service"
   check_container "hr-db" "HR Database"
   ```

   Add to scripts/backup_databases.sh:
   ```bash
   # Backup HR database
   log_message "Backing up HR database..."
   docker compose exec -T hr-db pg_dump -U hr_user hr_db > \
       "$BACKUP_DIR/hr_db_$TIMESTAMP.sql"
   ```

**Deliverables:**
- ✅ All features tested end-to-end
- ✅ HR_USER_GUIDE.md created
- ✅ OPERATIONS_GUIDE.md updated
- ✅ ARCHITECTURE.md updated
- ✅ README.md updated
- ✅ Monitoring scripts updated
- ✅ Backup scripts updated

**Test:**
- Run full end-to-end workflow
- Verify all documentation is accurate
- Test backup script
- Test health check script

---

## DATABASE SCHEMA

### Complete Schema Reference

```sql
-- Employees Table
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    employee_number VARCHAR UNIQUE NOT NULL,

    -- Basic Info
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    middle_name VARCHAR,
    email VARCHAR UNIQUE NOT NULL,
    phone_number VARCHAR,

    -- Address
    street_address VARCHAR,
    city VARCHAR,
    state VARCHAR,
    zip_code VARCHAR,

    -- Emergency Contact
    emergency_contact_name VARCHAR,
    emergency_contact_phone VARCHAR,
    emergency_contact_relationship VARCHAR,

    -- Employment
    hire_date DATE NOT NULL,
    termination_date DATE,
    employment_status VARCHAR DEFAULT 'Active',
    employee_type VARCHAR DEFAULT 'Part-Time',

    -- Integration
    clover_employee_id VARCHAR UNIQUE,
    clover_synced_at TIMESTAMP WITH TIME ZONE,
    inventory_user_id INTEGER,
    inventory_sync_enabled BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by INTEGER
);

CREATE INDEX idx_employees_email ON employees(email);
CREATE INDEX idx_employees_clover_id ON employees(clover_employee_id);
CREATE INDEX idx_employees_status ON employees(employment_status);

-- Positions Table
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    title VARCHAR NOT NULL,
    department VARCHAR,
    description TEXT,
    hourly_rate_min NUMERIC(10, 2),
    hourly_rate_max NUMERIC(10, 2),
    is_active BOOLEAN DEFAULT TRUE
);

-- Employee Positions (Assignment)
CREATE TABLE employee_positions (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    position_id INTEGER REFERENCES positions(id),
    location_id INTEGER,
    hourly_rate NUMERIC(10, 2),
    salary NUMERIC(10, 2),
    start_date DATE NOT NULL,
    end_date DATE,
    is_primary BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_emp_pos_employee ON employee_positions(employee_id);
CREATE INDEX idx_emp_pos_position ON employee_positions(position_id);

-- Documents Table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    document_type VARCHAR NOT NULL,
    file_name VARCHAR NOT NULL,
    file_path VARCHAR NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR,
    uploaded_by INTEGER,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expiration_date DATE,
    status VARCHAR DEFAULT 'Current',
    notes TEXT
);

CREATE INDEX idx_documents_employee ON documents(employee_id);
CREATE INDEX idx_documents_expiration ON documents(expiration_date);

-- Shifts Table
CREATE TABLE shifts (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,

    clock_in TIMESTAMP WITH TIME ZONE NOT NULL,
    clock_out TIMESTAMP WITH TIME ZONE,
    override_in TIMESTAMP WITH TIME ZONE,
    override_out TIMESTAMP WITH TIME ZONE,

    total_hours NUMERIC(5, 2),
    break_duration INTEGER,

    location_id INTEGER,
    status VARCHAR DEFAULT 'completed',

    clover_shift_id VARCHAR UNIQUE,
    notes TEXT
);

CREATE INDEX idx_shifts_employee ON shifts(employee_id);
CREATE INDEX idx_shifts_date ON shifts(clock_in);
CREATE INDEX idx_shifts_clover ON shifts(clover_shift_id);

-- Payroll Periods Table
CREATE TABLE payroll_periods (
    id SERIAL PRIMARY KEY,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    pay_date DATE,
    status VARCHAR DEFAULT 'Open',
    total_hours NUMERIC(10, 2),
    total_amount NUMERIC(12, 2)
);

CREATE INDEX idx_payroll_dates ON payroll_periods(period_start, period_end);
```

---

## API ENDPOINTS

### Complete API Reference

#### Positions
```
POST   /api/positions              Create position
GET    /api/positions              List positions
GET    /api/positions/{id}         Get position
PUT    /api/positions/{id}         Update position
DELETE /api/positions/{id}         Delete position
```

#### Employees
```
POST   /api/employees              Create employee
GET    /api/employees              List employees
GET    /api/employees/{id}         Get employee
PUT    /api/employees/{id}         Update employee
DELETE /api/employees/{id}         Deactivate employee
GET    /api/employees/{id}/positions  Get employee positions
POST   /api/employees/{id}/positions  Assign position
```

#### Documents
```
POST   /api/employees/{id}/documents    Upload document
GET    /api/employees/{id}/documents    List documents
GET    /api/documents/{id}/download     Download document
DELETE /api/documents/{id}              Delete document
GET    /api/documents/expiring          Get expiring documents
```

#### Shifts
```
POST   /api/shifts                 Create shift
GET    /api/shifts                 List shifts (filter by date/employee)
GET    /api/employees/{id}/shifts  Get employee shifts
PUT    /api/shifts/{id}            Update shift
DELETE /api/shifts/{id}            Delete shift
```

#### Payroll
```
POST   /api/payroll/periods                Create payroll period
GET    /api/payroll/periods                List payroll periods
GET    /api/payroll/periods/{id}/summary   Get payroll summary
GET    /api/payroll/periods/{id}/export    Export payroll CSV
PUT    /api/payroll/periods/{id}           Update period status
```

#### Sync
```
POST   /api/sync/clover/employees  Sync employees from Clover
POST   /api/sync/clover/shifts     Sync shifts from Clover
GET    /api/sync/status            Get sync status
```

---

## TESTING CHECKLIST

### Phase 1: Foundation
- [ ] HR database starts successfully
- [ ] HR app container starts successfully
- [ ] Can access https://rm.swhgrp.com/hr/
- [ ] Positions CRUD works via API
- [ ] Employees CRUD works via API
- [ ] Positions page loads and displays data
- [ ] Employees page loads and displays data
- [ ] Can create position via UI
- [ ] Can create employee via UI

### Phase 2: Documents
- [ ] Can upload PDF document
- [ ] Can upload DOCX document
- [ ] Can upload JPG/PNG image
- [ ] File size validation works (>10MB rejected)
- [ ] Invalid file types rejected
- [ ] Can download document
- [ ] Can delete document
- [ ] Expiration date tracking works
- [ ] Document list shows in employee detail

### Phase 3: Time Tracking
- [ ] Can create manual shift
- [ ] Hours calculated correctly
- [ ] Overtime calculated correctly (>40 hours)
- [ ] Can view employee timesheet
- [ ] Weekly hours summary correct
- [ ] Can export timesheet to CSV
- [ ] Break duration deducted from total hours

### Phase 4: Clover Integration
- [ ] Clover employee sync works
- [ ] Employees matched by email
- [ ] clover_employee_id populated
- [ ] Clover shift sync works
- [ ] Shifts created in HR database
- [ ] Hours calculated from Clover timestamps
- [ ] Auto-sync runs every 15 minutes
- [ ] Manual sync button works

### Phase 5: Inventory Integration
- [ ] Can create employee with inventory user
- [ ] User created in inventory system
- [ ] inventory_user_id populated
- [ ] Employee termination syncs to inventory
- [ ] User deactivated in inventory
- [ ] Sync can be disabled via settings

### Phase 6: Payroll
- [ ] Can create payroll period
- [ ] Payroll summary calculates hours correctly
- [ ] Regular hours capped at 40
- [ ] Overtime hours calculated (>40)
- [ ] Overtime rate 1.5x correct
- [ ] CSV export formatted correctly
- [ ] Can import CSV into ADP/Paychex

### Integration Testing
- [ ] Full workflow: Create employee → Clover sync → Shifts sync → Payroll
- [ ] Full workflow: Create employee with user → Upload docs → Terminate → User deactivated
- [ ] All services start via docker compose
- [ ] Backup script backs up HR database
- [ ] Health check monitors HR service
- [ ] SSL works for /hr/ routes

---

## SUCCESS METRICS

### Phase 1 Complete
- ✅ HR service accessible at https://rm.swhgrp.com/hr/
- ✅ Can manage 50+ employees
- ✅ Can manage 10+ positions
- ✅ UI functional and styled consistently

### Phase 2 Complete
- ✅ 100+ documents uploaded
- ✅ All employee documents organized
- ✅ Expiration tracking working
- ✅ No missing required documents

### Phase 3 Complete
- ✅ Manual time entry working
- ✅ Can view timesheets for all employees
- ✅ Hours calculation accurate

### Phase 4 Complete
- ✅ Clover employees synced
- ✅ Clover shifts synced
- ✅ Auto-sync running every 15 minutes
- ✅ Zero manual time entry needed

### Phase 5 Complete
- ✅ All employees have inventory user accounts
- ✅ Terminations sync automatically
- ✅ Single source of truth for employee data

### Phase 6 Complete
- ✅ Payroll export works
- ✅ Successfully import into payroll provider
- ✅ Labor costs tracked accurately
- ✅ Zero payroll errors

### Final Success
- ✅ System in production use
- ✅ All documentation complete
- ✅ Team trained on HR system
- ✅ Automated backups running
- ✅ Monitoring alerts configured

---

## NOTES & DECISIONS

### Why This Sequence?
1. **Foundation First**: Can't build integrations without basic functionality
2. **Manual Before Auto**: Manual time entry validates the data model before adding Clover complexity
3. **Test Each Phase**: Each phase is fully testable before moving to next
4. **Integrations Last**: Core HR features work standalone, integrations are enhancements

### Key Technical Decisions
1. **No Hard Foreign Keys**: API references only (inventory_user_id, location_id) to maintain microservices independence
2. **One-Way Clover Sync**: Pull from Clover, don't push back (avoid sync conflicts)
3. **Optional Inventory Sync**: Can be disabled if using inventory standalone
4. **Separate Databases**: Each service owns its data (hr_db, inventory_db, accounting_db)

### Future Enhancements
- Training records and certifications
- Performance reviews
- PTO/vacation tracking
- Employee self-service portal
- Mobile app for clock in/out
- Biometric time clock integration
- Advanced scheduling (shift templates, swap requests)
- Benefits tracking
- Onboarding checklists

---

**Document Version**: 1.0
**Last Updated**: October 15, 2025
**Next Review**: After Phase 1 completion
