# SW Hospitality Group — Accounting Daily Review Spec
_Last updated: 2026-03-26_

## Purpose
This document defines the daily automated review Claude Code performs across the
Accounting, Integration Hub, and Inventory services. It is the authoritative source
of truth for what constitutes an anomaly, a duplicate, a GL error, and when an
auto-correction is permitted. Claude Code reads this document at the start of every
review session and does not proceed until it has been read in full.

---

## Database Access

Use the existing session/connection patterns already established in each service.
Do not create new connection strings or reference environment variables that aren't
already defined in the codebase.

- Accounting DB: `src/accounting/database.py`
- Integration Hub DB: `src/hub/database.py`
- Inventory DB: `src/inventory/database.py`

All queries are **read-only** unless explicitly authorized in Sections 7 or 8 of this spec.

---

## PDF Access

PDFs are accessible via:
1. **Direct path** (preferred for performance): path stored in `invoices.pdf_path` on the shared Docker volume
2. **Files service API** (fallback): `GET http://files:8000/api/files/{file_id}/download`

Use direct path access during batch review. Fall back to the Files service API only
if the direct path is missing or inaccessible. If both fail, log the failure and
flag the invoice — do not attempt to correct it.

OCR re-read pattern: `src/hub/services/ocr_service.py`
When re-reading a PDF for verification, extract only the specific field in question.
Do not re-process the entire invoice.

---

## Review Window

Default: last **48 hours** (`NOW() - INTERVAL '48 hours'`).
The 48-hour window ensures late-processing invoices and overnight GL postings
are captured even when the review runs early morning.

---

## Section 1 — Invoice Accuracy Review (Hub → Accounting)

### What to Query
- `invoices` table in Hub DB: all records with `status = 'processed'` and
  `created_at >= NOW() - INTERVAL '48 hours'`
- `invoice_line_items` joined to `master_items` via `vendor_items`
- `gl_entries` in Accounting DB linked to each invoice

### OCR / Parse Quality Checks

| Check | Flag When |
|---|---|
| Unit price outlier | `unit_price` deviates >40% from 90-day avg for that `vendor_item_id` |
| Quantity implausible | `quantity <= 0` or `quantity > 500` (review per category if needed) |
| Total mismatch | `SUM(line_items.extended_price)` differs from `invoice.total` by >$0.10 |
| Missing line items | `invoice.line_item_count != COUNT(invoice_line_items)` for that invoice |
| Tax double-count | Invoice GL entries contain both a dedicated tax line AND tax embedded in item costs |
| Vendor mismatch | `invoice.vendor_id` doesn't match the vendor on the source PDF filename pattern |
| Round number flag | All line items are suspiciously round numbers — possible OCR fill-in |
| Unknown item code | `vendor_item_code` on a line item has no match in `vendor_items` for that vendor |
| Description mismatch | Item description on line item doesn't match `vendor_items.description` for the matched code |

---

## Section 2 — GL Entry Verification (Accounting DB)

### What to Query
- `gl_entries` and `journal_entries` where `entry_date >= NOW() - INTERVAL '48 hours'`
- `gl_accounts` for account metadata
- `gl_anomaly_flags` for any flags already raised by the nightly anomaly engine

### GL Integrity Checks

| Check | Flag When |
|---|---|
| Unbalanced journal entry (AP) | Debits ≠ credits for any vendor bill journal entry (`reference_type = 'VENDOR_BILL'`) |
| Unbalanced journal entry (DSS) | Debits ≠ credits for any daily sales summary journal entry (`reference_type = 'SALE'`) |
| Unbalanced journal entry (other) | Debits ≠ credits for any other POSTED journal entry (manual, adjustment, payment) |
| Wrong account type | COGS entry posted to a liability account, revenue posted to expense, etc. |
| Missing reference | `gl_entry` has no `source_document_id` (invoice, payroll run, etc.) |
| Inactive account used | `gl_account.status = 'inactive'` but received a posting |
| Negative balance asset | Asset account has a credit balance (possible reversal error) |
| Large manual entry | Manual (non-system) journal entry > $5,000 — flag for human review |
| Cross-location posting | Entry's `location_id` doesn't match the source document's `location_id` |
| Corporate area on AP bill | Vendor bill journal entry has `area_id = 7` (SW Hospitality Group / Corporate) — AP bills should always be location-specific (area 1–6) |

