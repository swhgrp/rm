# Portal System - Restaurant Management

## Overview

The Portal is the central authentication and navigation hub for the SW Hospitality Group Restaurant Management System. It provides single sign-on (SSO) authentication and permission-based access control for all microservices.

## Status: 99% Production Ready ✅ (Updated Dec 8, 2025)

## Purpose

- Centralized user authentication
- JWT-based session management
- Permission-based access control
- System navigation dashboard
- Admin user management

## Technology Stack

- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL 15 (shared with HR system)
- **Authentication:** JWT tokens (jose library)
- **Password Hashing:** bcrypt
- **Templates:** Jinja2
- **Session Storage:** HTTP-only secure cookies

## Features

### ✅ Implemented (95%)

**Authentication & Authorization:**
- [x] User login/logout
- [x] JWT token generation
- [x] Session management with secure cookies
- [x] Permission-based system access
- [x] Password verification with bcrypt
- [x] Token expiration (configurable)
- [x] HTTPS enforcement

**User Management:**
- [x] Admin dashboard for user management
- [x] View all users
- [x] Edit user permissions per system
- [x] Enable/disable user accounts
- [x] Role assignment (accounting_role_id)
- [x] **User profile management** (update full name and email)
- [x] **Password change system** with cross-system synchronization
- [x] Password complexity enforcement (8+ characters minimum)

**System Integration:**
- [x] SSO token generation for microservices
- [x] 5-minute short-lived system tokens
- [x] Permission validation per system
- [x] Cross-system authentication
- [x] **Session auto-refresh** (extends session when <10 min remaining)
- [x] **Password sync to Inventory and Accounting systems**

**UI:**
- [x] Login page
- [x] Dashboard with system tiles
- [x] Settings/admin page
- [x] Dark theme matching other systems
- [x] Mobile-responsive design

**System Monitoring:** ✅ NEW
- [x] **Real-time monitoring dashboard** (admin-only)
- [x] 7 microservices health status
- [x] Database health and connection counts
- [x] SSL certificate expiration tracking
- [x] Backup status monitoring
- [x] Recent alerts and error logs
- [x] Auto-refresh every 30 seconds

### ❌ Missing (5%)

- [ ] Password reset via email flow
- [ ] User self-service registration
- [ ] Two-factor authentication (2FA)
- [ ] Failed login attempt tracking

## Architecture

### Authentication Flow

```
1. User visits https://rm.swhgrp.com/portal/login
2. User enters username/password
3. Portal validates against HR database
4. Portal creates JWT token with user info
5. Token stored in secure HTTP-only cookie
6. User redirected to dashboard

When accessing a system:
1. User clicks system tile (e.g., "Inventory")
2. Portal generates short-lived (5 min) system token
3. User redirected to system with token
4. System validates token and creates own session
5. User accesses system without re-login
```

### Database Schema

Uses HR system database, table: `users`

**User Model:**
```python
class User:
    id: int (primary key)
    username: str (unique)
    email: str (unique)
    hashed_password: str
    full_name: str
    is_active: bool
    is_admin: bool

    # System access permissions
    can_access_portal: bool
    can_access_inventory: bool
    can_access_accounting: bool
    can_access_hr: bool
    can_access_events: bool
    can_access_integration_hub: bool
    can_access_files: bool
    # System-specific roles
    accounting_role_id: int (nullable)
```

## API Endpoints

### Public Endpoints

