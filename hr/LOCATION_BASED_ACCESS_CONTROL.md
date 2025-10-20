# HR System - Location-Based Access Control

## Overview

The HR system now supports **multi-location management** with location-based access control. Users can be assigned to specific restaurant locations, and will only see employees, positions, and data for their assigned locations.

This implementation follows the same pattern as the inventory system for consistency across the restaurant management platform.

## Key Concepts

### Access Control Levels

1. **Admin Users** (`is_admin = True`)
   - Have access to ALL locations automatically
   - No location restrictions
   - Can manage location assignments for other users

2. **Location-Restricted Users**
   - Assigned to specific locations
   - Only see data for their assigned locations
   - Cannot access data from other locations

3. **No-Access Users** (non-admin with no location assignments)
   - Have NO access to any data
   - Will see empty result sets
   - Must be assigned to at least one location to view data

### Important Security Principle

**Safe Default**: Non-admin users without location assignments get **NO ACCESS** (empty results), not all locations. This prevents accidental data exposure.

## Database Schema

### New Tables

#### `locations`
Restaurant location master data:
```sql
id              INTEGER PRIMARY KEY
name            VARCHAR NOT NULL (indexed)
address         TEXT
city            VARCHAR
state           VARCHAR(2)
zip_code        VARCHAR(10)
phone           VARCHAR
manager_name    VARCHAR
is_active       BOOLEAN DEFAULT true
created_at      TIMESTAMP WITH TIME ZONE
updated_at      TIMESTAMP WITH TIME ZONE
```

#### `user_locations`
Junction table linking users to locations (many-to-many):
```sql
user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE
location_id     INTEGER REFERENCES locations(id) ON DELETE CASCADE
created_at      TIMESTAMP WITH TIME ZONE
PRIMARY KEY (user_id, location_id)
```

**Indexes:**
- `ix_user_locations_user_id`
- `ix_user_locations_location_id`

### Model Relationships

```python
# User model
class User(Base):
    assigned_locations = relationship("Location", secondary=user_locations, backref="assigned_users")

# Location model
class Location(Base):
    # Automatically has `assigned_users` backref
    pass
```

## API Endpoints

### Location Management

All location management endpoints require authentication. CRUD operations require **Admin** privileges.

```
GET    /api/locations/                 - List locations (filtered by user access)
GET    /api/locations/{location_id}    - Get location (only if user has access)
POST   /api/locations/                 - Create location (Admin only)
PUT    /api/locations/{location_id}    - Update location (Admin only)
DELETE /api/locations/{location_id}    - Delete location (Admin only)
```

### User Location Assignment

Admin-only endpoints for managing user-location assignments:

```
GET    /api/locations/user/{user_id}   - Get user's assigned locations
POST   /api/locations/user/{user_id}   - Assign locations to user
DELETE /api/locations/user/{user_id}   - Clear all assignments (grants full access)
```

## Usage Examples

### 1. Create a Location

```bash
curl -X POST "http://localhost:8000/api/locations/" \
  -H "Content-Type: application/json" \
  -H "Cookie: hr_session=<session_token>" \
  -d '{
    "name": "Downtown Portland",
    "address": "123 Main St",
    "city": "Portland",
    "state": "OR",
    "zip_code": "97201",
    "phone": "503-555-1234",
    "manager_name": "John Smith"
  }'
```

### 2. Assign Locations to User

```bash
curl -X POST "http://localhost:8000/api/locations/user/2" \
  -H "Content-Type: application/json" \
  -H "Cookie: hr_session=<admin_session>" \
  -d '{
    "location_ids": [1, 3, 5]
  }'
```

**Note:** Empty `location_ids` array `[]` means user has access to ALL locations (no restrictions).

### 3. Get User's Assigned Locations

```bash
curl -X GET "http://localhost:8000/api/locations/user/2" \
  -H "Cookie: hr_session=<admin_session>"
```

Response:
```json
{
  "user_id": 2,
  "username": "manager1",
  "assigned_locations": [
    {
      "id": 1,
      "name": "Downtown Portland",
      "address": "123 Main St",
      "is_active": true,
      "created_at": "2025-10-15T10:00:00Z"
    }
  ],
  "has_restrictions": true
}
```

### 4. Clear User's Location Assignments (Grant Full Access)

