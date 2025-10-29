# Files Management System

Document management and file storage system for the SW Restaurant Management System.

## Overview

The Files system provides centralized file storage, folder organization, and document sharing capabilities. Built with FastAPI and using local file storage, it offers a secure and efficient way to manage restaurant documents, images, and files.

## Status: 100% Production Ready ✅

**LAST UPDATED:** 2025-10-29

The Files system is fully implemented and actively used in production.

## Technology Stack

- **Backend:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL 15 (HR database for users, local DB for file metadata)
- **ORM:** SQLAlchemy 2.0
- **Storage:** Local filesystem (`/app/storage`)
- **Authentication:** JWT via Portal SSO
- **Containerization:** Docker

## Core Features

### ✅ File Management
- **Upload Files:** Single and bulk file uploads with drag-and-drop
- **Download Files:** Direct download and streaming support
- **File Preview:** In-browser preview for PDFs, images, and Office documents
- **Delete Files:** Remove files with permission checking
- **Copy/Move Files:** Organize files across folders
- **Rename Files:** Update filenames in-place
- **File Metadata:** Track file size, type, owner, timestamps
- **MIME Type Detection:** Automatic content-type detection
- **Bulk Selection:** Multi-select files and folders for batch operations

### ✅ Folder Organization
- **Create Folders:** Hierarchical folder structure
- **Nested Folders:** Support for parent/child relationships with CASCADE delete
- **Folder Navigation:** Breadcrumb navigation and back button support
- **Dashboard View:** Home page with recent files and stats
- **My Files View:** Traditional folder browser with full hierarchy
- **Shared Views:** Dedicated pages for "Shared with Me" and "Shared by Me"

### ✅ Permissions & Security
- **User-Based Storage:** Each user gets isolated storage (`user_{id}/`)
- **Role-Based Access:** Admin, owner, and shared permissions
- **Permission Types:** Read, write, delete controls
- **JWT Authentication:** Secure API access via Portal tokens
- **Permission Inheritance:** Folder permissions apply to contents

### ✅ File Sharing
- **Internal Sharing:** Share files/folders with specific users
- **Public Share Links:** Generate shareable links with optional passwords
- **Username Autocomplete:** Search and select users by full name
- **Granular Permissions:** View, edit, upload, download, share, comment controls
- **Share Management:** View and manage all shares in one place
- **Share Tracking:** Visual badges show shared items
- **Expiration Support:** Set expiration dates for public links

### ✅ Document Preview & Conversion
- **PDF Preview:** Native browser preview for PDF documents
- **Image Preview:** Display images directly in browser
- **Office Document Conversion:** Convert Word/Excel/PowerPoint to PDF for preview
- **LibreOffice Integration:** Headless document conversion service
- **Supported Formats:** .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx, images

## Database Schema

### FileMetadata Table
Stores metadata about uploaded files.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `filename` | String | Original filename |
| `storage_path` | String | Relative path on filesystem |
| `size` | BigInteger | File size in bytes |
| `mime_type` | String | MIME type (e.g., image/jpeg) |
| `folder_id` | Integer | Parent folder (nullable) |
| `owner_id` | Integer | User who uploaded the file |
| `is_public` | Boolean | Public access flag |
| `created_at` | DateTime | Upload timestamp |
| `updated_at` | DateTime | Last modification timestamp |

### Folder Table
Organizes files into hierarchical folders.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `name` | String | Folder name |
| `path` | String | Full folder path |
| `parent_id` | Integer | Parent folder (nullable) |
| `owner_id` | Integer | Folder creator |
| `is_public` | Boolean | Public access flag |
| `created_at` | DateTime | Creation timestamp |

### InternalShare Table
Manages internal sharing between users.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `resource_type` | Enum | 'file' or 'folder' |
| `file_id` | Integer | Shared file (nullable) |
| `folder_id` | Integer | Shared folder (nullable) |
| `owner_id` | Integer | User who shared the resource |
| `shared_with_user_id` | Integer | User receiving access |
| `can_view` | Boolean | View permission |
| `can_edit` | Boolean | Edit permission |
| `can_upload` | Boolean | Upload permission (folders) |
| `can_download` | Boolean | Download permission |
| `can_share` | Boolean | Re-share permission |
| `can_comment` | Boolean | Comment permission |
| `is_active` | Boolean | Share status |
| `created_at` | DateTime | Share creation timestamp |

### ShareLink Table
Public share links with optional passwords.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `resource_type` | Enum | 'file' or 'folder' |
| `file_id` | Integer | Shared file (nullable) |
| `folder_id` | Integer | Shared folder (nullable) |
| `owner_id` | Integer | User who created the link |
| `share_token` | String | Unique share token (UUID) |
| `password_hash` | String | Bcrypt hashed password (nullable) |
| `expires_at` | DateTime | Expiration date (nullable) |
| `is_active` | Boolean | Link status |
| `access_count` | Integer | Number of accesses |
| `created_at` | DateTime | Link creation timestamp |