### Overlap with GL Anomaly Engine
Pull any `gl_anomaly_flags` with `status = 'open'` not already in a prior report.
Include their existing AI reasoning in the output. Do not re-run AI analysis on
already-flagged items — surface them as-is with their original reasoning attached.

---

## Section 3 — Inventory Cost Consistency

### What to Query
- `master_item_location_costs` and `master_item_location_cost_history` in Inventory DB
- Cross-reference against Hub invoice line items processed in the same 48-hour window

### Checks

| Check | Flag When |
|---|---|
| Cost not updated | Invoice processed in Hub but `MasterItemLocationCost.last_updated` not refreshed within 2 hours of invoice processing |
| Cost spike | New cost > 150% of previous cost for same item/location |
| Orphaned cost record | `MasterItemLocationCost` exists for an item with no purchases in 90 days |

---

## Section 4 — Duplicate Payment / Disbursement Check

Query payment records and AP disbursements in Accounting DB within the 48-hour window.

| Check | Flag When |
|---|---|
| Same-vendor duplicate payment | Same `vendor_id` + same amount + within 7 days |
| Payment with no invoice | Payment record exists with no matching invoice in Hub |
| Both invoices paid | Duplicate invoice pair where BOTH records show payment (possible real double payment — escalate) |

---

## Section 5 — Clover Sales Accuracy (Existing Routine)

Continue the existing Clover pull verification routine without modification.
Results should appear in the same daily report under their own section.

---

## Section 5A — Hub ↔ Accounting Sync Reconciliation

### What to Query
- `hub_invoices` in Hub DB where `sent_to_accounting = true`
- `vendor_bills` in Accounting DB where `reference_number LIKE 'HUB-%'`
- `vendor_bill_lines` joined to `vendor_bills`
- `journal_entry_lines` joined to `journal_entries` via `vendor_bills.journal_entry_id`

### Checks

| Check | Flag When | Severity |
|---|---|---|
| Vendor bill lines vs bill total | `SUM(vendor_bill_lines.amount)` differs from `vendor_bills.total_amount` by >$0.10 for any non-VOID bill | Critical 🔴 |
| JE imbalance (all types) | `SUM(debit_amount) != SUM(credit_amount)` for any POSTED journal entry — includes AP bills, DSS sales entries, manual JEs, and adjustments | Critical 🔴 |
| Hub sent but no accounting bill | Hub invoice has `sent_to_accounting = true` but no matching `vendor_bill` with `reference_number = 'HUB-{invoice_id}'` and `status != 'VOID'` | Critical 🔴 |
| Accounting bill but Hub not marked sent | `vendor_bill` exists with `reference_number = 'HUB-{id}'` but Hub invoice has `sent_to_accounting = false` | Warning 🟡 |
| Total mismatch Hub vs Accounting | Hub `total_amount` differs from Accounting `vendor_bills.total_amount` for same invoice | Critical 🔴 |
| Duplicate vendor bills | Same `bill_number + vendor_id` appears on multiple non-VOID vendor bills | Critical 🔴 |

### Why This Section Exists
In March 2026 we discovered 81 vendor bills where the Hub sent `invoice.total_amount`
as every GL line amount instead of per-account grouped amounts, creating $54K in
inflated debit lines. We also found 7 duplicate vendor bills from sync retries.
These checks prevent both issues from recurring.

---

## Section 5B — Invoice Pipeline Health

### What to Query
- `hub_invoices` in Hub DB — all statuses

### Checks

| Check | Flag When | Severity |
|---|---|---|
| Stale ready invoices | `status = 'ready'` AND `sent_to_accounting = false` AND invoice has been in `ready` status for >24 hours | Warning 🟡 |
| Missing location | `status IN ('ready', 'sent', 'needs_review')` AND `location_id IS NULL` | Critical 🔴 — accounting cannot post without a location |
| Statement misclassification | `is_statement = true` AND invoice has >0 mapped line items AND `total_amount != 0` | Warning 🟡 |
| Stuck in needs_review | `status = 'needs_review'` for >72 hours without human action | Warning 🟡 |
| Credit memo without lines | `total_amount < 0` AND `COUNT(hub_invoice_items) = 0` AND `status != 'statement'` | Warning 🟡 |

---

## Section 5C — Beverage Distributor Pricing Validation