```bash
curl -X DELETE "http://localhost:8000/api/locations/user/2" \
  -H "Cookie: hr_session=<admin_session>"
```

### 5. List Locations (Filtered by User Access)

```bash
curl -X GET "http://localhost:8000/api/locations/" \
  -H "Cookie: hr_session=<user_session>"
```

Users only see locations they have access to.

## How Location Filtering Works

### Authorization Helper Functions

Located in [`hr/src/hr/core/authorization.py`](hr/src/hr/core/authorization.py):

#### `get_user_location_ids(user: User) -> Optional[List[int]]`

Returns:
- `None` - User is admin (access to all locations)
- `[1, 2, 3]` - User has access to specific locations
- `[]` - User has no access (safe default)

```python
from hr.core.authorization import get_user_location_ids

location_ids = get_user_location_ids(current_user)

if location_ids is None:
    print("Admin - full access")
elif location_ids:
    print(f"Access to locations: {location_ids}")
else:
    print("No access")
```

#### `filter_by_user_locations(query, location_column, user: User)`

Applies location filtering to a SQLAlchemy query:

```python
from hr.core.authorization import filter_by_user_locations

# Example: Filter employees by location
query = db.query(Employee).join(EmployeePosition)
query = filter_by_user_locations(query, EmployeePosition.location_id, current_user)
employees = query.all()
```

### Filtered Endpoints

The following endpoints are automatically filtered by location:

**Employees:**
- `GET /api/employees/` - List employees
- `GET /api/employees/{id}` - Get employee
- `PUT /api/employees/{id}` - Update employee
- `DELETE /api/employees/{id}` - Delete employee

Employees are filtered based on their **position assignments**. Users only see employees who have positions at locations they can access.

**Locations:**
- `GET /api/locations/` - List locations
- `GET /api/locations/{id}` - Get location

## Employee-Location Relationship

Employees don't have a direct `location_id` field. Instead, they're linked to locations through **position assignments** (`employee_positions` table):

```
Employee
  └─> EmployeePosition (has location_id)
        └─> Location
```

This allows:
- Employees to work at multiple locations
- Different positions at different locations
- Different pay rates per location

### Example Query Pattern

```python
from hr.models.employee import Employee
from hr.models.employee_position import EmployeePosition
from hr.core.authorization import get_user_location_ids

# Get user's location IDs
location_ids = get_user_location_ids(current_user)

# Build query
query = db.query(Employee).join(
    EmployeePosition,
    Employee.id == EmployeePosition.employee_id
)

# Apply filtering
if location_ids is not None:  # Not admin
    query = query.filter(EmployeePosition.location_id.in_(location_ids))

# Execute
employees = query.distinct().all()  # distinct() to avoid duplicates
```

## Authentication with Location Loading

The `get_current_user()` function automatically **eagerly loads** user locations to prevent N+1 query problems:

```python
def get_current_user(request: Request, db: Session) -> Optional[User]:
    # ... authentication logic ...

    user = db.query(User).options(
        joinedload(User.assigned_locations)  # Eager load!
    ).filter(User.id == user_id).first()

    return user
```

This ensures `user.assigned_locations` is available without additional queries.

## Migration Information

**Migration Version**: `20251015_1700`
**Previous Version**: `20251015_1600`

The migration creates:
1. `locations` table with indexes
2. `user_locations` junction table with composite primary key
3. Indexes on both foreign keys for query performance
4. CASCADE delete constraints for automatic cleanup

## Best Practices

### 1. Always Apply Location Filtering First

```python
# CORRECT - Apply location filter first
query = db.query(Employee).join(EmployeePosition)
query = filter_by_user_locations(query, EmployeePosition.location_id, user)
query = query.filter(Employee.employment_status == "Active")

# WRONG - Other filters might expose data before location filter
query = db.query(Employee).filter(Employee.employment_status == "Active")
query = query.join(EmployeePosition)
query = filter_by_user_locations(query, EmployeePosition.location_id, user)
```

### 2. Use Distinct for Multi-Location Employees

```python
# Employees can have multiple positions at different locations
# Use distinct() to avoid duplicates in results
employees = query.distinct().all()
```

### 3. Check Access Before Modification

```python
# Always verify user has access before allowing updates/deletes
employee = get_employee_with_location_check(employee_id, current_user)
if not employee:
    raise HTTPException(status_code=404, detail="Not found or no access")
```

