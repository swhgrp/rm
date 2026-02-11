# Files Sharing API Documentation

Complete API reference for advanced file sharing features in the SW Restaurant Management Files System.

**Last Updated:** 2025-10-29

## Recent Updates (v1.2.0)
- Username autocomplete when creating internal shares
- Share badges visible on files/folders
- Dedicated "Shared with Me" and "Shared by Me" pages
- Improved share management UI
- Fixed share counting to only include active shares

## Base URL

```
https://rm.swhgrp.com/files/api/shares
```

## Authentication

Most endpoints require JWT authentication via Portal SSO. Exceptions are noted with 🔓 (public access).

**Headers:**
```
Authorization: Bearer <jwt_token>
```

---

## Share Links (External Sharing)

Create public share links for files and folders with expiration, passwords, and usage limits.

### Create Share Link

**`POST /links`**

Create a new public share link.

**Request Body:**
```json
{
  "resource_type": "folder",  // or "file"
  "resource_id": 123,
  "access_type": "read_only",  // read_only | upload_only | read_write | edit | admin
  "password": "optional-password",
  "require_login": false,
  "expires_in_days": 30,  // null = never expires
  "max_downloads": null,  // null = unlimited
  "max_uses": null,
  "allow_download": true,
  "allow_preview": true,
  "notify_on_access": false
}
```

**Response:**
```json
{
  "id": 1,
  "share_url": "https://rm.swhgrp.com/files/s/abc123...",
  "share_token": "abc123def456...",
  "resource_type": "folder",
  "resource_name": "Q4 Reports",
  "access_type": "read_only",
  "expires_at": "2025-12-01T00:00:00Z",
  "is_password_protected": true,
  "require_login": false,
  "created_at": "2025-11-01T10:30:00Z",
  "is_active": true,
  "download_count": 0,
  "use_count": 0
}
```

**Access Types:**
- `read_only` - View and download only
- `upload_only` - Upload files only (for vendor file collection)
- `read_write` - View, download, and upload
- `edit` - Full edit permissions
- `admin` - Full control including resharing

---

### List My Share Links

**`GET /links?active_only=true`**

Get all share links created by current user.

**Query Parameters:**
- `active_only` (boolean, default: true) - Only show active links

**Response:**
```json
[
  {
    "id": 1,
    "share_url": "https://rm.swhgrp.com/files/s/abc123...",
    "resource_name": "Q4 Reports",
    "access_type": "read_only",
    "expires_at": "2025-12-01T00:00:00Z",
    "download_count": 45,
    "is_active": true
  }
]
```

---

### Revoke Share Link

**`DELETE /links/{share_link_id}`**

Deactivate a share link (cannot be reactivated).

**Response:**
```json
{
  "message": "Share link revoked successfully",
  "id": 1
}
```

---

### Get Share Info 🔓

**`GET /access/{share_token}`** *(Public - No Auth Required)*

Get information about a share link before accessing it.

**Response:**
```json
{
  "resource_type": "folder",
  "resource_name": "Q4 Reports",
  "access_type": "read_only",
  "requires_password": true,
  "requires_login": false,
  "expires_at": "2025-12-01T00:00:00Z",
  "allow_download": true,
  "allow_preview": true
}
```

**Error Responses:**
- `404` - Share link not found
- `410` - Share link expired or deactivated

---

### Verify Share Access 🔓

**`POST /access/{share_token}/verify`** *(Public - No Auth Required)*

Verify password and gain access to a share link.

**Request Body:**
```json
{
  "password": "optional-password"
}
```

**Response:**
```json
{
  "message": "Access granted",
  "access_type": "read_only",
  "resource_type": "folder"
}
```

**Error Responses:**
- `401` - Password required or incorrect
- `410` - Share link expired

---

## Internal Shares (HR User Sharing)

Share files and folders with internal HR users with granular permissions.

### Create Internal Share

**`POST /internal`**

Share a file or folder with HR users, departments, roles, or locations.

**Request Body:**
```json
{
  "resource_type": "folder",
  "resource_id": 123,

  // At least one target required:
  "shared_with_user_id": 5,
  "shared_with_department": "Accounting",
  "shared_with_role": "Manager",
  "shared_with_location": "Seaside Grill",

  // Granular permissions:
  "can_view": true,
  "can_download": true,
  "can_upload": false,
  "can_edit": false,
  "can_delete": false,
  "can_share": false,  // Can they reshare?
  "can_comment": true,

  "expires_in_days": 90,
  "message": "Please review these files by end of quarter",
  "notify_by_email": true
}
```

