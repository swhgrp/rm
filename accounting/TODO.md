# Accounting System - TODO

**Last Updated:** December 25, 2025

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## Outstanding Issues

### P1 - High Priority

- [ ] **Bank feed automation** - Complete Plaid or similar integration for automatic bank transaction import
- [ ] **Budget variance alerts** - Automated notifications when spending exceeds budget thresholds

### P2 - Medium Priority

- [ ] **Multi-year budget planning** - Support for budgets spanning multiple fiscal years
- [ ] **Forecasting and projections** - Predictive analytics based on historical data
- [ ] **Fixed asset management** - Depreciation schedules and asset tracking
- [ ] **Advanced consolidation** - Multi-entity consolidated reporting with eliminations

### P3 - Low Priority / Future

- [ ] **Job costing** - Track costs by job/project
- [ ] **Project accounting** - Full project-based accounting module
- [ ] **Advanced variance analysis** - Drill-down variance reports with root cause analysis

---

## Known Bugs

*No known critical bugs at this time*

---

## Technical Debt

- [ ] Consider migrating deprecated `datetime.utcnow()` to `datetime.now(timezone.utc)` in any remaining files
- [ ] Review and clean up unused API endpoints if any exist

---

## Integration Improvements

- [ ] Improve Integration Hub → Accounting sync error handling and retry logic
- [ ] Add webhook notifications for journal entry status changes

---

## UI/UX Enhancements

- [ ] Dashboard widget customization (user preferences)
- [ ] Dark/light theme toggle (currently dark only)
- [ ] Keyboard shortcuts for common operations

---

## Documentation Needed

- [ ] End-user documentation for year-end close process
- [ ] API documentation improvements (auto-generated but could use examples)
