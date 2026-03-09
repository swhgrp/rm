# Restaurant System Documentation Index

**Last Updated:** 2026-03-08

---

## Quick Start

**New to the system?** Start here:
1. [README.md](README.md) - Project overview, architecture, and getting started
2. [CLAUDE.md](CLAUDE.md) - Developer reference (patterns, commands, feature docs)
3. [docs/guides/USER_GUIDE.md](docs/guides/USER_GUIDE.md) - End user guide
4. [docs/reference/QUICK_REFERENCE.md](docs/reference/QUICK_REFERENCE.md) - Quick reference

---

## Current Status

- **[docs/status/ACCOUNTING_SYSTEM_STATUS.md](docs/status/ACCOUNTING_SYSTEM_STATUS.md)** - Accounting system (~95% complete)
- **[docs/status/INTEGRATION_HUB_STATUS.md](docs/status/INTEGRATION_HUB_STATUS.md)** - Integration Hub (~98% complete)

For all systems status, see the [Feature Completion Reference](#feature-completion-reference) below.

---

## User & Operations Guides

### For End Users
- [docs/guides/USER_GUIDE.md](docs/guides/USER_GUIDE.md) - Accounting system usage and workflows
- [docs/guides/REPORTS_TESTING_GUIDE.md](docs/guides/REPORTS_TESTING_GUIDE.md) - Report generation and testing

### For System Administrators
- [docs/guides/OPERATIONS_GUIDE.md](docs/guides/OPERATIONS_GUIDE.md) - System operations, backup, monitoring
- [docs/guides/INTEGRATION_HUB_DEPLOYMENT.md](docs/guides/INTEGRATION_HUB_DEPLOYMENT.md) - Hub deployment and testing
- [docs/operations/BACKUP_STRATEGY.md](docs/operations/BACKUP_STRATEGY.md) - Backup & disaster recovery (RTO/RPO)
- [docs/operations/MONITORING_GUIDE.md](docs/operations/MONITORING_GUIDE.md) - System monitoring
- [docs/operations/S3_BACKUP_IMPLEMENTATION_PLAN.md](docs/operations/S3_BACKUP_IMPLEMENTATION_PLAN.md) - Optional S3 backup (low priority)

---

## Technical Reference

- [docs/reference/ARCHITECTURE.md](docs/reference/ARCHITECTURE.md) - System architecture and database schema
- [docs/reference/DESIGN_STANDARD.md](docs/reference/DESIGN_STANDARD.md) - UI/UX design standards and styling
- [docs/reference/MIGRATION_NOTES.md](docs/reference/MIGRATION_NOTES.md) - Database migration history
- [docs/reference/QUICK_REFERENCE.md](docs/reference/QUICK_REFERENCE.md) - Common commands and operations

---

## Feature Documentation

### Banking & Reconciliation
- [docs/banking/DECISION_SUMMARY.md](docs/banking/DECISION_SUMMARY.md) - Scope decisions and approach
- [docs/banking/PHASE_1B_COMPLETION_SUMMARY.md](docs/banking/PHASE_1B_COMPLETION_SUMMARY.md) - Phase 1B progress
- [docs/banking/SIMPLIFIED_WORKFLOW_SUMMARY.md](docs/banking/SIMPLIFIED_WORKFLOW_SUMMARY.md) - Current workflow
- [docs/banking/HYBRID_RECONCILIATION_DESIGN.md](docs/banking/HYBRID_RECONCILIATION_DESIGN.md) - Architecture reference
- [docs/banking/DSS_VALIDATION_REPORT.md](docs/banking/DSS_VALIDATION_REPORT.md) - Daily Sales Summary validation
- [docs/banking/BANKING_RECONCILIATION_USER_MANUAL.md](docs/banking/BANKING_RECONCILIATION_USER_MANUAL.md) - User manual
- [docs/banking/ACTUAL_WORKFLOW.md](docs/banking/ACTUAL_WORKFLOW.md) - Actual workflow reference
- [docs/banking/PHASE_1B_TEST_RESULTS.md](docs/banking/PHASE_1B_TEST_RESULTS.md) - Test results

### Events & Calendar
- [docs/events-caldav-calendar-sync.md](docs/events-caldav-calendar-sync.md) - CalDAV setup and sync
- [docs/EVENTS_MODULE.md](docs/EVENTS_MODULE.md) - Events system documentation

### Files & WebDAV
- [docs/files-webdav-sync.md](docs/files-webdav-sync.md) - WebDAV desktop sync guide

### Testing
- [docs/testing/banking_user_test_guide.md](docs/testing/banking_user_test_guide.md) - Banking test scenarios
- [docs/testing/banking_test_summary.md](docs/testing/banking_test_summary.md) - Banking test results
- [docs/testing/DASHBOARD_TEST_RESULTS.md](docs/testing/DASHBOARD_TEST_RESULTS.md) - Dashboard test results

### Security & Tasks
- [SECURITY.md](SECURITY.md) - Security audit findings + remediation tracker (consolidated)
- [TODO.md](TODO.md) - Active task tracking

### Development History
- [docs/development-history.md](docs/development-history.md) - Archived session log

---

## Service READMEs

| Service | Documentation |
|---------|--------------|
| Portal | [portal/README.md](portal/README.md) |
| Inventory | [inventory/README.md](inventory/README.md) |
| HR | [hr/README.md](hr/README.md) |
| Accounting | [accounting/README.md](accounting/README.md) |
| Events | [events/README.md](events/README.md) |
| Integration Hub | [integration-hub/README.md](integration-hub/README.md) |
| Files | [files/README.md](files/README.md) |
| Websites | [websites/README.md](websites/README.md) |
| Maintenance | Separate compose: `maintenance/` |
| Food Safety | Separate compose: `food-safety/` |

---

## Feature Completion Reference

| System | Status | Primary Docs |
|--------|--------|-------------|
| Portal | ~95% | [README](portal/README.md) |
| Inventory | 100% | [README](inventory/README.md) |
| HR | ~95% | [README](hr/README.md) |
| Accounting | ~95% | [Status](docs/status/ACCOUNTING_SYSTEM_STATUS.md) |
| Events | ~99% | [README](events/README.md) |
| Integration Hub | ~98% | [Status](docs/status/INTEGRATION_HUB_STATUS.md) |
| Files | ~85% | [README](files/README.md) |
| Websites | ~90% | [README](websites/README.md) |
| Maintenance | 100% | `maintenance/` |
| Food Safety | 100% | `food-safety/` |
| Mobile (iOS) | Inventory complete | [CLAUDE.md](CLAUDE.md#mobile-app-mar-2026) |
| Mobile (Android) | Planned (KMP) | [CLAUDE.md](CLAUDE.md#mobile-app-mar-2026) |

---

## Archived Documentation

Old planning docs, completion reports, and analysis files from Oct-Nov 2025 have been moved to [docs/archived/](docs/archived/). These are preserved in git history and available for reference but are no longer actively maintained.

---

**Note:** For day-to-day development, use [CLAUDE.md](CLAUDE.md) as the primary reference.
