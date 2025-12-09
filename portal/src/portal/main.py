"""Portal main application"""
from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import os
import sys
import bcrypt
import httpx
import logging

# Add shared directory to path for Sentry config
# sys.path.insert(0, '/opt/restaurant-system/shared/python')
# from sentry_config import init_sentry

logger = logging.getLogger(__name__)

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

# Initialize Sentry error tracking
# init_sentry("portal")

# FastAPI app
app = FastAPI(
    title="Restaurant Management Portal",
    version="1.0.0",
    description="Central authentication portal for restaurant management systems",
    root_path="/portal"
)

# Middleware to refresh session tokens
@app.middleware("http")
async def session_refresh_middleware(request: Request, call_next):
    """Automatically refresh session tokens when they're close to expiring"""
    response = await call_next(request)

    # Only refresh on successful responses for authenticated users
    if response.status_code == 200 and hasattr(request.state, "user"):
        user = request.state.user
        token_exp = getattr(request.state, "token_exp", None)

        if token_exp and user:
            # Check if token expires in less than 10 minutes
            time_until_expiry = token_exp - datetime.now(timezone.utc).timestamp()

            if 0 < time_until_expiry < 600:  # Less than 10 minutes (600 seconds)
                # Issue a new token with fresh expiration (include full user data for SSO)
                new_token = create_access_token(data={
                    "sub": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "user_id": user.id,
                    "is_admin": user.is_admin
                })

                # Update the cookie with the new token
                response.set_cookie(
                    key=SESSION_COOKIE_NAME,
                    value=new_token,
                    httponly=True,
                    max_age=SESSION_EXPIRE_MINUTES * 60,
                    path="/",  # Make cookie available for all paths
                    samesite="lax",
                    secure=False  # Disable secure flag (nginx handles HTTPS termination)
                )

                logger.info(f"Session refreshed for user {user.username} (had {int(time_until_expiry)} seconds remaining)")

    return response

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
    can_access_events = Column(Boolean, default=True)
    can_access_files = Column(Boolean, default=True)
    can_access_websites = Column(Boolean, default=True)
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
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=SESSION_EXPIRE_MINUTES)
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
        exp = payload.get("exp")
        if username is None:
            return None

        # Store token expiration in request state for potential refresh
        request.state.token_exp = exp
        request.state.token = token
    except JWTError:
        return None

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None

    # Store user in request state for middleware
    request.state.user = user
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

    if user.can_access_events:
        systems.append({
            "name": "Events & Catering",
            "description": "Event planning, BEO management, and task tracking",
            "url": "/events/",
            "icon": "🎉",
            "system_key": "events"
        })

    if user.can_access_files:
        systems.append({
            "name": "Files",
            "description": "Document management and file storage",
            "url": "/files/",
            "icon": "📁",
            "system_key": "files"
        })

    # Websites - always show for admins
    logger.info(f"User {user.username}: is_admin={user.is_admin}, can_access_websites={getattr(user, 'can_access_websites', 'NOT_FOUND')}")
    if getattr(user, 'can_access_websites', False) or user.is_admin:
        systems.append({
            "name": "Websites",
            "description": "Manage restaurant websites, menus, and content",
            "url": "/websites/",
            "icon": "🌐",
            "system_key": "websites"
        })
        logger.info(f"Added Websites to systems list for user {user.username}")

    # Admin-only: Monitoring Dashboard
    if user.is_admin:
        systems.append({
            "name": "System Monitoring",
            "description": "Real-time system health and monitoring dashboard",
            "url": "/portal/monitoring",
            "icon": "📊",
            "system_key": "monitoring"
        })

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "systems": systems
        }
    )


@app.get("/debug")
async def debug_user(request: Request, db: Session = Depends(get_db)):
    """Debug endpoint to check user attributes"""
    user = get_current_user(request, db)
    if not user:
        return {"error": "Not logged in"}

    # Use getattr with defaults to safely access all attributes
    result = {
        "username": getattr(user, 'username', 'MISSING'),
        "full_name": getattr(user, 'full_name', 'MISSING'),
        "is_admin": getattr(user, 'is_admin', 'MISSING'),
        "is_active": getattr(user, 'is_active', 'MISSING'),
        "can_access_files": getattr(user, 'can_access_files', 'MISSING'),
        "all_attrs": [attr for attr in dir(user) if not attr.startswith('_')]
    }

    # Also check what type the user object is
    result["user_type"] = str(type(user))
    result["user_dict"] = {k: str(v) for k, v in user.__dict__.items() if not k.startswith('_')}

    return result


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

    # Create access token with user information for SSO
    access_token = create_access_token(data={
        "sub": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "user_id": user.id,
        "is_admin": user.is_admin
    })

    # Check for redirect parameter from query string
    redirect_url = request.query_params.get("redirect", "/portal/")

    # Validate redirect URL (security: only allow internal paths)
    if not redirect_url.startswith("/"):
        redirect_url = "/portal/"

    # Redirect with session cookie
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=SESSION_EXPIRE_MINUTES * 60,
        path="/",  # Make cookie available for all paths
        domain=None,  # Let browser set domain automatically
        samesite="lax",
        secure=False  # Disable secure flag (nginx handles HTTPS termination)
    )

    return response


