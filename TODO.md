# Restaurant Management System - Consolidated TODO

**Last Updated:** February 6, 2026

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## 🔥 Immediate Needs (Active Investigation)

### P0 - Investigate Now
- [ ] **Rework Inventory Master Items UOM display** - Current UOM presentation is confusing; need clearer UI for primary count unit vs purchase unit vs cost unit relationships
- [ ] **Why can Inventory edit vendor items?** - Vendor items should be Hub-only; check if Inventory has edit UI that should be removed or redirected to Hub
- [ ] **Check Flap Meat pricing** - Compare pricing in Hub vs Inventory; verify cost propagation is working correctly
- [ ] **Weight-based invoice items** - Need solution for items that come in on invoice by weight (variable quantity); current system assumes fixed units

---

## 🔒 Security Audit Findings (Jan 25, 2026)

Full report: `SECURITY_AUDIT_REPORT.md`

### P0 - Critical Security (Immediate)
- [x] **Rotate exposed OpenAI API key** - ✅ DONE Feb 6 - Rotated key, deleted old keys from OpenAI dashboard
- [x] **Remove hardcoded database credentials** - ✅ DONE Feb 6 - Removed hardcoded defaults from dblink calls, database.py, accounting_sender.py, invoice_parser.py, location_cost_updater.py, portal config.py, inventory config.py. All DB URLs now require env vars.
- [ ] **Encrypt Plaid/Clover API tokens** - Stored plaintext in accounting/models/bank_account.py and pos.py
- [ ] **Add auth to Accounting accounts endpoints** - GET /api/accounts/ has no authentication (accounting/api/accounts.py:54-103)
- [ ] **Fix session cookie security** - Set secure=True in portal/main.py:84
- [ ] **Enable SSL verification** - Disabled in files/api/onlyoffice.py:259 (verify=False)
- [ ] **Fix path traversal in file operations** - String replacement vulnerability in files/api/filemanager.py:971,1093
- [ ] **Remove weak secret key defaults** - portal/config.py and events/core/security.py have placeholder defaults

### P1 - High Security
- [ ] **Add auth to Inventory update endpoint** - inventory/api/inventory.py:270-304 missing authorization
- [ ] **Add auth to check batch preview** - accounting/api/payments.py:289-316 no auth
- [ ] **Add location-based access on HR delete** - hr/endpoints/employees.py:399-421 admin can delete any employee
- [ ] **Protect internal employee endpoint** - hr/endpoints/employees.py:835-862 marked "no auth required"
- [ ] **Fix weak password sync auth** - events/api/auth.py:151-176 uses simple string comparison
- [ ] **Add auth to Hub settings API** - integration-hub/api/settings.py:44-436 exposes email credentials
- [ ] **Fix mass assignment vulnerability** - inventory/api/inventory.py uses setattr without field whitelist
- [ ] **Remove bare except clauses** - integration-hub/services/email_monitor.py:233,309 and accounting/services/csv_parser.py:243,260,284
- [ ] **Fix command injection in CalDAV sync** - events/services/caldav_sync_service.py:285-286
- [ ] **Encrypt email password storage** - integration-hub/services/email_monitor.py:56 stores plaintext
- [ ] **Fix exception info disclosure** - Multiple endpoints expose internal errors to clients
- [ ] **Fix race condition in email processing** - integration-hub/services/email_monitor.py:289-294

### P2 - Medium Security
- [ ] **Enable hCaptcha on public intake form** - Disabled in events/api/public.py:42
- [ ] **Add rate limiting on public endpoints** - events/api/public.py, files/api/shares.py
- [ ] **Remove debug endpoint** - portal/main.py:474-495 exposes user info
- [ ] **Add CSRF protection** - portal/main.py:743-805 missing CSRF tokens
- [ ] **Fix CORS wildcard** - files/core/config.py:26 allows all origins
- [ ] **Fix division by zero risks** - inventory/models/master_item_count_unit.py:101-109, inventory/api/items.py:2161
- [ ] **Add null checks after DB queries** - Multiple files assume .first() returns non-None
- [ ] **Strengthen password validation** - inventory/api/auth.py:375-380 only requires 8 chars
- [ ] **Fix health check info disclosure** - accounting/main.py:172-188 exposes system config
- [ ] **Add file upload validation** - accounting/api/bank_accounts.py missing type/size checks

