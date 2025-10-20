# HR System - Roles and Permissions

## Overview

The HR system now has a comprehensive role-based access control (RBAC) system with two default roles: **Admin** and **Manager**.

## Default Roles

### Admin Role
**Description**: Full system access - all permissions

**Permissions**:
- **Employee Management**: view, create, edit, delete, export employees
- **Position Management**: view, create, edit, delete positions
- **Document Management**: view, upload, delete documents
- **User Management**: view, create, edit, delete users, manage roles
- **Reports**: view and export reports

### Manager Role
**Description**: Create/view employees and upload documents

**Permissions**:
- **Employee Management**: view, create employees
- **Position Management**: view positions
- **Document Management**: view, upload documents

## Database Schema

### Tables Created

1. **roles** - Stores role definitions
   - `id`, `name`, `description`, `is_active`, `created_at`, `updated_at`

2. **permissions** - Stores available permissions
   - `id`, `name`, `description`, `resource`, `action`, `created_at`

3. **role_permissions** - Links roles to permissions (many-to-many)
   - `id`, `role_id`, `permission_id`, `created_at`

4. **user_roles** - Links users to roles (many-to-many)
   - `id`, `user_id`, `role_id`, `assigned_at`, `assigned_by`

## API Endpoints

All role management endpoints require **Admin** privileges.

### Role Management

```
GET    /api/roles/                     - List all roles
GET    /api/roles/{role_id}            - Get role with permissions
POST   /api/roles/                     - Create new role
PUT    /api/roles/{role_id}            - Update role
DELETE /api/roles/{role_id}            - Delete role
```

### Permission Management

```
GET    /api/roles/permissions/all      - List all available permissions
```

### User Role Assignment

```
POST   /api/roles/assign               - Assign role to user
DELETE /api/roles/assign/{user_role_id} - Remove role from user
GET    /api/roles/user/{user_id}       - Get user's roles
GET    /api/roles/me/roles             - Get current user's roles and permissions
```

## Usage Examples

### 1. Assign Admin Role to a User

```bash
curl -X POST "http://localhost:8000/api/roles/assign" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "role_id": 1
  }'
```

### 2. Get User's Roles

```bash
curl -X GET "http://localhost:8000/api/roles/user/1"
```

### 3. Get Current User's Roles and Permissions

```bash
curl -X GET "http://localhost:8000/api/roles/me/roles"
```

### 4. List All Roles

```bash
curl -X GET "http://localhost:8000/api/roles/"
```

### 5. Get Role with Permissions

```bash
curl -X GET "http://localhost:8000/api/roles/1"
```

## Authorization Helper Functions

The system provides helper functions in `hr.core.authorization`:

### Permission Checking

```python
from hr.core.authorization import check_permission, require_permission

# Check if user has permission
if check_permission(db, user, "view_employees"):
    # User has permission
    pass

# Use as route dependency
@router.get("/employees", dependencies=[Depends(require_permission("view_employees"))])
def list_employees():
    pass
```

### Role Checking

```python
from hr.core.authorization import check_role, require_role

# Check if user has role
if check_role(db, user, "Manager"):
    # User has Manager role
    pass

# Use as route dependency
@router.get("/reports", dependencies=[Depends(require_role("Manager"))])
def view_reports():
    pass
```

### Multiple Permissions/Roles

```python
from hr.core.authorization import require_any_permission, require_any_role

# Require ANY of the listed permissions
@router.get("/data", dependencies=[Depends(require_any_permission("view_employees", "manage_employees"))])
def get_data():
    pass

# Require ANY of the listed roles
@router.get("/admin", dependencies=[Depends(require_any_role("Admin", "Manager"))])
def admin_page():
    pass
```

## Permission Naming Convention

Permissions follow the pattern: `{action}_{resource}`

**Resources**: employee, position, document, user, report
**Actions**: view, create, edit, delete, export, upload, manage_roles

Examples:
- `view_employees`
- `create_employee`
- `edit_position`
- `upload_document`
- `manage_roles`

## Managing Roles and Permissions

### Adding a New Permission

1. Add the permission to the database:

```python
permission = Permission(
    name="archive_employee",
    description="Archive employee records",
    resource="employee",
    action="archive"
)
db.add(permission)
db.commit()
```

2. Assign to roles:

```python
role_perm = RolePermission(
    role_id=1,  # Admin role
    permission_id=permission.id
)
db.add(role_perm)
db.commit()
```

### Creating a New Role

Use the API or create directly:

```python
new_role = Role(
    name="HR Officer",
    description="Limited HR access",
    is_active=True
)
db.add(new_role)
db.flush()

# Add permissions
for perm_name in ["view_employees", "create_employee"]:
    perm = db.query(Permission).filter(Permission.name == perm_name).first()
    if perm:
        role_perm = RolePermission(role_id=new_role.id, permission_id=perm.id)
        db.add(role_perm)

db.commit()
```

## Re-seeding Roles and Permissions

To reset or update roles and permissions:

```bash
# Inside the container
docker compose exec hr-app python seed_roles.py

# Or from host
docker compose exec hr-app python seed_roles.py
```

The script is idempotent - it will create new roles/permissions or update existing ones.

## User Responses Now Include Roles

All user response objects now include a `roles` field:

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "full_name": "System Administrator",
  "is_active": true,
  "is_admin": true,
  "created_at": "2025-10-15T10:00:00Z",
  "roles": ["Admin"]
}
```

## Migration Information

**Migration Version**: `20251015_1600`
**Previous Version**: `20251015_1500`

The migration creates all four tables (roles, permissions, role_permissions, user_roles) with appropriate indexes and foreign key constraints.

## Testing the System

1. **Login as an admin user** to test full access
2. **Create a new user** via the API
3. **Assign the Manager role** to the new user
4. **Login as the Manager** and verify limited access
5. **Try accessing admin-only endpoints** - should receive 403 Forbidden

## Future Enhancements

Potential improvements:
- Location-based permissions (restrict users to specific locations)
- Dynamic permission assignment in UI
- Role hierarchy (roles inherit from parent roles)
- Audit logging for role changes
- Permission caching for performance
- Role expiration dates
- Temporary elevated permissions