@app.get("/logout")
async def logout():
    """Logout user"""
    response = RedirectResponse(url="/portal/login", status_code=303)
    # Delete cookie with all possible combinations to ensure cleanup
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=False)
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

    # Prevent users from removing their own admin access
    form_data = await request.form()
    new_is_admin = form_data.get("is_admin") == "on"

    if user_id == current_user.id and not new_is_admin:
        return {"success": False, "message": "You cannot remove your own admin privileges"}

    # Track if admin status changed
    admin_changed = user.is_admin != new_is_admin

    # Update admin status
    user.is_admin = new_is_admin

    # Update permissions (only if not admin, admins get all access automatically)
    if not new_is_admin:
        user.can_access_portal = form_data.get("can_access_portal") == "on"
        user.can_access_inventory = form_data.get("can_access_inventory") == "on"
        user.can_access_accounting = form_data.get("can_access_accounting") == "on"
        user.can_access_integration_hub = form_data.get("can_access_integration_hub") == "on"
        user.can_access_hr = form_data.get("can_access_hr") == "on"
        user.can_access_events = form_data.get("can_access_events") == "on"
        user.can_access_files = form_data.get("can_access_files") == "on"
        if hasattr(user, 'can_access_websites'):
            user.can_access_websites = form_data.get("can_access_websites") == "on"
    else:
        # Admins get full access to everything
        user.can_access_portal = True
        user.can_access_inventory = True
        user.can_access_accounting = True
        user.can_access_integration_hub = True
        user.can_access_hr = True
        user.can_access_events = True
        user.can_access_files = True
        if hasattr(user, 'can_access_websites'):
            user.can_access_websites = True

    # Update accounting role if provided
    accounting_role = form_data.get("accounting_role_id")
    if accounting_role:
        user.accounting_role_id = int(accounting_role) if accounting_role else None

    db.commit()

    return {"success": True, "message": "Permissions updated", "admin_changed": admin_changed}


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
    elif system == "events" and not user.can_access_events:
        raise HTTPException(status_code=403, detail="No access to Events system")
    elif system == "files" and not user.can_access_files:
        raise HTTPException(status_code=403, detail="No access to Files system")
    elif system == "websites" and not getattr(user, 'can_access_websites', False) and not user.is_admin:
        raise HTTPException(status_code=403, detail="No access to Websites system")

    # Create SSO token for system authentication (30 minutes to match session timeout)
    token_data = {
        "sub": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "user_id": user.id,
        "is_admin": user.is_admin,
        "system": system,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
    }

    # Add accounting role if accessing accounting system
    if system == "accounting" and user.accounting_role_id:
        token_data["accounting_role_id"] = user.accounting_role_id

    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {"token": token}


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    """User profile page"""
    user = require_login(request, db)
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user
    })


class ProfileUpdateRequest(BaseModel):
    full_name: str
    email: str


@app.post("/api/profile/update")
async def update_profile(
    request: Request,
    profile_data: ProfileUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update user profile information"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Validate email format
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if profile_data.email and not re.match(email_pattern, profile_data.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Check if email is already taken by another user
    if profile_data.email != user.email:
        existing_user = db.query(User).filter(
            User.email == profile_data.email,
            User.id != user.id
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already in use by another user")

    # Update user information in HR database
    user.full_name = profile_data.full_name
    user.email = profile_data.email
    db.commit()

    logger.info(f"Profile updated for user {user.username}")

    return {"success": True, "message": "Profile updated successfully"}


@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, db: Session = Depends(get_db)):
    """Change password page"""
    user = require_login(request, db)
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "user": user
    })


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