### User Table (from HR Database)
Users are authenticated via HR database.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | Primary key |
| `username` | String | Login username |
| `email` | String | User email |
| `full_name` | String | Display name |
| `is_admin` | Boolean | Admin flag |
| `can_access_files` | Boolean | Files system access permission |

## API Structure

### Authentication Endpoints (`/api/auth`)
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/verify` - Verify JWT token

### File Endpoints (`/api/files`)
- `GET /api/files/dashboard` - Get dashboard with recent files and stats
- `GET /api/files/folders` - List accessible folders
- `POST /api/files/folders` - Create new folder
- `DELETE /api/files/folders/{folder_id}` - Delete folder (CASCADE)
- `GET /api/files/folders/{folder_id}/files` - List files in folder
- `POST /api/files/upload` - Upload file(s)
- `GET /api/files/download/{file_id}` - Download file
- `GET /api/files/preview/{file_id}` - Preview file (PDF/images/Office docs)
- `DELETE /api/files/{file_id}` - Delete file
- `PUT /api/files/{file_id}/rename` - Rename file
- `PUT /api/files/{file_id}/move` - Move file to different folder
- `POST /api/files/{file_id}/copy` - Copy file to folder
- `GET /api/files/users` - Get list of users for sharing autocomplete

### Share Endpoints (`/api/shares`)
- `POST /api/shares/internal` - Create internal share with user
- `GET /api/shares/internal/by-resource` - Get shares for a file/folder
- `GET /api/shares/internal/shared-with-me` - Get items shared with current user
- `GET /api/shares/internal/shared-by-me` - Get items shared by current user
- `DELETE /api/shares/internal/{share_id}` - Remove internal share
- `POST /api/shares/public` - Create public share link
- `GET /api/shares/public/by-resource` - Get public links for file/folder
- `DELETE /api/shares/public/{link_id}` - Delete public share link
- `GET /api/shares/public/{token}` - Access public share (no auth required)

### Frontend Pages
- `/` - Dashboard with recent files and stats
- `/share/{token}` - Public share access page
- `/health` - Health check endpoint
- `/api/docs` - Interactive API documentation (Swagger UI)

## Directory Structure

```
files/
├── src/
│   └── files/
│       ├── __init__.py
│       ├── main.py                    # FastAPI application
│       ├── init_db.py                 # Database initialization
│       ├── api/
│       │   ├── auth.py                # Authentication endpoints
│       │   ├── filemanager.py         # File management endpoints
│       │   └── shares.py              # Sharing endpoints
│       ├── core/
│       │   ├── config.py              # Configuration settings
│       │   ├── deps.py                # Dependency injection
│       │   └── security.py            # JWT validation
│       ├── db/
│       │   └── database.py            # Database connections
│       ├── models/
│       │   ├── file_metadata.py       # File/Folder models
│       │   ├── shares.py              # Share models (InternalShare, ShareLink)
│       │   └── user.py                # User model
│       └── templates/
│           ├── filemanager.html       # File browser UI
│           └── public_share.html      # Public share access page
├── storage/                           # File storage directory
│   └── user_{id}/                     # Per-user storage
├── logs/                              # Application logs
├── alembic/                           # Database migrations
├── Dockerfile                         # Container definition
├── requirements.txt                   # Python dependencies
└── .env                               # Environment variables
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15 (HR database)
- Access to Portal for SSO

### Environment Variables

Create `.env` file:

```bash
# Application
APP_NAME=Files Management System
APP_VERSION=1.0.0
DEBUG=False

# Database (HR users)
HR_DATABASE_URL=postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db

# Security
SECRET_KEY=your-super-secret-key-change-in-production-galveston34
PORTAL_SECRET_KEY=your-super-secret-key-change-in-production-galveston34

# CORS
ALLOWED_ORIGINS=https://rm.swhgrp.com

# Storage
STORAGE_PATH=/app/storage
```

### Build and Deploy

```bash
# Build container
docker-compose build files-app

# Start service
docker-compose up -d files-app

# View logs
docker-compose logs -f files-app
```

### Access
- **Production:** https://rm.swhgrp.com/files/
- **API Docs:** https://rm.swhgrp.com/files/api/docs
- **Health Check:** https://rm.swhgrp.com/files/health

## Usage

### Upload a File
1. Navigate to https://rm.swhgrp.com/files/
2. Select folder or create new folder
3. Click "Upload" button
4. Choose file(s) from computer
5. Files are uploaded to your user storage area

### Create Folder
1. Click "New Folder" button
2. Enter folder name
3. Choose parent folder (optional)
4. Set public/private visibility

### Share Folder
1. Navigate to folder
2. Click "Share" button
3. Select user(s) to share with
4. Set permissions (read/write/delete)
5. User gains access to folder

### Download File
1. Navigate to file location
2. Click on filename or download icon
3. File downloads directly to your computer

## Permission Model

### Permission Hierarchy
1. **Admin Users:** Full access to all files and folders
2. **Owner:** Full control over their own files/folders
3. **Shared Access:** Explicit permissions granted by owner
4. **Public Folders:** Read-only access for all users