---

## Outstanding Work by System

### Integration Hub

#### P2 - Medium Priority
- [ ] **Invoice approval workflow** - Multi-step approval for high-value invoices (basic approval exists, needs value-based thresholds)
- [ ] **Location Cost Grid** - View/compare costs across locations

#### P3 - Low Priority / Future
- [ ] **Advanced duplicate detection** - Cross-invoice matching for credits/adjustments (invoice-level detection done)
- [ ] **Vendor API integration** - Connect to vendor portals (US Foods, Sysco) - aspirational

#### UI/UX Enhancements
- [ ] Dashboard charts for invoice volume trends
- [ ] Mobile-responsive invoice detail view (Bootstrap responsive exists, not fully optimized)

#### Technical Debt
- [ ] Clean up orphaned invoice items from deleted invoices (cascade delete works, no cleanup job)
- [ ] Review webhook endpoint (stub only, not functional)
- [ ] Consider moving to Celery for background processing (currently APScheduler)
- [ ] Clear stale error messages after successful sync

#### Data Quality
- [ ] Process remaining OCR matches requiring manual review
- [ ] Add vendor items for Gold Coast Beverage, Southern Glazier's if needed

---

### Inventory

#### P1 - High Priority
- [x] ~~**UOM Architecture Consolidation**~~ ✅ **DONE Jan 18** - Merged into single `MasterItemCountUnit` model with primary + secondary units, conversion factors, individual specs, and unified UI
- [ ] **Export functionality** - Add Excel/PDF export to reports (CSV done, Excel/PDF needed)

#### P2 - Medium Priority
- [ ] **Barcode scanning** - Mobile barcode capture interface (fields exist, mobile UI incomplete)
- [ ] **POS sync status dashboard** - Add sync monitoring to dashboard

#### P3 - Low Priority / Future
- [ ] **Advanced analytics** - Trend analysis, predictive ordering
- [ ] **Supplier portal** - Vendor-facing order submission
- [ ] **Waste reduction AI** - ML-based waste pattern analysis
- [ ] **Add more POS systems** - Square and Toast defined but not implemented (Clover done)

#### Technical Debt
- [x] ~~Remove deprecated models~~ ✅ **DONE Jan 19** - Removed `_deprecated/` folders (Invoice, VendorItem, VendorAlias models moved to Integration Hub)
- [ ] Clean up deprecated `unit_of_measure` string field (marked deprecated, not removed)
- [ ] Review and consolidate duplicate master items (ongoing data quality)
- [ ] Items in "Uncategorized" category need proper categorization

#### UI/UX Enhancements
- [ ] Improved mobile counting interface (responsive template exists, not mobile-optimized)
- [ ] Quick-add item from count screen (edit exists, full add incomplete)
- [ ] Dashboard widget customization
- [ ] Dark mode toggle (infrastructure only, not functional)

---

### Accounting

#### P2 - Medium Priority
- [ ] **Multi-year budget planning** - Support for budgets spanning multiple fiscal years
- [ ] **Forecasting and projections** - Predictive analytics based on historical data
- [ ] **Fixed asset management** - Depreciation schedules and asset tracking
- [ ] **Advanced consolidation** - Multi-entity consolidated reporting with eliminations

#### P3 - Low Priority / Future
- [ ] **Job costing** - Track costs by job/project
- [ ] **Project accounting** - Full project-based accounting module
- [ ] **Advanced variance analysis** - Drill-down variance reports with root cause analysis

#### Technical Debt
- [x] ~~Migrate deprecated `datetime.utcnow()` to `datetime.now(timezone.utc)`~~ ✅ **DONE Jan 19** - Fixed 99 instances across all systems
- [ ] Review and clean up unused API endpoints if any exist

#### Integration Improvements
- [ ] Improve Integration Hub → Accounting sync error handling and retry logic (basic handling exists)
- [ ] Add webhook notifications for journal entry status changes

#### UI/UX Enhancements
- [ ] Dashboard widget customization (user preferences)
- [ ] Dark/light theme toggle (currently light only)
- [ ] Keyboard shortcuts for common operations
- [x] ~~Replace remaining JavaScript alerts() with Bootstrap modals~~ ✅ **DONE Jan 19**

