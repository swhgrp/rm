"""Portal main application"""
from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import bcrypt

from portal.config import (
    HR_DATABASE_URL,
    SECRET_KEY,
    ALGORITHM,
    SESSION_COOKIE_NAME,
    SESSION_EXPIRE_MINUTES,
    INVENTORY_API_URL,
    ACCOUNTING_API_URL,
    HR_API_URL,
    INTEGRATION_HUB_URL
)

# FastAPI app
app = FastAPI(
    title="Restaurant Management Portal",
    version="1.0.0",
    description="Central authentication portal for restaurant management systems",
    root_path="/portal"
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Database setup
engine = create_engine(HR_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# User model (mirroring HR database)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # Portal access permissions
    can_access_portal = Column(Boolean, default=True)
    can_access_inventory = Column(Boolean, default=True)
    can_access_accounting = Column(Boolean, default=True)
    can_access_integration_hub = Column(Boolean, default=True)
    can_access_hr = Column(Boolean, default=True)
    accounting_role_id = Column(Integer, nullable=True)


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Authentication helpers
def verify_password(plain_password, hashed_password):
    """Verify password against hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user from session cookie"""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None

    return user


def require_login(request: Request, db: Session = Depends(get_db)):
    """Require user to be logged in"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/portal/login"}
        )
    return user


# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page - show dashboard if logged in, otherwise redirect to login"""
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/portal/login", status_code=303)

    # Build list of accessible systems
    systems = []

    if user.can_access_inventory:
        systems.append({
            "name": "Inventory Management",
            "description": "Manage inventory, vendors, and stock counts",
            "url": "/inventory/",
            "icon": "📦",
            "system_key": "inventory"
        })

    if user.can_access_accounting:
        systems.append({
            "name": "Accounting System",
            "description": "Chart of accounts, journal entries, and financial reports",
            "url": "/accounting/",
            "icon": "💰",
            "system_key": "accounting"
        })

    if user.can_access_integration_hub:
        systems.append({
            "name": "Integration Hub",
            "description": "Vendor sync and system integrations",
            "url": "/hub/",
            "icon": "🔄",
            "system_key": "hub"
        })

    if user.can_access_hr:
        systems.append({
            "name": "HR System",
            "description": "Employee management and payroll",
            "url": "/hr/",
            "icon": "👥",
            "system_key": "hr"
        })

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "systems": systems
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process login"""
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password"
            },
            status_code=400
        )

    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Account is disabled"
            },
            status_code=400
        )

    if not user.can_access_portal:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "You do not have permission to access the portal"
            },
            status_code=403
        )

    # Create access token
    access_token = create_access_token(data={"sub": user.username})

    # Redirect to home with session cookie
    response = RedirectResponse(url="/portal/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=SESSION_EXPIRE_MINUTES * 60,
        samesite="lax"
    )

    return response


@app.get("/logout")
async def logout():
    """Logout user"""
    response = RedirectResponse(url="/portal/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    """User management settings page (admin only)"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get all users
    all_users = db.query(User).order_by(User.username).all()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "all_users": all_users
        }
    )


@app.post("/api/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_login),
    db: Session = Depends(get_db)
):
    """Update user permissions (admin only)"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Parse form data
    form_data = await request.form()

    # Update permissions
    user.can_access_portal = form_data.get("can_access_portal") == "on"
    user.can_access_inventory = form_data.get("can_access_inventory") == "on"
    user.can_access_accounting = form_data.get("can_access_accounting") == "on"
    user.can_access_integration_hub = form_data.get("can_access_integration_hub") == "on"
    user.can_access_hr = form_data.get("can_access_hr") == "on"

    # Update accounting role if provided
    accounting_role = form_data.get("accounting_role_id")
    if accounting_role:
        user.accounting_role_id = int(accounting_role) if accounting_role else None

    db.commit()

    return {"success": True, "message": "Permissions updated"}


@app.get("/api/generate-token/{system}")
async def generate_system_token(
    system: str,
    user: User = Depends(require_login)
):
    """Generate a single-use token for accessing a system"""
    # Validate system access
    if system == "inventory" and not user.can_access_inventory:
        raise HTTPException(status_code=403, detail="No access to Inventory system")
    elif system == "accounting" and not user.can_access_accounting:
        raise HTTPException(status_code=403, detail="No access to Accounting system")
    elif system == "hr" and not user.can_access_hr:
        raise HTTPException(status_code=403, detail="No access to HR system")
    elif system == "hub" and not user.can_access_integration_hub:
        raise HTTPException(status_code=403, detail="No access to Integration Hub")

    # Create a short-lived token (5 minutes) for system authentication
    token_data = {
        "sub": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "user_id": user.id,
        "is_admin": user.is_admin,
        "system": system,
        "exp": datetime.utcnow() + timedelta(minutes=5)
    }

    # Add accounting role if accessing accounting system
    if system == "accounting" and user.accounting_role_id:
        token_data["accounting_role_id"] = user.accounting_role_id

    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {"token": token}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "portal"}
