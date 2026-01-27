# Security Remediation Plan

**Created:** January 25, 2026
**Reference:** `SECURITY_AUDIT_REPORT.md`

---

## Risk Assessment Summary

Each fix has been analyzed for potential breakage to other system components.

---

## Phase 1: Safe Fixes (Do First - No/Low Risk)

### 1. Rotate OpenAI API Key ✅ ZERO RISK
**Steps:**
1. Go to OpenAI console (https://platform.openai.com/api-keys)
2. Revoke the exposed key
3. Generate new key
4. Update `integration-hub/.env` with new key
5. Restart container: `docker restart integration-hub`

**Risk:** None. Immediate security win with no code changes.

---

### 2. Fix Exception Info Disclosure - LOW RISK
**Files to update:**
- `accounting/src/accounting/api/vendor_bills.py:605`
- `accounting/src/accounting/api/payments.py:286`
- `accounting/src/accounting/api/areas.py:340`
- `accounting/src/accounting/api/customer_invoices.py:426`
- `files/src/files/api/filemanager.py:724`
- 20+ more endpoints

**Pattern to fix:**
```python
# BEFORE (bad):
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# AFTER (good):
except Exception as e:
    logger.error(f"Error in operation: {str(e)}", exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error")
```

**Risk:** Very low - just changes error messages users see. Won't break functionality.

---

### 3. Remove Bare `except:` Clauses - LOW RISK
**Files to update:**
- `integration-hub/src/integration_hub/services/email_monitor.py:233,309`
- `accounting/src/accounting/services/csv_parser.py:243,260,284`
- `accounting/src/accounting/services/ofx_parser.py:193`
- `accounting/src/accounting/api/customer_invoices.py:840`

**Pattern to fix:**
```python
# BEFORE (bad):
except:
    pass

# AFTER (good):
except ValueError:
    pass
except Exception as e:
    logger.warning(f"Unexpected error: {e}")
```

**Risk:** Low - might surface errors that were previously silently swallowed, which is actually good for debugging.

---

### 4. Add Null Checks After DB Queries - LOW RISK
**Pattern to fix:**
```python
# BEFORE (bad):
item = db.query(Model).filter(...).first()
item.name  # Crashes if None

# AFTER (good):
item = db.query(Model).filter(...).first()
if not item:
    raise HTTPException(status_code=404, detail="Item not found")
```

**Files with issues:**
- `integration-hub/src/integration_hub/api/vendor_items.py:436-446`
- `files/src/files/webdav_provider.py:125,341`
- Multiple inventory endpoints

**Risk:** Low - endpoints will return proper 404s instead of crashing with 500s.

---

### 5. Fix Division by Zero Risks - LOW RISK
**Files:**
- `inventory/src/restaurant_inventory/models/master_item_count_unit.py:101-109`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/items.py:2161`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/units.py:544`

**Pattern to fix:**
```python
# BEFORE (bad):
result = quantity / conversion_factor

# AFTER (good):
if conversion_factor is None or conversion_factor == 0:
    raise ValueError("Conversion factor must be positive")
result = quantity / conversion_factor
```

**Risk:** Low - prevents crashes, returns proper error messages.

---

## Phase 2: Medium Risk (Requires Testing)

### 6. Add Auth to Unprotected Endpoints - MEDIUM RISK

**BEFORE FIXING - Check for internal callers:**
```bash
# Check if Hub calls accounting accounts
grep -r "api/accounts" integration-hub/ inventory/ portal/

# Check if other services call internal employee endpoint
grep -r "_internal/list" events/ portal/ hr/ integration-hub/

# Check if Hub settings are called internally
grep -r "api/settings" integration-hub/templates/
```

**Endpoints to protect:**
| Endpoint | File | Line | Internal Callers? |
|----------|------|------|-------------------|
| GET /api/accounts/ | accounting/api/accounts.py | 54-103 | CHECK FIRST |
| GET /check-batches/{id}/preview | accounting/api/payments.py | 289-316 | Likely UI only |
| PUT /inventory/{id} | inventory/api/inventory.py | 270-304 | CHECK FIRST |
| GET /_internal/list | hr/endpoints/employees.py | 835-862 | Other services use this |
| /api/settings/* | integration-hub/api/settings.py | 44-436 | UI only |

**Fix pattern:**
```python
# Add to endpoint signature:
current_user: User = Depends(require_auth)
```

**Risk:** Medium - could break integrations if internal services call these without auth tokens.

---

### 7. Fix Path Traversal in File Operations - MEDIUM RISK
**File:** `files/src/files/api/filemanager.py:971,977,1093,1098`

**BEFORE (vulnerable):**
```python
child.path = child.path.replace(old_path, new_path, 1)
```

**AFTER (safe):**
```python
from pathlib import PurePath

# Ensure old_path is at directory boundary
if not child.path.startswith(old_path + "/") and child.path != old_path:
    continue  # Skip - not actually a child

# Use proper path manipulation
relative = PurePath(child.path).relative_to(old_path)
child.path = str(PurePath(new_path) / relative)
```

**Test cases needed:**
- Rename folder with children
- Rename folder with similar-named sibling (e.g., /users/alice vs /users/alice_backup)
- Move folder to different parent
- Nested folder structures

**Risk:** Medium - could affect folder rename/move operations if edge cases aren't handled.

---

### 8. Fix Mass Assignment Vulnerability - MEDIUM RISK
**Files:**
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/inventory.py:286-290`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/items.py:826`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/waste.py:197`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/recipes.py:196,307`

**BEFORE (vulnerable):**
```python
update_data = inventory_data.dict(exclude_unset=True)
for field, value in update_data.items():
    setattr(record, field, value)
```

**AFTER (safe):**
```python
ALLOWED_FIELDS = {'current_quantity', 'unit_cost', 'reorder_level', 'max_level'}
update_data = inventory_data.dict(exclude_unset=True)
for field, value in update_data.items():
    if field in ALLOWED_FIELDS:
        setattr(record, field, value)
```

**Risk:** Medium - need to ensure all legitimate fields are in whitelist.

---

## Phase 3: High Risk (Requires Careful Planning)

### 9. Session Cookie `secure=True` ⚠️ HIGH RISK

**Potential Breakage:** If ANY environment accesses the system over HTTP (not HTTPS), login will completely break - cookies won't be sent.

**Pre-requisites:**
1. Verify nginx terminates HTTPS for all traffic
2. Check all environments (dev, staging, prod) use HTTPS
3. Check if any internal services connect over HTTP

**Safe approach - make configurable:**
```python
# portal/src/portal/main.py:84
secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
response.set_cookie(
    key=SESSION_COOKIE_NAME,
    value=new_token,
    httponly=True,
    secure=secure,  # Now configurable
    ...
)
```

Then set `COOKIE_SECURE=true` in production docker-compose/env.

**Risk:** High - could break all logins if not behind HTTPS.

---

### 10. Enable SSL Verification in OnlyOffice ⚠️ HIGH RISK
**File:** `files/src/files/api/onlyoffice.py:259`

**Potential Breakage:** If OnlyOffice uses self-signed certificates, document editing will completely break.

**Pre-requisites:**
1. Check OnlyOffice container SSL configuration
2. If self-signed, add CA cert to trust store
3. Test document editing after change

**Safe approach:**
```python
# Make configurable
verify_ssl = os.getenv("ONLYOFFICE_VERIFY_SSL", "true").lower() == "true"
async with httpx.AsyncClient(verify=verify_ssl) as client:
```

**Risk:** High - could break document editing entirely.

---

### 11. Remove Hardcoded DB Credentials ⚠️ HIGH RISK
**Files:**
- `integration-hub/src/integration_hub/main.py:1138,1257,2163,2287,2846,3210`
- `integration-hub/src/integration_hub/services/accounting_sender.py:47`
- `integration-hub/src/integration_hub/db/database.py:11`

**Potential Breakage:** The dblink queries are used for cross-database lookups. Removing them without proper replacement breaks invoice processing.

**Safe migration approach:**
```python
# Step 1: Add env var support with fallback (deploy this first)
INVENTORY_DB_URL = os.getenv(
    "INVENTORY_DB_URL",
    "postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db"  # Keep fallback temporarily
)

# Step 2: Update docker-compose to set INVENTORY_DB_URL
# Step 3: Verify everything works
# Step 4: Remove fallback in separate deploy
```

**Risk:** High - could break invoice processing and item mapping.

---

### 12. Remove Weak Secret Key Defaults ⚠️ HIGH RISK
**Files:**
- `portal/src/portal/config.py:11`
- `events/src/events/core/security.py:10`

**Potential Breakage:** If environment variable isn't set, app won't start.

**Pre-requisites:**
1. Audit ALL environments for SECRET_KEY and PORTAL_SECRET_KEY
2. Check docker-compose files
3. Check Kubernetes configs if applicable

**Safe approach:**
```python
# Add validation at startup
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")
if SECRET_KEY.startswith("your-") or "change-in-production" in SECRET_KEY:
    raise ValueError("SECRET_KEY appears to be a placeholder - set a real secret")
```

**Risk:** High - could prevent apps from starting.

---

## Phase 4: Highest Risk (Needs Full Migration Plan)

### 13. Encrypt Plaid/Clover API Tokens ⚠️ HIGHEST RISK
**Files:**
- `accounting/src/accounting/models/bank_account.py:33`
- `accounting/src/accounting/models/pos.py:22`

**This requires a full migration:**

1. **Add encryption infrastructure:**
```python
# accounting/src/accounting/core/encryption.py
from cryptography.fernet import Fernet

ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("TOKEN_ENCRYPTION_KEY must be set")

fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    return fernet.decrypt(encrypted.encode()).decode()
```

2. **Create migration script:**
```python
# Encrypt all existing tokens in database
for account in db.query(BankAccount).filter(BankAccount.plaid_access_token.isnot(None)):
    if not account.plaid_access_token.startswith("gAAAAA"):  # Not already encrypted
        account.plaid_access_token = encrypt_token(account.plaid_access_token)
db.commit()
```

3. **Update all code that reads/writes tokens**

4. **Test thoroughly before production**

**Risk:** Highest - if encryption key is lost or wrong, bank integration breaks completely.

---

## Recommended Execution Order

| Week | Phase | Items | Risk Level |
|------|-------|-------|------------|
| Week 1 Day 1 | 1 | Rotate OpenAI key | None |
| Week 1 Day 2-3 | 1 | Exception disclosure, bare excepts, null checks, division by zero | Low |
| Week 1 Day 4-5 | 2 | Audit internal callers for auth endpoints | Medium |
| Week 2 | 2 | Add auth to safe endpoints, path traversal fix, mass assignment | Medium |
| Week 3 | 3 | Cookie security (after HTTPS verification), SSL verification | High |
| Week 4 | 3 | Credential externalization (with fallbacks first) | High |
| Week 5+ | 4 | Token encryption (full migration with testing) | Highest |

---

## Testing Checklist

Before deploying any security fix:

- [ ] Run in development/staging first
- [ ] Test affected functionality manually
- [ ] Check container logs for errors: `docker logs <container> --tail 100`
- [ ] Verify no 500 errors in response
- [ ] For auth changes: test both authenticated and unauthenticated access
- [ ] For path operations: test folder rename/move with nested structures

---

## Rollback Plan

For each phase, keep a rollback ready:

```bash
# Git-based rollback
git stash  # or git checkout -- <file>
docker restart <container>

# If database was modified
# Keep backup before any migrations
pg_dump -h localhost -U user dbname > backup_before_security_fix.sql
```