---

### Websites

#### P1 - High Priority
- [ ] **Static site generation** - Actually generate static HTML files for hosting (stub endpoints exist, no generator code)
- [ ] **Email notifications** - Send alerts on new form submissions

#### P2 - Medium Priority
- [ ] **Sitemap generation** - Auto-generate sitemap.xml
- [ ] **Custom themes** - Beyond just color/font customization (basic color/font done)
- [ ] **Analytics integration** - Inject Google Analytics tracking code (field storage only)
- [ ] **Gallery block rendering** - Gallery block listed but not rendering in preview template

#### P3 - Low Priority / Future
- [ ] **A/B testing** - Test different page variants
- [ ] **Content scheduling** - Schedule content changes
- [ ] **Multi-language** - Internationalization support
- [ ] **Blog/news module** - Simple blog functionality

#### UI/UX Enhancements
- [ ] Better block editor (visual WYSIWYG)
- [ ] Image cropping in gallery (resize only, no crop)
- [ ] Undo/redo for content changes (no revision history)

---

### Portal

#### P2 - Medium Priority
- [ ] **Failed login tracking** - Lock accounts after X failed attempts
- [ ] **Two-factor authentication (2FA)** - TOTP or SMS-based 2FA

#### P3 - Low Priority / Future
- [ ] **User self-registration** - Allow users to request access
- [ ] **Session management UI** - View/revoke active sessions
- [ ] **Login history** - View login attempts per user
- [ ] **SSO with external providers** - Google, Microsoft SSO

#### Technical Debt
- [ ] Add session token rotation on sensitive actions (time-based only currently)

#### UI/UX Enhancements
- [ ] Dashboard widget customization
- [ ] User preferences (theme, layout)
- [ ] Quick links to frequently used features
- [ ] Notification center

#### Monitoring
- [ ] Email alerts for service failures
- [ ] Historical uptime tracking (real-time only, no history storage)
- [ ] Performance metrics graphs (numbers only, no charts)

---

### HR

#### P2 - Medium Priority
- [ ] **Onboarding workflows** - Guided new hire setup with document checklist
- [ ] **Document expiration email alerts** - Automated email notifications when certs expire (tracking exists, no email automation)
- [ ] **Performance review system** - Basic review tracking (beyond just uploading PDFs)
- [ ] **Training tracking** - Track certifications and training completions

#### P3 - Low Priority / Future
- [ ] **Benefits tracking** - Basic benefits enrollment info (not processing)
- [ ] **PTO/Leave tracking** - Manual leave balance tracking
- [ ] **Equipment assignment** - Track assigned equipment per employee
- [ ] **Disciplinary tracking** - Document disciplinary actions (document types exist, no tracking system)

#### UI/UX Enhancements
- [ ] Employee photo upload and display
- [ ] Org chart visualization

#### NOT Planned (Out of Scope)
- Time clock / punch in-out
- Shift scheduling
- Payroll processing / calculation
- Tax calculations / W-2 generation

---

### Events

#### P2 - Medium Priority
- [ ] **Audit logs** - Populate audit trail (model exists, not being written to)
- [ ] **Menu builder UI** - Visual menu editor (currently JSON storage only)

#### P3 - Low Priority / Future
- [ ] **Advanced reporting** - Event analytics and revenue reports
- [ ] **Celery background jobs** - For email sending and CalDAV sync (using async/await)

#### Technical Debt
- [ ] Consolidate Location and Venue tables (two separate tables exist)
- [ ] Clean up deprecated `location` text field in events and quick_holds

#### UI/UX Enhancements
- [ ] Event cloning/duplication feature
- [ ] Bulk event operations (status change, delete)
- [ ] Better mobile calendar view
- [ ] Custom calendar themes per venue

#### Integration
- [ ] Integration with Accounting for event deposits/payments

---

### Files

#### P2 - Medium Priority
- [ ] **File versioning** - Track file version history on updates
- [ ] **Trash/Recycle bin** - Soft delete with recovery option
- [ ] **Storage quotas** - Per-user storage limits (usage calculated, not enforced)
- [ ] **Full-text file search** - Search within document contents (name-based search done)