### Permission Types
- **Read:** View folder contents and download files
- **Write:** Upload new files to folder
- **Delete:** Remove files from folder

### Storage Isolation
Each user has a private storage area at `/app/storage/user_{id}/`. Files are organized within this directory, ensuring user data isolation.

## Security Features

### Authentication
- JWT tokens issued by Portal system
- Token validation on every request
- User sessions managed centrally

### Authorization
- Permission checks on all file operations
- Owner validation before modifications
- Admin override capabilities

### Data Protection
- User storage isolation (separate directories)
- MIME type validation
- File size limits (configurable)
- Path traversal prevention

## Integration with Other Systems

### Portal Integration
- **SSO Authentication:** Users log in via Portal
- **Permission Sync:** `can_access_files` flag controls access
- **User Data:** Full name, email from HR database

### Potential Future Integrations
- **Events System:** Attach BEO documents to events
- **HR System:** Employee document storage
- **Accounting System:** Invoice and receipt storage
- **Inventory System:** Product images and vendor docs

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables and secrets |
| `Dockerfile` | Container build instructions |
| `requirements.txt` | Python dependencies |
| `alembic.ini` | Database migration configuration |

## Dependencies

Key Python packages:

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
alembic==1.12.1
psycopg2-binary==2.9.9
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
aiofiles==23.2.1
```

## Troubleshooting

### "Permission denied" errors
**Cause:** User lacks permission to access file/folder
**Solution:**
- Check folder ownership
- Verify permissions granted
- Contact folder owner to request access

### "File not found" errors
**Cause:** File deleted or moved
**Solution:**
- Check if file was deleted by owner
- Verify correct folder location
- Contact admin if data recovery needed

### Upload failures
**Cause:** File size limit, storage full, or network issue
**Solution:**
- Check file size (limit may apply)
- Verify storage space available
- Retry upload with stable connection

### Database connection errors
**Cause:** HR database not accessible
**Solution:**
- Verify `HR_DATABASE_URL` in `.env`
- Check hr-db container is running
- Review docker-compose network config

## Development

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export HR_DATABASE_URL=postgresql://hr_user:HR_Pr0d_2024!@localhost:5432/hr_db
export SECRET_KEY=your-secret-key

# Run with uvicorn
uvicorn files.main:app --reload --host 0.0.0.0 --port 8000
```

### API Documentation
- **Swagger UI:** http://localhost:8000/api/docs
- **ReDoc:** http://localhost:8000/api/redoc

### Testing Uploads

```bash
# Test file upload
curl -X POST "http://localhost:8000/api/files/upload" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@test.pdf"

# Test folder creation
curl -X POST "http://localhost:8000/api/files/folders?name=TestFolder" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/files/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "files",
  "version": "1.0.0"
}
```

### Logs
```bash
# View recent logs
docker-compose logs --tail=100 files-app

# Follow logs
docker-compose logs -f files-app
```

### Storage Usage
```bash
# Check storage size
docker exec files-app du -sh /app/storage

# Check per-user storage
docker exec files-app du -sh /app/storage/user_*
```

## Future Enhancements

- [ ] File versioning (track file history)
- [ ] Search functionality (filename, content)
- [ ] Trash/recycle bin (soft delete)
- [ ] Storage quotas per user
- [ ] Bulk download (zip archives)
- [ ] File tagging and metadata
- [ ] Activity logs (who accessed what)
- [ ] WebDAV support
- [ ] Mobile app support
- [ ] Commenting on files
- [ ] Email notifications for shares

## Support

For issues or questions:
- Check logs: `docker-compose logs files-app`
- Verify storage permissions
- Check network connectivity
- Review JWT token validity

## Version History

### v1.2.0 (2025-10-29)
- **Dashboard View:** Home page with recent files, stats, and shared items
- **My Files View:** Separate traditional folder browser view
- **Username Autocomplete:** Search users by full name when sharing
- **Share Management:** View all shares in dedicated "Shared with Me" and "Shared by Me" pages
- **Share Badges:** Visual indicators showing share status on files/folders
- **Bug Fixes:** Fixed folder CASCADE delete, share counting, and view refresh issues

### v1.1.0 (2025-10-28)
- **File Preview:** In-browser preview for PDFs, images, and Office documents
- **LibreOffice Integration:** Convert Word/Excel/PowerPoint to PDF for preview
- **Internal Sharing:** Share files/folders with specific users
- **Public Share Links:** Generate shareable links with optional passwords
- **Granular Permissions:** View, edit, upload, download, share, comment controls
- **Bulk Operations:** Multi-select files and folders for batch actions
- **File Operations:** Copy, move, and rename files

### v1.0.0 (2025-10-28)
- Initial production release
- File upload/download functionality
- Folder organization with hierarchical structure
- JWT authentication via Portal
- Local filesystem storage
- Admin and owner-based access control

---

**Access:** https://rm.swhgrp.com/files/

**Status:** ✅ Production Ready (100% Complete)