**Response:**
```json
{
  "id": 1,
  "resource_type": "folder",
  "resource_name": "Q4 Reports",
  "shared_with_user": "John Smith",
  "shared_with_department": "Accounting",
  "permissions": {
    "can_view": true,
    "can_download": true,
    "can_upload": false,
    "can_edit": false,
    "can_delete": false,
    "can_share": false,
    "can_comment": true
  },
  "shared_at": "2025-11-01T10:30:00Z",
  "expires_at": "2026-02-01T10:30:00Z",
  "is_active": true
}
```

---

### Shared With Me

**`GET /internal/shared-with-me`**

Get all files/folders shared with current user.

**Response:**
```json
[
  {
    "id": 1,
    "resource_type": "folder",
    "resource_name": "Q4 Reports",
    "shared_with_user": "Jane Doe",
    "permissions": { /* ... */ },
    "shared_at": "2025-11-01T10:30:00Z",
    "is_active": true
  }
]
```

---

### Shared By Me

**`GET /internal/shared-by-me`**

Get all files/folders shared by current user.

**Response:**
```json
[
  {
    "id": 1,
    "resource_type": "folder",
    "resource_name": "Q4 Reports",
    "shared_with_user": "John Smith",
    "shared_with_department": "Accounting",
    "permissions": { /* ... */ },
    "shared_at": "2025-11-01T10:30:00Z",
    "is_active": true
  }
]
```

---

### Revoke Internal Share

**`DELETE /internal/{share_id}`**

Revoke an internal share.

**Response:**
```json
{
  "message": "Share revoked successfully",
  "id": 1
}
```

---

## Share Access Types

| Type | View | Download | Upload | Edit | Delete | Share |
|------|------|----------|--------|------|--------|-------|
| `read_only` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `upload_only` | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `read_write` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `edit` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Security Features

### Password Protection
- Passwords hashed with bcrypt (cost factor 12)
- Never returned in API responses
- Required for access if set

### Expiration
- Automatic validation on access
- `expires_at` timestamp in UTC
- Once expired, cannot be accessed

### Usage Limits
- `max_downloads` - Maximum file downloads (null = unlimited)
- `max_uses` - Maximum accesses (null = unlimited)
- Counters incremented on each use

### Audit Trail
All access logged in `share_access_logs`:
- User ID (if logged in)
- IP address
- User agent
- Action (view, download, upload, preview)
- Timestamp
- Success/failure

---

## Examples

### Create Password-Protected Share with 30-Day Expiration

```bash
curl -X POST "https://rm.swhgrp.com/files/api/shares/links" \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "folder",
    "resource_id": 123,
    "access_type": "read_only",
    "password": "SecurePass123!",
    "expires_in_days": 30,
    "allow_download": true,
    "notify_on_access": true
  }'
```

### Share Folder with Accounting Department

```bash
curl -X POST "https://rm.swhgrp.com/files/api/shares/internal" \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "folder",
    "resource_id": 123,
    "shared_with_department": "Accounting",
    "can_view": true,
    "can_download": true,
    "can_comment": true,
    "message": "Q4 financial reports ready for review"
  }'
```

### Access Public Share with Password

```bash
# Step 1: Get share info
curl "https://rm.swhgrp.com/files/api/shares/access/abc123def456"

# Step 2: Verify password
curl -X POST "https://rm.swhgrp.com/files/api/shares/access/abc123def456/verify" \
  -H "Content-Type: application/json" \
  -d '{"password": "SecurePass123!"}'
```

---

## Error Codes

| Code | Description |
|------|-------------|
| `400` | Bad Request - Invalid parameters |
| `401` | Unauthorized - Missing or invalid auth token |
| `403` | Forbidden - No permission to perform action |
| `404` | Not Found - Resource or share not found |
| `410` | Gone - Share link expired or deactivated |
| `500` | Internal Server Error |

---

## Interactive API Documentation

Full interactive API docs available at:

**Swagger UI:** https://rm.swhgrp.com/files/api/docs
**ReDoc:** https://rm.swhgrp.com/files/api/redoc

---

## Next Features (Planned)

- [ ] Share analytics dashboard
- [ ] Email notifications on share access
- [ ] Scheduled share expiration reminders
- [ ] Bulk share operations
- [ ] Share templates for common use cases
- [ ] QR codes for share links
- [ ] Share link customization (vanity URLs)