### Known Beverage Distributors
- Southern Glazer's (all name variants including "Southern Glaziers")
- Southern Eagle Distributing
- Gold Coast Beverage (all name variants including "Gold Coast Beverage LLC")
- Breakthru Beverage
- Western Beverage / Eagle Brands Sales
- Republic National Distributing
- J.J. Taylor

### Special Pricing Rules
Beverage distributors use discount pricing where the invoice `line_total` differs
from `quantity × unit_price`. This is normal — distributors apply volume discounts,
promotional pricing, and case break charges that are reflected in the line total
but not in the unit price.

### Checks

| Check | Flag When | Severity |
|---|---|---|
| Line total used correctly | For beverage distributors: `hub_invoice_items.total_amount` should match `raw_data.line_items[].line_total`, NOT `quantity * unit_price`. Flag if `total_amount = ROUND(quantity * unit_price, 2)` AND `raw_data` has a different `line_total` | Warning 🟡 |
| Discount not captured | `raw_data.line_total < quantity * unit_price` by >5% but `total_amount = quantity * unit_price` — the discount was lost | Warning 🟡 |

### Exception to Type 4 Correction
Do **NOT** apply Correction Type 4 (Extended Price Math Error) to beverage distributor
invoices. For these vendors, `total_amount != quantity * unit_price` is expected and
correct. The raw invoice line total is authoritative, not the computed value.

---

## Section 5D — Linen Service Parse Quality (Gold Coast Linen)

### Known Pattern
Gold Coast Linen invoices have a recurring AI parse failure where the parser puts
`line_total` in the `unit_price` field, then Hub computes
`total_amount = quantity × unit_price` producing inflated values.

### Detection Rule
For any Gold Coast Linen invoice item:
- If `unit_price` is approximately equal to `total_amount` AND `quantity > 1`
- OR if `unit_price` is approximately equal to `raw_data.line_items[].line_total`
  for that line position

Then the parser likely swapped `unit_price` and `line_total`.

### Check

| Check | Flag When | Severity |
|---|---|---|
| Price/total swap | `ABS(unit_price - total_amount) < 0.01` AND `quantity > 1` for any Gold Coast Linen item | Critical 🔴 — auto-correctable if raw_data has the correct values |
| Items vs invoice total | For Gold Coast Linen specifically: `SUM(hub_invoice_items.total_amount)` vs `invoice.total_amount - invoice.tax_amount`. Flag if diff > $1.00 | Warning 🟡 |

### Auto-Correction (extends Type 3)
If `raw_data` is available and contains `line_total` for the affected line:
1. Set `total_amount = raw_data.line_items[position].line_total`
2. Recalculate `unit_price = total_amount / quantity`
3. Log as Correction Type 3 variant with `verification_method = 'raw_data_line_total'`

---

## Section 5E — Delivery Fee / Fuel Surcharge Completeness

### What to Query
- `hub_invoice_items` grouped by `hub_invoices.vendor_id`
- Historical delivery charge frequency per vendor

### Detection
For each vendor, compute the percentage of invoices (last 90 days) that include
a delivery-related line item. Delivery items are identified by:
- `item_description` matching: `DELIVERY`, `FUEL SURCHARGE`, `FREIGHT`, `SHIPPING`,
  `TRANSPORTATION`, `HANDLING`
- OR `gl_cogs_account = '7140'` (Vendor Delivery Charge)

### Check

| Check | Flag When | Severity |
|---|---|---|
| Missing expected delivery fee | Vendor has delivery charges on ≥80% of historical invoices, but a new invoice (last 48 hours) has no delivery line item AND `total_amount > $100` | Warning 🟡 |

### Why This Matters
GFS invoices almost always include a fuel surcharge ($5–$8). When the parser misses
it, the line items don't add up to the invoice total, which blocks sending to
accounting. Catching this early prevents invoices from getting stuck in `needs_review`.

---

## Section 6 — Report Format

Write results to: `src/accounting/review_reports/YYYY-MM-DD_daily_review.md`
Create the `review_reports/` directory if it does not exist.
Use today's actual date in the filename.

### Report Structure