#### P3 - Low Priority / Future
- [ ] **S3 backend option** - Cloud storage for scalability
- [ ] **File comments** - Discussion threads on files (permission flag exists, no threads)
- [ ] **Activity feed** - Recent activity across all files (share logs only)

#### Technical Debt
- [ ] Consider consolidating file metadata DB with HR database connection
- [ ] Review and clean up any orphaned files on filesystem

#### UI/UX Enhancements
- [ ] Grid view option (in addition to list view)
- [ ] Thumbnail previews for images (full preview works, no thumbnails in list)
- [ ] Keyboard shortcuts (Ctrl+C, Ctrl+V, etc.)

#### OnlyOffice
- [ ] Collaborative editing (real-time co-authoring) - single-user editing only
- [ ] Form/signature support

---

### Maintenance

#### Future Enhancements (Phase 9+)
- [ ] Equipment documents & photos (Files service integration) - URL configured, no integration
- [ ] Depreciation tracking & reports
- [ ] Maintenance checklists with sub-tasks (basic checklist JSON exists)
- [ ] Equipment meter tracking (hours, cycles)
- [ ] Mobile-optimized issue reporting
- [ ] Email notifications (assignments, completions)
- [ ] Warranty expiration alerts (field exists, no alerting)
- [ ] Equipment transfer workflow (ownership types exist, no transfer flow)
- [ ] Accounting integration (GL entries)
- [ ] Events calendar integration
- [ ] Bulk equipment import
- [ ] QR code batch printing (PDF) - QR codes exist, no batch PDF

---

## Cross-System Items

### Immediate Priority
- [x] ~~**Replace remaining JavaScript alerts() with Bootstrap Modals**~~ ✅ **DONE Jan 19** - Replaced 182 alert() calls across 29 files with Bootstrap modal notifications

### Documentation Needed
- [ ] Employee onboarding guide for managers (HR)

---

## Recently Completed (Reference)

