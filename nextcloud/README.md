# Nextcloud Integration Service

A microservice that integrates Nextcloud file management and calendar functionality into the SW Restaurant Management System.

## Overview

The Nextcloud Integration Service provides seamless access to Nextcloud files and calendars through a web interface integrated with the restaurant management portal. Users can browse files, upload/download documents, and manage calendar events without leaving the restaurant system.

## Technology Stack

- **Backend**: FastAPI 0.104.1 (Python 3.11)
- **Database**: PostgreSQL 15 (for user credential storage)
- **ORM**: SQLAlchemy 2.0.23
- **Migrations**: Alembic 1.12.1
- **Nextcloud Clients**:
  - WebDAV3 3.14.6 (file operations)
  - CalDAV 1.3.9 (calendar operations)
- **Authentication**: JWT + Portal SSO
- **Frontend**: Jinja2 templates, Bootstrap 5 (dark theme)
- **Containerization**: Docker

## Core Features

### Files Management
- **Browse Files**: Navigate Nextcloud directory structure
- **Upload Files**: Drag-and-drop or browse to upload
- **Download Files**: Download files with streaming support
- **Create Folders**: Organize files in directories
- **Delete**: Remove files and folders
- **Move/Rename**: Reorganize files

### Calendar Management
- **View Calendars**: List all user calendars
- **Browse Events**: View events by month/week/day
- **Create Events**: Add new calendar events (all-day or timed)
- **Edit Events**: Update existing events
- **Delete Events**: Remove calendar events
- **Today's Events**: Quick view of today's schedule

### Security
- **Per-User Credentials**: Each user uses their own Nextcloud account
- **Encrypted Storage**: Nextcloud passwords encrypted at rest using Fernet
- **Portal SSO**: Integrated with central authentication portal
- **JWT Tokens**: Secure API access with Bearer tokens

## Database Schema

### Users Table (Extended from HR Database)

The service adds the following columns to the existing `users` table:

| Column | Type | Description |
|--------|------|-------------|
| `nextcloud_username` | String | User's Nextcloud username |
| `nextcloud_encrypted_password` | String | Encrypted Nextcloud password |
| `can_access_nextcloud` | Boolean | Permission flag for Nextcloud access |

## API Structure

### Authentication Endpoints (`/api/v1/auth`)
- `GET /me` - Get current user info and Nextcloud setup status
- `POST /setup` - Initial Nextcloud credentials configuration
- `PUT /credentials` - Update Nextcloud credentials
- `DELETE /credentials` - Remove Nextcloud credentials

### Files Endpoints (`/api/v1/files`)
- `GET /list?path={path}` - List files in directory
- `GET /download?path={path}` - Download file
- `POST /upload?path={path}` - Upload file
- `POST /mkdir` - Create folder
- `DELETE /delete` - Delete file/folder
- `POST /move` - Move or rename file/folder

### Calendar Endpoints (`/api/v1/calendar`)
- `GET /calendars` - List all calendars
- `GET /events?start_date={date}&end_date={date}` - List events in date range
- `GET /events/today` - Get today's events
- `POST /events?calendar_url={url}` - Create event
- `PUT /events/{uid}?calendar_url={url}` - Update event
- `DELETE /events/{uid}?calendar_url={url}` - Delete event

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/` | Service landing page |
| `/setup` | Nextcloud credentials setup page |
| `/files` | File browser interface |
| `/calendar` | Calendar view interface |

## Deployment Architecture

```
┌─────────────────────────────────────────────────┐
│  Restaurant System (Docker Compose)             │
│                                                  │
│  ┌──────────────┐       ┌──────────────┐       │
│  │   Portal     │──────▶│  Nextcloud   │       │
│  │   (Auth)     │  JWT  │   Service    │       │
│  └──────────────┘       └──────┬───────┘       │
│                                 │                │
│  ┌──────────────┐       ┌──────┴───────┐       │
│  │  Nextcloud   │       │  HR Database │       │
│  │  PostgreSQL  │       │  (Users)     │       │
│  └──────────────┘       └──────────────┘       │
│         │                                        │
└─────────┼────────────────────────────────────────┘
          │
          │ HTTPS
          ▼
