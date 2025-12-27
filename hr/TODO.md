# HR System - TODO

**Last Updated:** December 25, 2025

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## Important Note

This is an **employee information management system**, NOT a full HRIS. It intentionally does NOT include scheduling, time tracking, or payroll - those would be separate systems or third-party integrations.

---

## Outstanding Issues

### P2 - Medium Priority

- [ ] **Onboarding workflows** - Guided new hire setup with document checklist
- [ ] **Document expiration alerts** - Email notifications when certs expire (e.g., Food Handler)
- [ ] **Performance review system** - Basic review tracking (beyond just uploading PDFs)
- [ ] **Training tracking** - Track certifications and training completions

### P3 - Low Priority / Future

- [ ] **Benefits tracking** - Basic benefits enrollment info (not processing)
- [ ] **PTO/Leave tracking** - Manual leave balance tracking
- [ ] **Exit interview tracking** - Termination documentation
- [ ] **Equipment assignment** - Track assigned equipment per employee
- [ ] **Disciplinary tracking** - Document disciplinary actions

---

## NOT Planned (Out of Scope)

These features are intentionally NOT planned as they require specialized systems:

- Time clock / punch in-out
- Shift scheduling
- Payroll processing / calculation
- Tax calculations / W-2 generation
- Direct deposit processing
- Timesheet approval workflows

---

## Known Bugs

*No known critical bugs at this time*

---

## Technical Debt

- [ ] Review field encryption implementation for any edge cases
- [ ] Add more comprehensive input validation for employee data

---

## UI/UX Enhancements

- [ ] Employee photo upload and display
- [ ] Org chart visualization
- [ ] Better mobile document viewer
- [ ] Quick employee lookup search

---

## Integration Improvements

- [ ] Events system user sync (currently via Portal SSO)
- [ ] Consider read-only employee API for other systems

---

## Documentation Needed

- [ ] Employee onboarding guide for managers
- [ ] Document type requirements guide
- [ ] RBAC permissions reference