### January 2026
- [x] **Customer Invoice System Overhaul** (Accounting) - Jan 29: Fixed invoice creation 422 errors (field name mismatches), added detail/print page, professional PDF with location branding, draft editing with line item replacement, draft/void deletion, Post vs Email separation, AR GL service account number fixes, customer name in API response, Bootstrap confirm dialogs
- [x] **Clover POS Discount Sync Fix** (Accounting) - Jan 26: Fixed discount calculation for percentage-based discounts, added rounding adjustment for variances, prevented double-counting of order vs line-item discounts
- [x] **Discount Edit Saving Fix** (Accounting) - Jan 26: Fixed discount edits not saving to journal entries - added discount_breakdown to save payload and made verify save first
- [x] **Refund Breakdown by Category** (Accounting) - Jan 26: Track refunds by original sale category for accurate journal entries - new refund_breakdown JSONB column
- [x] **Daily Sales UI Cleanup** (Accounting) - Jan 26: Removed redundant Tax column from Sales Categories tab, fixed discount amounts to always show 2 decimal places
- [x] **Vendor Item Creation Fix** (Hub) - Jan 25: Fixed 500 error when creating vendor items - database constraint mismatch for `units_per_case` and `purchase_unit_id` columns
- [x] **Count Units Update Fix** (Inventory) - Jan 25: Fixed 500 error when updating master item count units - removed invalid `hub_uom_id` references
- [x] **Vendor Parsing Rules** (Hub) - Jan 25: Added vendor-specific invoice parsing rules system with AI prompt customization, column identification, and pack size format hints
- [x] **Check Batch View Details Fix** (Accounting) - Jan 23: Fixed 403 error on View Details button for completed check batches
- [x] **MICR Line Format Fix** (Accounting) - Jan 23: Corrected MICR line field order to banking standard (Routing, Account, Check Number)
- [x] **Invoice Upload AI Parsing** (Hub) - Jan 21: Replaced manual upload form with AI-powered PDF parsing (same as email invoices). Uploads now show review page with parsed data and inline PDF viewer
- [x] **Check Printing Fixes** (Accounting) - Jan 21: Fixed NoneType decode error in ReportLab PDF generation, added PATCH endpoint for check batches, Bootstrap modals for confirmations, default status filter to Draft
- [x] **Void Bill Journal Entry Handling** (Accounting) - Jan 21: Voiding a bill now marks its journal entry as REVERSED (excludes from reports) instead of creating a reversing entry that could offset other transactions
- [x] **Duplicate Invoice Prevention** (Hub) - Jan 21: Added vendor+invoice number duplicate check on invoice upload to prevent accidental duplicates
- [x] **Codebase Cleanup** (All Systems) - Jan 19: Removed deprecated files, replaced 182 JavaScript alerts with Bootstrap modals, fixed 99 datetime.utcnow() calls, removed commented code, fixed hardcoded user_id=1 security issue, added system timezone settings
- [x] **System Settings Page** (Portal) - System-wide timezone configuration with database persistence
- [x] **UOM Architecture Consolidation** (Inventory) - Merged `item_unit_conversions` into `master_item_count_units`, unified UI, dimension filtering
- [x] Recipe ingredient searchable dropdown (Inventory) - Tom Select integration with all master items
- [x] Recipe unit dropdown (Inventory) - Dynamic unit selection based on item's count units
- [x] Recipe costing from Hub pricing (Inventory) - Fetches cost from hub_vendor_items
- [x] UOM architecture research (Inventory) - Analyzed MarketMan, Restaurant365, meez, COGS-Well, xtraCHEF, etc.
- [x] Invoice 217 re-parse issue resolved (Hub) - Invoice deleted during cleanup
- [x] E-Signature Template Field Editor (HR)
- [x] Maintenance System - Full implementation (Phases 1-8)
- [x] CalDAV Bidirectional Sync (Events) - Two-way sync implemented
- [x] SSL Certificate Renewal
- [x] Hub Vendor Merge Feature API + Push to Systems
- [x] Duplicate Bill Detection (Accounting)
- [x] Payment Method Validation Fix (Accounting)
- [x] Auto-logout redirect fix (Portal → Accounting)
- [x] Storage areas database migration (Inventory) - display_order implemented
- [x] Bank feed automation (Accounting) - Plaid integration complete
- [x] Budget variance alerts (Accounting) - Model and configuration done
- [x] SEO meta tags (Websites) - Page/site-level meta implemented
- [x] Preview mode (Websites) - Fully implemented
- [x] Password reset via email (Portal) - Full flow implemented
- [x] JWT expiration policies (Portal) - Configurable, enforced
- [x] Exit interview tracking (HR) - Full implementation with emails
- [x] Quick employee lookup (HR) - Client-side search
- [x] Field encryption (HR) - Comprehensive with fallback
- [x] Mobile document viewer (HR) - Responsive preview
- [x] UI role-based hiding (Events) - Permission-based access control
- [x] Document versioning (Events) - Version tracking implemented
- [x] HR Integration (Events) - User sync from HR
- [x] S3 storage configuration (Events) - S3 configured
- [x] File search (Files) - Name-based with filters
- [x] Advanced sharing (Files) - Department/role/location sharing
- [x] Upload progress indicator (Files) - Real-time XHR progress
- [x] Document templates (Files) - Word/Excel/PowerPoint blanks
- [x] Batch processing UI (Hub) - 6+ batch operations implemented
- [x] Cost Propagation (Hub) - Weighted average with audit trail
- [x] ML item mapping (Hub) - OpenAI embeddings + cosine similarity
- [x] Vendor item auto-creation (Hub) - create_from_invoice_item() implemented
- [x] Invoice PDF preview (Hub) - Basic implementation
- [x] Recipe-based deduction (Inventory) - Fully implemented

### December 2025
- [x] Location-aware costing refactor (Hub + Inventory)
- [x] Vendor items UI update with location-based pricing
- [x] Location sync architecture (Inventory as source of truth)
- [x] OCR accuracy improvements - 99.5% mapping rate (Hub)
- [x] Duplicate invoice detection and cleanup UI (Hub)
- [x] Item detail page - full implementation (Inventory)
- [x] UOM + Pricing Model Refactor (Hub)
- [x] Invoice Batch Operations API (Hub)
- [x] Reporting Dashboard API (Hub)

### Documentation Complete
- [x] End-user documentation for year-end close process (Accounting README)
- [x] Invoice workflow documentation (Hub README)
- [x] GL mapping best practices (Hub README)
- [x] Event workflow documentation (Events README)
- [x] Site setup guide (Websites README)