```
# SW Hospitality Group — Daily Accounting Review
**Date:** YYYY-MM-DD
**Generated:** [full timestamp]
**Reviewed by:** Claude Code (automated)
**Review window:** Last 48 hours

---

## Summary

| Category                      | Total Reviewed | Issues Found | Critical 🔴 | Warnings 🟡 |
|-------------------------------|----------------|--------------|-------------|-------------|
| Invoice Accuracy (Hub)        |                |              |             |             |
| GL Entries                    |                |              |             |             |
| Inventory Costs               |                |              |             |             |
| Payments / Disbursements      |                |              |             |             |
| Duplicate Invoices            |                |              |             |             |
| Clover Sales Pulls            |                |              |             |             |
| Hub ↔ Accounting Sync         |                |              |             |             |
| Invoice Pipeline Health       |                |              |             |             |
| Beverage Distributor Pricing  |                |              |             |             |
| Linen Service Parse Quality   |                |              |             |             |
| Delivery Fee Completeness     |                |              |             |             |

---

## 🔴 Critical Issues (require same-day action)
[Each issue: what it is, which record, plain-English explanation, recommended action]

## 🗑️ Duplicate Invoices Resolved
| Kept Invoice | Removed Invoice | Vendor | Amount | Match Type | Action Taken |
...

## ✏️ Corrections Made
| Invoice | Field | Original Value | Corrected Value | Verified By | Log ID |
...

## 🟡 Warnings (review within 48 hours)
[Each warning with record reference and explanation]

## 👤 Flagged for Human Review
[Items that need human judgment — include exactly what information is needed to resolve]

## ✅ Passed Checks
[All checks that found zero issues — list every check by name]

## ⚠️ Review Infrastructure Issues
[Any DB errors, missing tables, inaccessible PDFs encountered during the run]

---
_Report generated by Claude Code automated accounting review_
_Audit logs: invoice_correction_log, invoice_duplicate_log_
```

### Severity Definitions
- **Critical 🔴**: Unbalanced journal entry (any type), confirmed duplicate invoice, tax double-count, payment with no invoice, real double payment, vendor bill lines vs total mismatch, Hub-Accounting sync failure, missing location on ready/sent invoice, linen price/total swap
- **Warning 🟡**: Unit price outlier, cost not updated, cost spike, large manual entry, near-duplicate (Tier 2), cross-location posting, stale ready invoices, statement misclassification, missing delivery fee, beverage discount not captured, stuck needs_review, credit memo without lines
- **Info ℹ️**: Round number flag, orphaned cost record, description mismatch

---

## Section 7 — Auto-Correction Protocol

### Guiding Principle
Claude Code may only write a correction when ALL of the following are true:
1. The source PDF is accessible and readable (except Type 4 math errors — no PDF needed)
2. The correct value is unambiguous in the PDF
3. The discrepancy matches a known correction type defined below
4. Confidence is HIGH
5. The invoice status is NOT `'approved'`, `'paid'`, `'locked'`, or `'voided'`

If any condition fails → flag only, never guess, never correct.

### Required Audit Table
Create this table on first run if it does not exist:

```sql
CREATE TABLE IF NOT EXISTS invoice_correction_log (
    id                  SERIAL PRIMARY KEY,
    corrected_at        TIMESTAMP DEFAULT NOW(),
    invoice_id          INTEGER NOT NULL,
    line_item_id        INTEGER,
    correction_type     VARCHAR(50) NOT NULL,
    field_name          VARCHAR(100) NOT NULL,
    original_value      TEXT NOT NULL,
    corrected_value     TEXT NOT NULL,
    confidence          VARCHAR(10) NOT NULL,
    verification_method TEXT NOT NULL,
    pdf_path            TEXT,
    reviewer            VARCHAR(50) DEFAULT 'claude-code-automated',
    review_session_id   VARCHAR(100),
    notes               TEXT
);
```

### Confidence Levels
- **HIGH** → auto-correct: PDF value is unambiguous, exact format match, fits a known OCR error pattern
- **MEDIUM** → flag only: PDF value is readable but requires interpretation
- **LOW** → flag only: PDF is unclear, rotated, low-res, or field is partially obscured

---

### Correction Type 1: Wrong Item Code

**Trigger:** `invoice_line_items.vendor_item_code` doesn't match any known
`vendor_items.item_code` for that vendor, OR the code matches a different item
than the line item description.

**Verification procedure:**
1. Retrieve PDF from `invoices.pdf_path`
2. Re-read the specific line using `src/hub/services/ocr_service.py`
3. Extract item code directly from PDF at the line position
4. Look up extracted code in `vendor_items` for that vendor
5. If exact match found → HIGH confidence → correct
6. If ambiguous or not found → flag for human review