### 4. Admin Bypass Pattern

```python
location_ids = get_user_location_ids(user)

if location_ids is None:
    # Admin - no filtering needed
    query = db.query(Employee)
else:
    # Non-admin - apply filtering
    query = db.query(Employee).join(EmployeePosition)
    query = query.filter(EmployeePosition.location_id.in_(location_ids))
```

## Security Considerations

### 1. Information Disclosure

The system returns **404 Not Found** (not 403 Forbidden) when users try to access resources at locations they don't have access to. This prevents information disclosure about whether a resource exists.

```python
# CORRECT
if not employee:
    raise HTTPException(
        status_code=404,
        detail="Employee not found or you don't have access to their location"
    )

# WRONG - Leaks existence information
if not employee:
    if user_has_access:
        raise HTTPException(status_code=404)
    else:
        raise HTTPException(status_code=403)
```

### 2. Cascade Deletes

When a location or user is deleted, all assignments are automatically cleaned up:

```sql
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
```

### 3. Assignment Validation

The API validates all location IDs before creating assignments:

```python
# Verify all location IDs exist
locations = db.query(Location).filter(Location.id.in_(location_ids)).all()
if len(locations) != len(location_ids):
    raise HTTPException(status_code=400, detail="Invalid location IDs")
```

## Testing the System

### Test Scenario 1: Admin Access

```bash
# Login as admin
# Admin should see ALL employees regardless of location

curl -X GET "http://localhost:8000/api/employees/" \
  -H "Cookie: hr_session=<admin_session>"
```

### Test Scenario 2: Location-Restricted Manager

```bash
# 1. Create user
# 2. Assign to Manager role
# 3. Assign to location ID 1
# 4. Login as that user
# 5. Try to list employees

# Should only see employees with positions at location 1
curl -X GET "http://localhost:8000/api/employees/" \
  -H "Cookie: hr_session=<manager_session>"
```

### Test Scenario 3: No Access Default

```bash
# 1. Create user
# 2. Assign to Manager role
# 3. Do NOT assign any locations
# 4. Login as that user
# 5. Try to list employees

# Should receive empty array (no access)
curl -X GET "http://localhost:8000/api/employees/" \
  -H "Cookie: hr_session=<no_location_user>"

# Response: []
```

### Test Scenario 4: Multi-Location Access

```bash
# 1. Assign user to locations [1, 2, 3]
# 2. Login and list employees
# 3. Should see employees from all three locations

curl -X GET "http://localhost:8000/api/employees/" \
  -H "Cookie: hr_session=<multi_location_manager>"
```

## Troubleshooting

### Issue: User sees no data after assignment

**Check:**
1. User has assigned locations: `GET /api/locations/user/{user_id}`
2. Employees have position assignments with `location_id` set
3. User is authenticated and session is valid

### Issue: Admin sees same as regular user

**Check:**
1. User's `is_admin` flag is set to `true`
2. Session is valid and reflects admin status

### Issue: N+1 query problems

**Solution:**
The `get_current_user()` function uses `joinedload(User.assigned_locations)` to eagerly load locations. Verify this is in place.

### Issue: Duplicate employees in results

**Solution:**
Use `.distinct()` when querying employees with joins to `employee_positions`:

```python
employees = query.distinct().all()
```

## Future Enhancements

Potential improvements:
- Location-based document access control
- Location-specific position availability
- Cross-location transfer workflows
- Location hierarchy (regions > districts > stores)
- Temporary location access grants
- Location access audit logging
- Location-based reporting dashboards

## Integration with Other Services

The location system is designed to integrate with:

**Inventory System:**
- Employees can be linked to inventory system users at specific locations
- Location IDs can be synchronized across services

**Accounting System:**
- Payroll can be calculated per location
- Location-based expense tracking
- Multi-location P&L reports

**POS System (Future):**
- Employee clock-in/out per location
- Sales data by location
- Inventory sync per location

## Summary

The location-based access control system provides:

✅ **Secure** - Safe defaults, no information disclosure
✅ **Flexible** - Multi-location assignments per user
✅ **Performant** - Eager loading, indexed queries
✅ **Consistent** - Same pattern as inventory system
✅ **Admin-Friendly** - Easy assignment management
✅ **Scalable** - Handles multiple locations efficiently

All location management is done through the API with proper authentication and authorization checks.
