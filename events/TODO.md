# Events System - TODO

**Last Updated:** December 25, 2025

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## Outstanding Issues

### P2 - Medium Priority

- [ ] **UI role-based hiding** - Hide buttons/features users don't have permission for (API enforcement works, UI shows everything)
- [ ] **Document versioning** - Complete version history tracking and UI (database model exists, logic incomplete)
- [ ] **Audit logs** - Populate audit trail (model exists, not being written to)
- [ ] **Menu builder UI** - Visual menu editor (currently JSON storage only)

### P3 - Low Priority / Future

- [ ] **HR Integration** - Sync users from HR system automatically (currently via Portal SSO only)
- [ ] **S3 storage** - Move file storage to S3 (currently local filesystem)
- [ ] **Advanced reporting** - Event analytics and revenue reports
- [ ] **Celery background jobs** - For email sending and CalDAV sync

---

## Known Bugs

*No known critical bugs at this time*

---

## Technical Debt

- [ ] Consolidate Location and Venue tables (currently two separate tables with same names but different UUIDs)
- [ ] Clean up deprecated `location` text field in events (replaced by `venue_id`)

---

## UI/UX Enhancements

- [ ] Event cloning/duplication feature
- [ ] Bulk event operations (status change, delete)
- [ ] Better mobile calendar view
- [ ] Custom calendar themes per venue

---

## Integration Improvements

- [ ] Two-way CalDAV sync (currently push-only to Radicale)
- [ ] Integration with Accounting for event deposits/payments

---

## Documentation Needed

- [ ] Event workflow documentation for end users
- [ ] BEO customization guide
- [ ] CalDAV setup guide for new users