**Correction SQL:**
```sql
UPDATE invoice_line_items
SET vendor_item_code = :correct_code,
    master_item_id   = :correct_master_item_id,
    corrected        = true,
    corrected_at     = NOW()
WHERE id = :line_item_id;
```

---

### Correction Type 2: Quantity Decimal Error

**Trigger:** `quantity` is implausible for the item category AND PDF shows a
different value (e.g., DB has 1.2, PDF shows 12 — classic OCR decimal drop).

**Verification:** Re-read PDF quantity for that line. Confirmed if PDF value
equals `db_quantity * 10` or `db_quantity * 100` exactly.

**Correction:** Update `quantity` and recalculate `extended_price = corrected_quantity * unit_price`.
Update both fields atomically.

---

### Correction Type 3: Unit Price Decimal Shift

**Trigger:** `unit_price` deviates >80% from 90-day average for that vendor item
AND the deviation is exactly 10x or 100x.

**Verification:** Re-read PDF unit price. Must be exact match to expected corrected value.

**Correction:** Update `unit_price` and `extended_price`.
Flag any GL entries linked to this invoice for human recalculation — do not auto-update GL.

---

### Correction Type 4: Extended Price Math Error

**Trigger:** `extended_price != ROUND(quantity * unit_price, 2)` by more than $0.01.

**Verification:** Math only — no PDF re-read required. Always auto-correctable.

**Correction:** `extended_price = ROUND(quantity * unit_price, 2)`

---

### Correction Type 5: Tax Double-Count

**Trigger:** Invoice has both a dedicated `TAX` line item AND tax appears to be
embedded in individual item costs (known pattern from Integration Hub fix history).

**Verification:** Compare `invoice.tax_amount` to GL entries. Confirmed if both
a dedicated tax GL entry AND inflated item costs exist simultaneously.

**Correction:** Remove the duplicate tax line item. Update `invoice.total` to reflect removal.
Flag GL entries for human recalculation — do not auto-update GL for tax corrections.

---

### After Any Correction
1. Write to `invoice_correction_log` before executing the UPDATE — log the attempt regardless of outcome
2. Re-run the affected check on corrected data and confirm resolution
3. If line item corrections change `invoice.total`, update `invoice.total = SUM(corrected line items)`
4. Record every correction in the **Corrections Made** section of the daily report

### Never Auto-Correct
- Invoices with `status IN ('approved', 'paid', 'locked', 'voided')`
- GL journal entries (flag only — accounting corrections require human journal entries)
- Vendor master data
- `master_item_location_costs` — flag for Hub reprocessing instead
- Any field where confidence is MEDIUM or LOW
- Any field where the PDF is inaccessible or throws an error

---

## Section 8 — Duplicate Invoice Detection and Resolution

### Vendor Matching
Use the existing vendor matching logic in `src/hub/services/vendor_matcher.py`.
A vendor match score **>= 0.85** is treated as a confirmed vendor match for all
duplicate detection logic below. This threshold reflects Claude's established
performance on this task.

### Required Audit Table
Create on first run if it does not exist:

```sql
CREATE TABLE IF NOT EXISTS invoice_duplicate_log (
    id                      SERIAL PRIMARY KEY,
    detected_at             TIMESTAMP DEFAULT NOW(),
    kept_invoice_id         INTEGER NOT NULL,
    removed_invoice_id      INTEGER NOT NULL,
    match_type              VARCHAR(50) NOT NULL,
    match_fields            JSONB NOT NULL,
    had_gl_entries          BOOLEAN DEFAULT FALSE,
    had_payments            BOOLEAN DEFAULT FALSE,
    action_taken            VARCHAR(30) NOT NULL,
    gl_entries_voided       INTEGER DEFAULT 0,
    reviewer                VARCHAR(50) DEFAULT 'claude-code-automated',
    review_session_id       VARCHAR(100),
    notes                   TEXT
);
```

Also add these columns to `invoices` if not present:
```sql
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS voided_reason TEXT;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS duplicate_of_invoice_id INTEGER;
```

---

### Duplicate Match Tiers

#### Tier 1 — Exact Duplicate (Confidence: CERTAIN → eligible for deletion)
ALL of the following must match:
- `vendor_id` exact OR vendor match score >= 0.85
- `invoice_total` exact ($0.00 difference)
- `invoice_date` exact
- `invoice_number` exact (if both records have one)

