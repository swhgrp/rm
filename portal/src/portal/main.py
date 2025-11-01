"""Portal main application"""
from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from datetime import datetime, timedelta
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
            time_until_expiry = token_exp - datetime.utcnow().timestamp()

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
    can_access_mail = Column(Boolean, default=True)
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

    if user.can_access_mail:
        systems.append({
            "name": "Mail",
            "description": "Email and webmail access",
            "url": "https://mail.swhgrp.com/SOGo/",
            "icon": "📧",
            "system_key": "mail"
        })

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
        user.can_access_mail = form_data.get("can_access_mail") == "on"
    else:
        # Admins get full access to everything
        user.can_access_portal = True
        user.can_access_inventory = True
        user.can_access_accounting = True
        user.can_access_integration_hub = True
        user.can_access_hr = True
        user.can_access_events = True
        user.can_access_files = True
        user.can_access_mail = True

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
    elif system == "mail" and not user.can_access_mail:
        raise HTTPException(status_code=403, detail="No access to Mail system")

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


@app.get("/api/auth/verify")
async def verify_auth(request: Request, db: Session = Depends(get_db)):
    """Verify portal session for nginx auth_request (Mail module)"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Check mail access permission
    if not user.can_access_mail:
        raise HTTPException(status_code=403, detail="No access to Mail system")

    # Return user email for SOGo SSO
    response = JSONResponse({"authenticated": True, "username": user.username})
    # Provide email for SOGo remote user header
    email = user.email if user.email else f"{user.username}@swhgrp.com"
    response.headers["X-Mail-User"] = email
    return response


@app.get("/api/auth/verify-admin")
async def verify_admin(request: Request, db: Session = Depends(get_db)):
    """Verify portal admin session (Mail admin interface)"""
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"authenticated": True, "username": user.username}


@app.post("/api/admin/mail/provision-users")
async def provision_mail_users(
    request: Request,
    db: Session = Depends(get_db)
):
    """Provision mailboxes for all HR users (admin only)"""
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from portal.config import MAILCOW_API_URL, MAILCOW_API_KEY, MAIL_DOMAIN
    import ssl

    if not MAILCOW_API_KEY:
        raise HTTPException(status_code=500, detail="Mailcow API key not configured")

    # Get all active users from HR database
    users = db.query(User).filter(User.is_active == True).all()

    results = {
        "total_users": len(users),
        "provisioned": [],
        "already_exists": [],
        "failed": []
    }

    # Create SSL context that doesn't verify (for internal docker communication)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        for usr in users:
            email = usr.email if usr.email else f"{usr.username}@{MAIL_DOMAIN}"
            local_part = email.split('@')[0]

            # Check if mailbox already exists
            try:
                check_response = await client.get(
                    f"{MAILCOW_API_URL}/api/v1/get/mailbox/{email}",
                    headers={"X-API-Key": MAILCOW_API_KEY}
                )

                if check_response.status_code == 200:
                    results["already_exists"].append({
                        "username": usr.username,
                        "email": email
                    })
                    continue
            except Exception as e:
                logger.warning(f"Error checking mailbox {email}: {str(e)}")

            # Create mailbox
            try:
                create_response = await client.post(
                    f"{MAILCOW_API_URL}/api/v1/add/mailbox",
                    headers={"X-API-Key": MAILCOW_API_KEY},
                    json={
                        "local_part": local_part,
                        "domain": MAIL_DOMAIN,
                        "name": usr.full_name or usr.username,
                        "quota": 5120,  # 5GB quota
                        "password": usr.hashed_password[:16],  # Use part of hash as temp password
                        "password2": usr.hashed_password[:16],
                        "active": "1"
                    }
                )

                if create_response.status_code in [200, 201]:
                    response_data = create_response.json()
                    if isinstance(response_data, list) and response_data:
                        if response_data[0].get("type") == "success":
                            results["provisioned"].append({
                                "username": usr.username,
                                "email": email,
                                "full_name": usr.full_name
                            })
                            logger.info(f"Provisioned mailbox for {email}")
                        else:
                            results["failed"].append({
                                "username": usr.username,
                                "email": email,
                                "error": response_data[0].get("msg", "Unknown error")
                            })
                    else:
                        results["failed"].append({
                            "username": usr.username,
                            "email": email,
                            "error": f"Unexpected response format"
                        })
                else:
                    results["failed"].append({
                        "username": usr.username,
                        "email": email,
                        "error": f"HTTP {create_response.status_code}"
                    })

            except Exception as e:
                results["failed"].append({
                    "username": usr.username,
                    "email": email,
                    "error": str(e)
                })
                logger.error(f"Failed to provision {email}: {str(e)}")

    return results


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "portal"}


# Mail Gateway - Proxy to SOGo with SSO
@app.get("/mail-gateway/")
async def mail_gateway_root(request: Request, db: Session = Depends(get_db)):
    """Redirect root mail-gateway to SOGo"""
    # Debug logging
    print(f"===== MAIL GATEWAY DEBUG =====", flush=True)
    print(f"Cookies: {request.cookies}", flush=True)
    print(f"Cookie header: {request.headers.get('cookie', 'NONE')}", flush=True)
    print(f"All headers: {dict(request.headers)}", flush=True)
    print(f"==============================", flush=True)

    # Get current user
    user = get_current_user(request, db)
    if not user:
        print("No user found, redirecting to login", flush=True)
        return RedirectResponse(url="/portal/login", status_code=303)

    if not user.can_access_mail:
        raise HTTPException(status_code=403, detail="No access to Mail system")

    # Redirect to mail gateway with empty path (will proxy to SOGo root)
    return await mail_gateway("", request, db)


@app.api_route("/mail-gateway/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def mail_gateway(path: str, request: Request, db: Session = Depends(get_db)):
    """Proxy requests to SOGo with SSO authentication header"""
    import httpx

    # Get current user
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/portal/login", status_code=303)

    if not user.can_access_mail:
        raise HTTPException(status_code=403, detail="No access to Mail system")

    # Get user email
    email = user.email if user.email else f"{user.username}@swhgrp.com"

    # Prepare headers for SOGo
    headers = dict(request.headers)
    headers["X-Webobjects-Remote-User"] = email

    # Remove problematic headers
    headers.pop("content-length", None)
    headers.pop("transfer-encoding", None)
    headers.pop("host", None)  # Remove existing host header to avoid duplicates

    # Set SOGo host header
    headers["host"] = "rm.swhgrp.com"

    # Build SOGo URL - handle empty path
    if path:
        sogo_url = f"http://mail-sogo-mailcow-1:20000/SOGo/{path}"
    else:
        sogo_url = "http://mail-sogo-mailcow-1:20000/SOGo/"

    if request.url.query:
        sogo_url += f"?{request.url.query}"

    # Proxy the request
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=sogo_url,
                headers=headers,
                content=await request.body() if request.method in ["POST", "PUT", "PATCH"] else None,
                follow_redirects=False
            )

            print(f"SOGo response status: {response.status_code}", flush=True)
            print(f"SOGo response headers: {dict(response.headers)}", flush=True)

            # Handle redirects from SOGo
            if response.status_code in [301, 302, 303, 307, 308]:
                location = response.headers.get("location", "")
                print(f"SOGo redirect location: {location}", flush=True)

                # Rewrite SOGo paths to go through mail gateway
                # Use string replacement to handle all /SOGo/ paths correctly
                if location.startswith("http://") or location.startswith("https://"):
                    # Parse absolute URLs and rewrite the path
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(location)
                    if parsed.path.startswith("/SOGo/"):
                        # Replace /SOGo/ with /mail/ in the path
                        new_path = "/mail/" + parsed.path[6:]
                        # Return just the path (relative redirect)
                        location = new_path + ("?" + parsed.query if parsed.query else "")
                        print(f"Rewritten location (absolute → relative): {location}", flush=True)
                elif location.startswith("/SOGo/"):
                    # Relative URL - just replace /SOGo/ with /mail/
                    location = "/mail/" + location[6:]
                    print(f"Rewritten location (relative): {location}", flush=True)

                return RedirectResponse(url=location, status_code=response.status_code)

            # Return the response
            response_headers = dict(response.headers)
            # Remove headers that FastAPI will recalculate
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-length", None)

            # httpx automatically decompresses gzip content, but leaves the content-encoding header
            # Remove it to prevent browser from trying to decompress again
            if response.headers.get("content-encoding") == "gzip":
                response_headers.pop("content-encoding", None)
                print(f"Removed gzip encoding header (httpx already decompressed)", flush=True)

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get("content-type")
            )
        except Exception as e:
            logger.error(f"Mail gateway error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Mail gateway error: {str(e)}")


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

    try:
        # Run the dashboard status script
        result = subprocess.run(
            ["/opt/restaurant-system/scripts/dashboard-status.sh"],
            capture_output=True,
            text=True,
            timeout=45
        )

        if result.returncode == 0:
            # Parse JSON output (skip the Content-Type header)
            # The script outputs "Content-Type: application/json\n\n{json...}"
            lines = result.stdout.split('\n')
            # Find the first line that starts with '{'
            json_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('{'):
                    json_start = i
                    break

            json_output = '\n'.join(lines[json_start:])
            import json
            return JSONResponse(content=json.loads(json_output))
        else:
            raise HTTPException(status_code=500, detail=f"Script failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Monitoring status check timed out")
    except Exception as e:
        logger.error(f"Monitoring status error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "portal"}
