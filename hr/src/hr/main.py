"""
Main FastAPI application for HR Management System
"""

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from hr.api.api_v1.endpoints import positions, employees, documents, roles, locations, departments, audit
from hr.api.api_v1.endpoints import settings
from hr.api.auth_helpers import require_login, require_admin
from hr.api import auth, users
from hr.db.database import get_db
from hr.models.employee import Employee
from hr.models.position import Position
from hr.models.user import User
import os

app = FastAPI(
    title="SW HR Management",
    description="Human Resources Management System",
    version="1.0.0",
    root_path="/hr"
)

# Include API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(locations.router)
app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
app.include_router(employees.router, prefix="/api/employees", tags=["employees"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(departments.router, prefix="/api/departments", tags=["departments"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])

# Setup templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Mount static files (will be used later)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Custom exception handler for authentication redirects
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions - redirect 401 to Portal login for HTML requests"""
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # Check if this is an HTML request (not API)
        accept = request.headers.get("accept", "")
        if "text/html" in accept or request.url.path.startswith("/hr/"):
            # Redirect to Portal login instead of local login
            return RedirectResponse(url="/portal/login?redirect=/hr/", status_code=302)
    # For API requests or other errors, return JSON response
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login page"""
    # Check if already logged in
    from hr.api.auth import get_current_user
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request})

    return user


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    """HR Dashboard (protected)"""
    # Get statistics
    active_employees = db.query(Employee).filter(Employee.employment_status == "Active").count()
    total_positions = db.query(Position).filter(Position.is_active == True).count()
    terminated = db.query(Employee).filter(Employee.employment_status == "Terminated").count()

    # New employees this month
    first_of_month = datetime.now().replace(day=1).date()
    new_this_month = db.query(Employee).filter(Employee.hire_date >= first_of_month).count()

    # Recent employees (last 10)
    recent_employees = db.query(Employee).order_by(Employee.created_at.desc()).limit(10).all()

    stats = {
        "active_employees": active_employees,
        "total_positions": total_positions,
        "new_this_month": new_this_month,
        "terminated": terminated
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "recent_employees": recent_employees,
        "current_user": user
    })


@app.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request, user: User = Depends(require_login)):
    """Positions management page (protected)"""
    return templates.TemplateResponse("positions.html", {"request": request, "current_user": user})


@app.get("/employees", response_class=HTMLResponse)
async def employees_page(request: Request, user: User = Depends(require_login)):
    """Employees list page (protected)"""
    return templates.TemplateResponse("employees.html", {"request": request, "current_user": user})


@app.get("/employees/new", response_class=HTMLResponse)
async def new_employee_page(request: Request, user: User = Depends(require_login)):
    """New employee form page (protected)"""
    return templates.TemplateResponse("employee_form.html", {"request": request, "current_user": user, "employee": None})


@app.get("/employees/{employee_id}/edit", response_class=HTMLResponse)
async def edit_employee_page(request: Request, employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    """Edit employee form page (protected)"""
    from hr.models.employee import Employee as EmployeeModel

    employee = db.query(EmployeeModel).filter(EmployeeModel.id == employee_id).first()
    if not employee:
        return RedirectResponse(url="/hr/employees", status_code=302)

    return templates.TemplateResponse("employee_form.html", {
        "request": request,
        "current_user": user,
        "employee": employee
    })


@app.get("/employees/{employee_id}", response_class=HTMLResponse)
async def employee_detail_page(request: Request, employee_id: int, user: User = Depends(require_login)):
    """Employee detail page (protected)"""
    return templates.TemplateResponse("employee_detail.html", {"request": request, "current_user": user})


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request, user: User = Depends(require_login)):
    """Documents management page (protected)"""
    from hr.schemas.document import DOCUMENT_TYPES
    return templates.TemplateResponse("documents.html", {
        "request": request,
        "current_user": user,
        "document_types": DOCUMENT_TYPES
    })


@app.get("/locations", response_class=HTMLResponse)
async def locations_page(request: Request, user: User = Depends(require_login)):
    """Locations management page (protected)"""
    return templates.TemplateResponse("locations.html", {"request": request, "current_user": user})


@app.get("/departments", response_class=HTMLResponse)
async def departments_page(request: Request, user: User = Depends(require_login)):
    """Departments management page (protected)"""
    return templates.TemplateResponse("departments.html", {"request": request, "current_user": user})


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    """User management page (admin only)"""
    from hr.api.auth import require_admin
    try:
        require_admin(user)
    except:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("users.html", {"request": request, "current_user": user})


@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, user: User = Depends(require_login)):
    """Audit log page (protected)"""
    return templates.TemplateResponse("audit.html", {"request": request, "current_user": user})


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: User = Depends(require_login)):
    """User profile page (protected)"""
    return templates.TemplateResponse("profile.html", {"request": request, "current_user": user})


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "hr-management"}


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "service": "SW HR Management API",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: User = Depends(require_admin)):
    """System Settings page (protected)"""
    return templates.TemplateResponse("settings.html", {"request": request})

