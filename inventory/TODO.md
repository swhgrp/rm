# Inventory System - TODO

**Last Updated:** December 25, 2025

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## Outstanding Issues

### P1 - High Priority

- [ ] **Item detail page** - Template created but needs full implementation
- [ ] **Storage areas page** - Template created but needs completion
- [ ] **Export functionality** - Add CSV/Excel/PDF export to reports (currently browser-based only)

### P2 - Medium Priority

- [ ] **Par level alerts** - Email notifications when items drop below par levels
- [ ] **Ordering suggestions** - Auto-generate order recommendations based on par levels
- [ ] **Batch/lot tracking** - Track expiration dates by batch
- [ ] **Barcode scanning** - Mobile barcode input for counting and receiving
- [ ] **Purchase orders** - Create and track POs to vendors

### P3 - Low Priority / Future

- [ ] **Advanced analytics** - Trend analysis, predictive ordering
- [ ] **Supplier portal** - Vendor-facing order submission
- [ ] **Waste reduction AI** - ML-based waste pattern analysis

---

## Known Bugs

*No known critical bugs at this time*

---

## Technical Debt

- [ ] Clean up deprecated `unit_of_measure` string field (replaced by `unit_of_measure_id`)
- [ ] Review and consolidate duplicate master items (ongoing data quality)
- [ ] Items in "Uncategorized" category need proper categorization (96 remaining)

---

## Data Quality Tasks

- [ ] Continue categorizing uncategorized items (96 items)
- [ ] Verify all vendor item codes are accurate
- [ ] Review and merge any remaining duplicate master items
- [ ] Validate unit conversions are set up for all items needing them

---

## UI/UX Enhancements

- [ ] Improved mobile counting interface
- [ ] Quick-add item from count screen
- [ ] Dashboard widget customization
- [ ] Dark mode toggle

---

## Integration Improvements

- [ ] Better error feedback from Integration Hub syncs
- [ ] Real-time inventory updates via WebSocket

---

## POS Integration Enhancements

- [ ] Add more POS systems (currently: Clover, Square, Toast)
- [ ] Improved recipe-based deduction accuracy
- [ ] POS sync status dashboard

---

## Documentation Needed

- [ ] Count session best practices guide
- [ ] Recipe costing walkthrough
- [ ] POS integration setup guides per system
