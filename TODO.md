# TODO — Active Tasks

**Last Updated:** March 8, 2026

**Security items** tracked separately in [SECURITY.md](SECURITY.md).

---

## P0 — Investigate / Active

- [ ] **Rework Inventory Master Items UOM display** — Clearer UI for primary count unit vs purchase unit vs cost unit
- [ ] **Why can Inventory edit vendor items?** — Should be Hub-only; check if edit UI should be removed
- [ ] **Check Flap Meat pricing** — Compare Hub vs Inventory; verify cost propagation
- [ ] **Weight-based invoice items** — Need solution for variable-weight items on invoices

---

## P1 — High Priority

### Integration Hub
- [ ] Invoice approval workflow — Value-based thresholds for high-value invoices
- [ ] Location Cost Grid — View/compare costs across locations

### Inventory
- [ ] Export functionality — Excel/PDF export for reports (CSV done)
- [ ] Barcode scanning — Mobile barcode capture interface

### Websites
- [ ] Static site generation — Generate static HTML for hosting (stub endpoints exist)
- [ ] Email notifications — Alert on new form submissions

---

## P2 — Medium Priority

### Accounting
- [ ] Multi-year budget planning
- [ ] Forecasting and projections
- [ ] Fixed asset management / depreciation
- [ ] Advanced consolidation — Multi-entity with eliminations

### HR
- [ ] Onboarding workflows — Guided new hire setup with document checklist
- [ ] Document expiration email alerts
- [ ] Performance review system
- [ ] Training tracking

### Events
- [ ] Audit logs — Populate audit trail (model exists, not written to)
- [ ] Menu builder UI — Visual editor (currently JSON only)

### Files
- [ ] File versioning — Track version history on updates
- [ ] Trash/Recycle bin — Soft delete with recovery
- [ ] Storage quotas — Per-user limits (usage calculated, not enforced)
- [ ] Full-text file search

### Portal
- [ ] Failed login tracking — Lock after X attempts
- [ ] Two-factor authentication (2FA)

### Websites
- [ ] Sitemap generation
- [ ] Custom themes
- [ ] Analytics integration (GA tracking code)

---

## P3 — Future / Low Priority

### Integration Hub
- [ ] Advanced duplicate detection — Cross-invoice credits/adjustments
- [ ] Vendor API integration — Connect to vendor portals (aspirational)

### Inventory
- [ ] Advanced analytics / trend analysis / predictive ordering
- [ ] Supplier portal — Vendor-facing order submission
- [ ] Additional POS systems — Square and Toast (Clover done)

### Accounting
- [ ] Job costing
- [ ] Advanced variance analysis with drill-down

### Events
- [ ] Event cloning/duplication
- [ ] Accounting integration for deposits/payments

### Maintenance
- [ ] Equipment documents & photos (Files integration)
- [ ] Depreciation tracking
- [ ] Email notifications for assignments/completions
- [ ] QR code batch printing (PDF)

### Files
- [ ] S3 backend option
- [ ] Collaborative editing (OnlyOffice co-authoring)

---

## Technical Debt

- [ ] Clean up deprecated `unit_of_measure` string field in Inventory (marked deprecated)
- [ ] Review/consolidate duplicate master items (ongoing data quality)
- [ ] Items in "Uncategorized" category need proper categorization
- [ ] Hub `UnitDimension` enum still imported in `uom.py` — should use `MeasureType`
- [ ] Consolidate Location and Venue tables in Events
- [ ] Clean up deprecated `location` text field in events/quick_holds
- [ ] Review unused API endpoints across services
