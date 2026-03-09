# Security Audit & Remediation Tracker

**Original Audit:** January 25, 2026
**Last Verified:** March 8, 2026
**Total Issues Found:** 93 (12 Critical, 29 High, 35 Medium, 17 Low)

---

## Status Summary

| Category | Total | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 12 | 5 | 7 |
| High | 29 | 3 | 26 |
| Medium | 35 | 0 | 35 |
| Low | 17 | 0 | 17 |

---

## Critical Issues

### FIXED

| # | Issue | File | Fixed Date |
|---|-------|------|-----------|
| 1 | Hardcoded OpenAI API key | integration-hub/.env | Feb 6 — Key rotated on OpenAI dashboard |
| 2 | Hardcoded DB credentials in source code | hub/main.py, accounting_sender.py, database.py, portal/config.py, inventory/config.py | Feb 6 — All now use `os.getenv()` |
| 4 | Missing auth on Accounting accounts endpoints | accounting/api/accounts.py | Feb 6 — Added `Depends(require_auth)` |
| 6 | Insecure cookie configuration (secure=False) | portal/main.py | Fixed — All `set_cookie()` calls now have `secure=True` |
| 15 | Mass assignment vulnerability (setattr) | inventory/api/inventory.py | Fixed — Pydantic schema whitelist enforces allowed fields |

### NOT FIXED

| # | Issue | File | Risk | Notes |
|---|-------|------|------|-------|
| 3 | Weak secret key defaults | portal/config.py:10, events/core/security.py:10 | CRITICAL | Still has `"your-secret-key-change-in-production"` as default fallback. Should fail if env var missing. |
| 5 | Plaintext Plaid/Clover API tokens | accounting/models/bank_account.py:33, pos.py:22 | CRITICAL | OAuth tokens unencrypted in DB. Requires migration to encrypt existing tokens. |
| 7 | SSL verification disabled (verify=False) | files/api/onlyoffice.py:259 | CRITICAL | OnlyOffice HTTP calls skip SSL. Internal Docker network mitigates somewhat. |
| 8 | Path traversal in file operations | files/api/filemanager.py:971,977,1093,1098 | CRITICAL | `str.replace()` on paths — should use `pathlib` for safe path manipulation. |

---

## High Severity Issues

### FIXED

| # | Issue | File | Notes |
|---|-------|------|-------|
| 10 | Missing auth on check batch preview | accounting/api/payments.py | Auth added |
| 8* | Mass assignment (duplicate of #15) | inventory/api/inventory.py | Pydantic schema enforces whitelist |

### NOT FIXED

| # | Issue | File | Notes |
|---|-------|------|-------|
| 9 | Missing auth on Inventory update endpoint | inventory/api/inventory.py:270 | No authorization check |
| 11 | Missing location-based access on HR delete | hr/endpoints/employees.py:399 | Admin can delete any employee regardless of location |
| 12 | Unprotected internal employee endpoint | hr/endpoints/employees.py:835 | `/_internal/list` has no auth — used by other services |
| 13 | Weak password sync authentication | events/api/auth.py:151 | Simple string comparison for service auth |
| 14 | Missing settings API authentication | integration-hub/api/settings.py:44 | Email credentials accessible without auth |
| 16 | SSO role escalation risk | inventory/api/auth.py:112 | Role from external source not validated |
| 17 | Unvalidated role from external source | inventory/core/deps.py:87 | Same issue as #16 |
| 18-22 | Bare except clauses / exception handling | email_monitor.py, csv_parser.py, vendor_bills.py, filemanager.py, hr/main.py | Swallows errors, discloses info |
| 23 | Command injection in CalDAV sync | events/services/caldav_sync_service.py:340 | `subprocess.run` with user-derived file_path |
| 24 | Command injection in LibreOffice subprocess | files/api/filemanager.py:690 | User filename in subprocess call |
| 25 | Raw SQL execution | accounting/services/bank_matching.py:450 | SQL string building |
| 26-29 | Data security (email password, decryption fallback, credential exposure, health check info) | Various | Plaintext storage, info disclosure |
| 30-37 | Logic bugs (race conditions, division by zero, missing filters) | Various | See original audit for details |

---

## Medium Severity (35 issues — not yet addressed)

**Security:** Missing hCaptcha, rate limiting, debug endpoint exposed (`portal/main.py /debug`), CSRF protection, CORS wildcard, weak MD5, XSS risks, token in URL, file upload validation

**Logic:** Missing null checks, no batch limits, weak password validation (8 chars only), type confusion, hardcoded AP account/system user IDs, missing folder depth limit, unsafe JSON deserialization, missing audit logging

---

## Low Severity (17 issues — code quality)

Print statements in production, dead code, inconsistent transaction handling, multiple DB engines, import inside functions, magic numbers, hardcoded timezone, inconsistent error formats, duplicate permission code, missing type hints, inconsistent pagination

---

## Remediation Priority

### Do Next (Low Risk)
1. **Remove weak secret key defaults** — Make apps fail on startup if SECRET_KEY not set
2. **Remove /debug endpoint** — Or add admin-only auth
3. **Fix exception info disclosure** — Replace `str(e)` with generic messages in HTTP responses
4. **Fix bare except clauses** — Use specific exception types
5. **Add null checks after DB queries** — Return 404 instead of crashing

### Requires Testing (Medium Risk)
6. **Fix path traversal** — Replace `str.replace()` with `pathlib` operations
7. **Add auth to remaining endpoints** — Check for internal service callers first
8. **Fix command injection** — Validate/sanitize file paths in subprocess calls
9. **Add rate limiting** — Public endpoints (events intake, file shares)

### Requires Migration (High Risk)
10. **Encrypt Plaid/Clover tokens** — Needs encryption key management + data migration
11. **Enable SSL verification** — Check OnlyOffice cert config first
12. **Fix CalDAV subprocess** — Validate event_id format before building paths

---

## Methodology

Original audit performed January 25, 2026 using static code analysis across 725 Python and HTML files. Status verified against live codebase March 8, 2026.

Previous detailed files archived: see `SECURITY_AUDIT_REPORT.md` and `SECURITY_REMEDIATION_PLAN.md` in git history.