**GET /portal/**
- Dashboard (requires authentication)
- Shows accessible systems based on user permissions
- Redirects to login if not authenticated

**GET /portal/login**
- Login page
- Form with username/password

**POST /portal/login**
- Process login
- Validates credentials
- Creates session cookie
- Redirects to dashboard

**GET /portal/logout**
- Logout user
- Clears session cookie
- Redirects to login

### Protected Endpoints (Require Admin)

**GET /portal/settings**
- User management page
- List all users
- Admin only

**POST /portal/api/users/{user_id}/permissions**
- Update user permissions
- Admin only
- Request body: Form data with permission checkboxes

### System Integration

**GET /portal/api/generate-token/{system}**
- Generate short-lived (5 min) token for system access
- Requires authentication
- Validates user has permission for system
- Returns: `{"token": "eyJ..."}`

**Supported systems:**
- `inventory`
- `accounting`
- `hr`
- `events`
- `hub` (Integration Hub)
- `files`

**GET /portal/health**
- Health check endpoint
- Returns: `{"status": "healthy", "service": "portal"}`

### User Profile & Password Management

**GET /profile**
- User profile page
- Shows current user information
- Allows editing full name and email

**POST /api/profile/update**
- Update user profile
- Request body: `{"full_name": "...", "email": "..."}`
- Validates email uniqueness
- Returns: User object

**GET /change-password**
- Password change page
- Form for current and new password

**POST /api/change-password**
- Change user password
- Request body: `{"current_password": "...", "new_password": "..."}`
- Enforces 8+ character minimum
- **Automatically syncs password to Inventory and Accounting systems**
- Returns: Sync status for each system

### System Monitoring

**GET /monitoring**
- **Real-time system monitoring dashboard**
- Shows 7 microservices health status
- Database connection counts and health
- SSL certificate expiration
- Backup status per database
- Recent alerts and error logs
- Auto-refresh every 30 seconds
- **Admin only**

**GET /api/monitoring/status**
- JSON status data for monitoring
- Calls `/opt/restaurant-system/scripts/dashboard-status.sh`
- Returns complete system health metrics
- Cache-busting headers included
- Admin only

### Debug Endpoints

**GET /debug**
- User attribute debugging
- Returns all current user attributes as JSON
- **WARNING:** No authentication required - consider removing in production

## Configuration

### Environment Variables (.env)

```bash
# Database (shares HR database)
HR_DATABASE_URL=postgresql://hr_user:password@hr-db:5432/hr_db

# JWT Authentication
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
SESSION_COOKIE_NAME=portal_session
SESSION_EXPIRE_MINUTES=480

# System URLs (for SSO)
INVENTORY_API_URL=http://inventory-app:8000
ACCOUNTING_API_URL=http://accounting-app:8000
HR_API_URL=http://hr-app:8000
INTEGRATION_HUB_URL=http://integration-hub:8000
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15
- HR system database configured

### Quick Start

1. **Set up environment variables:**
```bash
cd /opt/restaurant-system/portal
cp .env.example .env
# Edit .env with your configuration
```

2. **Build and start:**
```bash
docker compose up -d portal-app
```

3. **Create first admin user:**
```bash
# Connect to HR database and insert user
docker compose exec hr-db psql -U hr_user -d hr_db

INSERT INTO users (username, email, hashed_password, full_name, is_active, is_admin, can_access_portal)
VALUES ('admin', 'admin@example.com', '$2b$12$...', 'Admin User', true, true, true);
```

4. **Access portal:**
```
https://rm.swhgrp.com/portal/
```

## Usage

### User Login

1. Navigate to https://rm.swhgrp.com/portal/
2. Enter username and password
3. Click "Login"
4. Dashboard shows accessible systems

### Admin - Managing Users

1. Login as admin user
2. Click "Settings" in navigation
3. View list of all users
4. Click "Edit Permissions" on any user
5. Check/uncheck system access permissions
6. Save changes

### Accessing a System

1. From dashboard, click any system tile
2. Portal generates temporary token
3. Automatic redirect to system
4. No need to login again

## File Structure

```
portal/
├── src/
│   └── portal/
│       ├── __init__.py
│       ├── main.py           # FastAPI application, routes, auth logic
│       └── config.py         # Configuration and environment variables
├── templates/
│   ├── login.html           # Login page
│   ├── home.html            # Dashboard with system tiles
│   ├── settings.html        # Admin user management
│   └── base.html            # (if exists) Base template
├── static/
│   ├── css/                 # Stylesheets
│   └── images/              # Logo, icons
├── Dockerfile               # Container definition
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not in git)
└── README.md               # This file
```

## Dependencies

See `requirements.txt`:
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-jose[cryptography]==3.3.0
bcrypt==4.1.1
python-multipart==0.0.6
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
jinja2==3.1.2
```

## Security Considerations

**Implemented:**
- ✅ HTTPS only (enforced by nginx)
- ✅ HTTP-only secure cookies
- ✅ Bcrypt password hashing
- ✅ JWT token expiration
- ✅ CORS configuration
- ✅ SQL injection prevention (SQLAlchemy ORM)
- ✅ Password complexity enforcement (8+ characters)
- ✅ Cross-system password synchronization

**Security Warnings:** ⚠️

1. **Debug Endpoint (Line 283)**
   - `/debug` endpoint has no authentication
   - Returns all user attributes as JSON
   - **ISSUE:** Potential information disclosure
   - **RECOMMENDATION:** Remove or add authentication

2. **SSL Verification Disabled (Lines 731-734)**
   - SSL verification disabled for internal Docker requests
   - Acceptable for Docker internal network
   - Documented here for transparency

3. **Missing Rate Limiting**
   - No rate limiting on login endpoint
   - **RECOMMENDATION:** Add rate limiting

4. **Missing Audit Logging**
   - Profile changes not logged
   - Password changes not fully audited
   - **RECOMMENDATION:** Add comprehensive audit trail

**Recommended Additions:**
- [ ] Rate limiting on all sensitive endpoints
- [ ] Failed login attempt tracking
- [ ] Account lockout after X failed attempts
- [ ] Two-factor authentication (TOTP)
- [ ] Session token rotation
- [ ] IP-based restrictions (optional)
- [ ] Comprehensive audit logging for all sensitive operations

## Integration with Other Systems

Each microservice validates Portal-generated tokens:

```python
# Example: In another system
from jose import jwt

def validate_portal_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

Token payload includes:
```json
{
  "sub": "username",
  "email": "user@example.com",
  "full_name": "User Name",
  "user_id": 123,
  "is_admin": false,
  "system": "inventory",
  "accounting_role_id": 5,
  "exp": 1234567890
}
```

## Troubleshooting

### Issue: Can't login
**Solution:**
- Check database connection
- Verify user exists in HR database
- Confirm password hash is correct
- Check `is_active` and `can_access_portal` flags

### Issue: Redirect loops
**Solution:**
- Clear browser cookies
- Check nginx proxy configuration
- Verify `root_path="/portal"` in FastAPI config

### Issue: Token validation fails in other systems
**Solution:**
- Ensure `SECRET_KEY` matches across all systems
- Check token expiration time
- Verify system name in token payload

## Development

### Running Locally

```bash
cd /opt/restaurant-system/portal

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export HR_DATABASE_URL="postgresql://..."
export SECRET_KEY="your-secret-key"

# Run development server
cd src
uvicorn portal.main:app --reload --port 8000
```

Access at: http://localhost:8000

### Adding New Systems

1. Add permission column to User model in HR database
2. Update Portal main.py to check permission
3. Add system tile to dashboard template
4. Add token generation logic

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/portal/health
```

### Logs
```bash
docker compose logs -f portal-app
```

## Future Enhancements

- [ ] OAuth2/SAML integration for enterprise SSO
- [ ] LDAP/Active Directory integration
- [ ] Password reset via email
- [ ] User self-registration with approval workflow
- [ ] Two-factor authentication (TOTP)
- [ ] Session management dashboard
- [ ] Audit log for authentication events
- [ ] API key management for external integrations
- [ ] Customizable session timeout per user
- [ ] Remember me functionality

## Support

For issues or questions:
- Check logs: `docker compose logs portal-app`
- Health check: https://rm.swhgrp.com/portal/health
- Contact: Development Team

## License

Proprietary - SW Hospitality Group Internal Use Only