@app.post("/api/change-password")
async def change_password(
    request: Request,
    password_data: PasswordChangeRequest,
    db: Session = Depends(get_db)
):
    """Change password and sync across all systems"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Verify current password
    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Validate new password
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(password_data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Hash new password
    new_hashed = bcrypt.hashpw(
        password_data.new_password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    # 1. Update HR database (master)
    user.hashed_password = new_hashed
    db.commit()

    logger.info(f"Password changed for user {user.username}")

    # 2. Sync to other systems
    sync_results = await sync_password_to_systems(
        username=user.username,
        hashed_password=new_hashed
    )

    return {
        "message": "Password changed successfully",
        "synced_systems": sync_results
    }


async def sync_password_to_systems(username: str, hashed_password: str):
    """Sync password to all microservices"""
    systems = [
        {"name": "Inventory", "url": f"{INVENTORY_API_URL}/api/users/sync-password"},
        {"name": "Accounting", "url": f"{ACCOUNTING_API_URL}/api/users/sync-password"},
        # Note: Events system uses SSO-only authentication (no passwords stored)
        # Users authenticate via Portal SSO tokens, so no password sync needed
    ]

    results = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        for system in systems:
            try:
                response = await client.post(
                    system["url"],
                    json={
                        "username": username,
                        "hashed_password": hashed_password
                    },
                    headers={"X-Portal-Auth": SECRET_KEY}
                )
                if response.status_code == 200:
                    data = response.json()
                    results[system["name"]] = {
                        "status": "success",
                        "user_exists": data.get("user_exists", False)
                    }
                    logger.info(f"Password synced to {system['name']} for user {username}")
                else:
                    results[system["name"]] = {
                        "status": "failed",
                        "error": f"HTTP {response.status_code}"
                    }
                    logger.warning(f"Failed to sync password to {system['name']}: HTTP {response.status_code}")
            except Exception as e:
                results[system["name"]] = {
                    "status": "error",
                    "error": str(e)
                }
                logger.error(f"Error syncing password to {system['name']}: {str(e)}")

    return results


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "portal"}


# Monitoring Dashboard Routes
@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    """Display monitoring dashboard"""
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return templates.TemplateResponse("monitoring.html", {"request": request})


@app.get("/api/monitoring/status")
async def monitoring_status(current_user: User = Depends(get_current_user)):
    """Return monitoring status as JSON"""
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    import subprocess
    import tempfile
    import os
    import json

    try:
        # Use a temporary file to capture full output (bypasses subprocess buffer limits)
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as f:
            output_file = f.name

        logger.info(f"Running monitoring script, output to: {output_file}")

        # Run the dashboard status script with output redirected to file
        with open(output_file, 'w') as f:
            result = subprocess.run(
                ["/opt/restaurant-system/scripts/dashboard-status.sh"],
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

        logger.info(f"Monitoring script completed with return code: {result.returncode}")

        if result.returncode == 0:
            # Read the complete output from file
            with open(output_file, 'r') as f:
                full_output = f.read()

            # Clean up temp file
            os.unlink(output_file)

            logger.info(f"Read {len(full_output)} bytes from monitoring script output file")

            # Parse JSON output (skip the Content-Type header)
            # The script outputs "Content-Type: application/json\n\n{json...}"
            lines = full_output.split('\n')
            # Find the first line that starts with '{'
            json_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('{'):
                    json_start = i
                    break

            json_output = '\n'.join(lines[json_start:])
            logger.info(f"Extracted JSON: {len(json_output)} chars, {len(lines)} total lines, JSON starts at line {json_start}")

            try:
                parsed_data = json.loads(json_output)
                logger.info(f"Successfully parsed JSON with {len(parsed_data)} top-level keys")
                # Return with cache-busting headers
                return JSONResponse(
                    content=parsed_data,
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error at line {e.lineno}, col {e.colno}: {e.msg}")
                logger.error(f"Problematic output (first 500 chars): {json_output[:500]}")
                logger.error(f"Output around error (lines {max(1, e.lineno-2)}-{e.lineno+2}): {lines[json_start + max(0, e.lineno-3):json_start + e.lineno+2]}")
                raise HTTPException(status_code=500, detail=f"Invalid JSON from monitoring script: {e.msg}")
        else:
            # Clean up temp file on error
            if os.path.exists(output_file):
                os.unlink(output_file)
            raise HTTPException(status_code=500, detail=f"Script failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        # Clean up temp file on timeout
        if 'output_file' in locals() and os.path.exists(output_file):
            os.unlink(output_file)
        raise HTTPException(status_code=504, detail="Monitoring status check timed out")
    except json.JSONDecodeError:
        # Already handled above
        raise
    except Exception as e:
        # Clean up temp file on any error
        if 'output_file' in locals() and os.path.exists(output_file):
            os.unlink(output_file)
        logger.error(f"Monitoring status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "portal"}
