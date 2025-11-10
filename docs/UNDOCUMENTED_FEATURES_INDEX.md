# Complete Index of Undocumented Features
## Restaurant Management System - November 9, 2025

---

## PORTAL SYSTEM (14 Undocumented Items)

### User Management Features
1. **User Profile Management**
   - GET `/profile` - User profile page
   - POST `/api/profile/update` - Update full name and email
   - Email validation and uniqueness checking
   - **Status:** Fully implemented, not documented

2. **Password Change System**
   - GET `/change-password` - Password change UI
   - POST `/api/change-password` - Change password with validation
   - Enforces 8+ character minimum
   - **Status:** Fully implemented, incorrectly marked as "Missing" in README

3. **Cross-System Password Synchronization**
   - Syncs password changes to Inventory and Accounting systems
   - Uses X-Portal-Auth header for internal authentication
   - Returns sync status for each system
   - **Status:** Fully implemented, completely undocumented

4. **Session Auto-Refresh Middleware**
   - Automatically refreshes tokens when <10 minutes remaining
   - Extends session transparently to user
   - Implements 30-minute idle timeout with automatic refresh
   - **Status:** Fully implemented, completely undocumented

### Mail System Features
5. **Mail Gateway Proxy**
   - GET `/mail-gateway/` - Root mail gateway
   - API `/mail-gateway/{path:path}` - Generic proxy to SOGo
   - Supports GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
   - **Status:** Fully implemented, completely undocumented

6. **Mail System Authentication**
   - GET `/api/auth/verify` - Verify mail authentication
   - Returns X-Mail-User header for SOGo
   - Checks can_access_mail permission
   - **Status:** Fully implemented, completely undocumented

7. **Mail Admin Endpoint**
   - GET `/api/auth/verify-admin` - Verify admin mail access
   - Admin-only endpoint for mail administration
   - **Status:** Fully implemented, completely undocumented

8. **Mailbox Provisioning**
   - POST `/api/admin/mail/provision-users` - Create mailboxes for all HR users
   - Integrates with Mailcow API
   - Handles existing mailboxes, creates new ones, tracks failures
   - Returns detailed provisioning results
   - **Status:** Fully implemented, completely undocumented

### System Administration Features
9. **Monitoring Dashboard**
   - GET `/monitoring` - Admin-only real-time monitoring
   - Shows 7 microservices status
   - Database health, backups, SSL certificates
   - Recent alerts and error logs
   - Auto-refresh every 30 seconds
   - **Status:** Fully implemented, vaguely documented

10. **Monitoring Status API**
    - GET `/api/monitoring/status` - JSON status data
    - Calls `/opt/restaurant-system/scripts/dashboard-status.sh`
    - Returns complete system health metrics
    - Includes cache-busting headers
    - **Status:** Fully implemented, not documented

### Debug Endpoints
11. **Debug Endpoint**
    - GET `/debug` - User attribute debugging
    - Returns all user attributes as JSON
    - **Status:** Fully implemented, not documented
    - **Security Note:** No authentication required

### Permission Flags
12. **Mail System Permission**
    - `can_access_mail` - New permission flag
    - Controls access to mail system
    - Added to User model
    - **Status:** Implemented, mentioned in code but not fully documented

---

## ACCOUNTING SYSTEM (40+ Undocumented Items)

### Framework & Architecture
1. **Framework Mismatch (CRITICAL)**
   - README states: Django 4.2
   - Code actually uses: FastAPI with SQLAlchemy
   - Uses Alembic for migrations, not Django migrations
   - No manage.py or Django project structure
   - **Impact:** CRITICAL - Developers will be confused

### Database Models (25+ Undocumented)

**Sync & Integration Models:**
- `InventorySyncLog` - Tracks syncs from inventory system
- `SyncStatus` - Enum: PENDING, SUCCESS, FAILED, PARTIAL

**GL Learning & AI Models:**
- `VendorGLMapping` - AI-powered vendor to GL mapping
- `DescriptionPatternMapping` - Pattern learning from descriptions
- `RecurringTransactionPattern` - Recurring transaction ML detection

**Cost & COGS Models:**
- `COGSTransaction` - Cost of goods sold tracking
- `TransactionType` - Enum for transaction types

**Banking Models:**
- `DailyCashPosition` - Daily cash position tracking
- `CashFlowTransaction` - Cash flow modeling
- `BankingAlert` - Alerts for banking operations
- `ReconciliationHealthMetric` - Bank reconciliation health scoring
- `BankStatementSnapshot` - Bank statement snapshots
- `BankMatchingRuleV2` - Advanced transaction matching rules
- `BankCompositeMatch` - Complex transaction matching

**Dashboard & Analytics Models:**
- `DailyFinancialSnapshot` - Daily financial snapshots
- `MonthlyPerformanceSummary` - Monthly aggregations
- `DashboardAlert` - Dashboard alert system
- `ExpenseCategorySummary` - Expense analysis by category
- `LocationCashFlowSummary` - Cash flow by location

**Payment Processing Models:**
- `PaymentSchedule` - Payment scheduling system
- `PaymentApproval` - Multi-level payment approvals
- `PaymentDiscount` - Early payment discount tracking
- `CheckBatch` - Check batch processing
- `ACHBatch` - ACH batch processing
- `CheckNumberRegistry` - Check number management