┌─────────────────────────┐
│  Nextcloud Server       │
│  cloud.swhgrp.com       │
│  (External)             │
│                         │
│  - WebDAV (Files)       │
│  - CalDAV (Calendar)    │
└─────────────────────────┘
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- Access to Nextcloud server (cloud.swhgrp.com)
- Users must have Nextcloud accounts

### Environment Variables

Create `.env` file:

```bash
# Application
APP_NAME=Nextcloud Integration
DEBUG=False

# Database (Nextcloud service database)
DATABASE_URL=postgresql://nextcloud_user:nextcloud_pass@nextcloud-db:5432/nextcloud_db

# HR Database (for user authentication)
HR_DATABASE_URL=postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db

# Security
SECRET_KEY=your-super-secret-key-change-in-production-galveston34
PORTAL_SECRET_KEY=your-super-secret-key-change-in-production-galveston34
ENCRYPTION_KEY=yX_axNoTYxskNPgHeaoSSi2gM1jXhXvsdwf9acQqKpM=

# Nextcloud Configuration
NEXTCLOUD_URL=https://cloud.swhgrp.com
NEXTCLOUD_WEBDAV_PATH=/remote.php/dav
NEXTCLOUD_CALDAV_PATH=/remote.php/dav

# CORS
ALLOWED_ORIGINS=https://restaurantsystem.swhgrp.com
```

### Build and Deploy

```bash
# Build container
docker-compose build nextcloud-app

# Run database migrations
docker-compose exec nextcloud-app alembic upgrade head

# Start service
docker-compose up -d nextcloud-app
```

### First-Time User Setup

1. User logs into Restaurant Portal
2. Navigate to Nextcloud service
3. Click "Setup Nextcloud Connection"
4. Enter Nextcloud username and password
5. Credentials are encrypted and stored
6. User can now access Files and Calendar

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables and secrets |
| `alembic.ini` | Database migration configuration |
| `Dockerfile` | Container build instructions |
| `requirements.txt` | Python dependencies |

## Security Features

### Credential Encryption
- Nextcloud passwords encrypted using Fernet (AES-128)
- Encryption key stored in environment variable
- Decryption happens only in memory during API calls

### Authentication Flow
1. User authenticates with Portal (JWT token issued)
2. Token passed to Nextcloud service via Bearer header or cookie
3. Service validates token and retrieves user
4. User's Nextcloud credentials decrypted for API calls
5. WebDAV/CalDAV client authenticates to Nextcloud server

### Permissions
- Portal SSO integration for authentication
- Per-user Nextcloud credentials (no shared accounts)
- `can_access_nextcloud` flag controls access
- Respects Nextcloud's own file/folder permissions

## Troubleshooting

### "Nextcloud credentials not configured"
**Cause**: User hasn't set up Nextcloud connection yet
**Solution**: Navigate to `/setup` page and enter credentials

### "Failed to connect to Nextcloud"
**Cause**: Network issue or invalid credentials
**Solution**:
- Verify Nextcloud URL is accessible
- Check user's Nextcloud username/password
- Update credentials via `/setup` page

### "Permission denied" on files
**Cause**: Nextcloud permissions don't allow access
**Solution**: Check file/folder permissions in Nextcloud admin

### Database connection errors
**Cause**: Database not accessible or wrong credentials
**Solution**: Verify `DATABASE_URL` in `.env` file

## Development

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://...
export NEXTCLOUD_URL=https://cloud.swhgrp.com

# Run with uvicorn
uvicorn nextcloud.main:app --reload --host 0.0.0.0 --port 8000
```

### Create Migration

```bash
# Auto-generate migration from model changes
docker-compose exec nextcloud-app alembic revision --autogenerate -m "Description"

# Apply migration
docker-compose exec nextcloud-app alembic upgrade head
```

### API Documentation

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## Planned Features

- [ ] File search functionality
- [ ] File previews (images, PDFs)
- [ ] Bulk file operations
- [ ] Recurring calendar events
- [ ] Calendar sharing
- [ ] Talk integration (chat)
- [ ] Activity feed
- [ ] Collaborative editing

## Support

For issues or questions:
- Check logs: `docker-compose logs nextcloud-app`
- Review Nextcloud server logs
- Verify network connectivity to cloud.swhgrp.com

## Version History

### v1.0.0 (2025-10-28)
- Initial release
- Files browsing and management
- Calendar viewing and event CRUD
- Per-user credential encryption
- Portal SSO integration