#### Tier 2 — Near-Exact Duplicate (Confidence: HIGH → eligible for deletion after line item check)
ALL of the following must match:
- `vendor_id` exact OR vendor match score >= 0.85
- `invoice_total` within $1.00
- `invoice_date` within 3 days
- Line item count identical
- At least 80% of line items match on item code + quantity

#### Tier 3 — Probable Duplicate (Confidence: MEDIUM → flag only, do not delete)
- Same vendor + same total, but `invoice_date` differs by 4–14 days
- OR same vendor + same `invoice_number`, but total differs slightly

---

### Which Invoice to Keep

When a Tier 1 or Tier 2 pair is confirmed, keep the invoice that:
1. Has `status = 'approved'` or `'paid'` over `'processed'`
2. Has more complete data (more line items, has invoice_number, fuller description)
3. Was created earlier (lower `id`) as a final tiebreaker

Document the keep/remove decision in `invoice_duplicate_log` with the reason.

---

### Pre-Deletion Checklist

Run this before every removal:

| Condition | Action |
|---|---|
| No GL entries, no payment, not paid/approved | Hard delete eligible |
| GL entries exist, no payment, not paid | Void GL entries first, then hard delete |
| Payment references the invoice | Soft void only — do not hard delete |
| Invoice status is `'paid'` | Soft void only — never hard delete a paid invoice |
| Both invoices in pair have payment records | Flag as possible real double payment — do not delete either |
| Invoice referenced in any report | Soft void only |

---

### Deletion Procedure

```python
# Step 1: Gather state
has_gl      = SELECT COUNT(*) FROM gl_entries WHERE invoice_id = :remove_id > 0
has_payment = SELECT COUNT(*) FROM payments WHERE invoice_id = :remove_id > 0
status      = SELECT status FROM invoices WHERE id = :remove_id

# Step 2a: Clean record — hard delete
if not has_gl and not has_payment and status not in ('paid', 'approved', 'locked'):
    DELETE FROM invoice_line_items WHERE invoice_id = :remove_id
    DELETE FROM invoices WHERE id = :remove_id
    action = 'hard_deleted'

# Step 2b: Has GL but no payment — void GL then hard delete
elif has_gl and not has_payment and status not in ('paid', 'locked'):
    UPDATE gl_entries
    SET status = 'voided', voided_reason = 'duplicate_invoice_' || :remove_id
    WHERE invoice_id = :remove_id
    DELETE FROM invoice_line_items WHERE invoice_id = :remove_id
    DELETE FROM invoices WHERE id = :remove_id
    action = 'hard_deleted_gl_voided'

# Step 2c: Has payment or is paid — soft void
else:
    UPDATE invoices
    SET status                   = 'voided',
        voided_at                = NOW(),
        voided_reason            = 'duplicate_of_invoice_' || :keep_id,
        duplicate_of_invoice_id  = :keep_id
    WHERE id = :remove_id
    action = 'soft_voided'

# Step 3: Always log before and after
INSERT INTO invoice_duplicate_log (...) VALUES (...)
```

---

### Safety Limit
Process a maximum of **5 duplicate removals per run**. If more than 5 confirmed
duplicates are found, process the first 5 and flag the remainder for the next run
or human review. This prevents runaway automated deletion if a systematic issue
(e.g., scheduler double-fire) has created a large number of duplicates.
Note the count of skipped duplicates prominently in the report.

### Never Delete
- Any invoice with `status = 'paid'` (soft void only)
- Tier 3 (probable) duplicates
- Either invoice in a pair where both have payment records
- More than 5 invoices in a single run

---

## Section 9 — What Claude Code Must Never Do

- Auto-correct any record it cannot verify from a source document or math
- Modify GL journal entries in any way — flag only
- Modify `vendor_bill_lines` or `journal_entry_lines` in Accounting DB — flag only
- UPDATE records with `status IN ('approved', 'paid', 'locked', 'voided')`
- Hard delete any invoice with `status = 'paid'`
- Call any external APIs (no OpenAI, no external services)
- Re-process entire invoices during verification — extract only the specific field needed
- Process more than 5 duplicate deletions in a single run
- Proceed past a database connection error without logging it
- Delete any record without first writing to the appropriate audit log
- Apply Correction Type 4 (math error) to beverage distributor invoices — their line totals intentionally differ from `qty × unit_price`
- Assume `area_id = 7` (Corporate) is correct for any AP vendor bill — always flag for location review