**Budget Management Models:**
- `BudgetTemplate` - Reusable budget templates
- `BudgetTemplateLine` - Budget template line items
- `BudgetRevision` - Budget revision tracking
- `BudgetAlert` - Budget variance alerts

**POS Integration Models:**
- `POSConfiguration` - POS system configuration
- `POSDailySalesCache` - POS sales caching
- `POSCategoryGLMapping` - POS category to GL mapping

**Other Models:**
- `SafeTransaction` - Safe/cash drawer tracking
- `SystemSetting` - System configuration storage

### API Endpoints (150+ Across 28 Route Files)

**Known Route Files:**
- `accounts.py` - Account management
- `journal_entries.py` - Journal entry posting
- `vendors.py` - Vendor management
- `bank_accounts.py` - Bank account management
- `bank_reconciliation.py` - Bank reconciliation
- `bank_statements.py` - Bank statement processing
- `banking_dashboard.py` - Banking dashboard
- `payments.py` - Payment processing
- `pos.py` - POS integration
- `daily_sales_summary.py` - Daily sales
- `areas.py` - Department/area codes
- `safe.py` - Safe/cash drawer management
- `general_dashboard.py` - General accounting dashboard
- `customers.py` - Customer management
- `budgets.py` - Budget management
- `roles.py` - Role-based access control
- `users.py` - User management
- `auth.py` - Authentication
- `fiscal_periods.py` - Period management
- `ap_reports.py` - Accounts payable reporting
- `composite_matching.py` - Advanced bank matching
- `ar_gl_service.py` - AR-specific GL service
- + 6 additional route files

### Services & Features (Not Documented)

**Banking Automation:**
- `plaid_service.py` - Plaid bank integration
- `csv_parser.py` - CSV bank statement parsing
- `ofx_parser.py` - OFX bank statement parsing
- `bank_matching.py` - Automatic transaction matching
- `transaction_matcher.py` - Advanced matching logic

**Payment Generation:**
- `check_printer.py` - Check PDF generation
- `ach_generator.py` - ACH file generation

**Analytics & Monitoring:**
- `dashboard_service.py` - General dashboard calculations
- `health_metrics_service.py` - Health metric calculations
- `alert_service.py` - Alert generation

**ML/AI Features:**
- `gl_learning_service.py` - Machine learning for GL suggestions

**POS Integration:**
- `pos_sync_service.py` - POS synchronization

### Schema Definitions (Not Documented)

- `gl_suggestion.py` - GL account suggestions
- `banking_dashboard.py` - Dashboard schemas
- `cash_flow.py` - Cash flow statement schema
- `composite_match.py` - Transaction matching schema
- `bank_statement.py` - Bank statement import schema
- `safe_transaction.py` - Safe transaction schema

---

## EVENTS SYSTEM (3 Minor Undocumented Items)

1. **Location/Venue Dual Table System**
   - Two separate location tables for different purposes
   - `locations` table - Settings, used by calendar items
   - `venues` table - Events, used by event records
   - **Status:** Fully implemented, only briefly documented

2. **Email Notification Routing**
   - Location-based routing to staff users
   - `{location_users}` variable support
   - Auto-routing confirmed events to venue staff
   - Changed from client-only emails to internal routing
   - **Status:** Fully implemented, documented in recent updates

3. **Custom Dialog System**
   - Branded dialogs replacing browser confirm/alert
   - Dark theme styled modals
   - No "rm.swhgrp.com says" messages
   - **Status:** Fully implemented, not prominently documented

---

## INVENTORY SYSTEM
✅ **No undocumented features** - Fully documented as of November 3, 2025

---

## HR SYSTEM
✅ **No undocumented features** - Fully documented as of October 30, 2025

---

## INTEGRATION HUB SYSTEM
✅ **No undocumented features** - Fully documented as of November 8, 2025

---

## FILES SYSTEM
✅ **No undocumented features** - Fully documented as of October 29, 2025

---

## SUMMARY STATISTICS

| System | Undocumented | Total Features | Completion | Last Updated |
|--------|---|---|---|---|
| **Portal** | 14 | ~40 | 85% | Nov 8 |
| **Accounting** | 40+ | ~250 | 60% | Oct 31 |
| **Events** | 3 | ~100 | 99% | Nov 9 |
| **Inventory** | 0 | ~200 | 100% | Nov 3 |
| **HR** | 0 | ~50 | 100% | Oct 30 |
| **Integration Hub** | 0 | ~80 | 100% | Nov 8 |
| **Files** | 0 | ~60 | 100% | Oct 29 |
| **TOTAL** | **57** | **~680** | **~82%** | **Nov 9** |

---

## DOCUMENTATION MAINTENANCE RECOMMENDATIONS

1. **Update During Development**
   - Modify README when adding new endpoints
   - Document new models in architecture section
   - Use automated tools (Swagger/OpenAPI) for API docs

2. **Regular Audits**
   - Quarterly review of code vs documentation
   - Use this index as baseline for future checks
   - Track documentation debt

3. **Code Organization**
   - Consider separating mail system (Portal feature)
   - Consider separating monitoring (Admin feature)
   - Keep related features in same service

---

**Report Generated:** November 9, 2025  
**Comprehensive Analysis:** `/opt/restaurant-system/docs/CODEBASE_ANALYSIS_NOV9_2025.md`  
**Critical Issues:** `/opt/restaurant-system/docs/CRITICAL_FINDINGS_SUMMARY.md`

