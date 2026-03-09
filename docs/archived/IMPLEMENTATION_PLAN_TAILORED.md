# Bank Reconciliation - Tailored Implementation Plan

**Date:** 2025-10-20
**Approach:** Option A - Full Spec (Simplified for User Workflow)
**Timeline:** 6-8 weeks
**Priority:** #1 for next 2 months ✅

---

## Key Insights from User Requirements

### ✅ What SIMPLIFIES the Scope

1. **POS-Agnostic Design**
   - User already has DSS upload capability ✅
   - Don't need POS-specific integrations
   - Focus on DSS → Undeposited Funds → Bank Deposit workflow
   - Works with ANY POS (Clover, Square, Toast, etc.)

2. **Delivery Platforms = Just Another Payment Type**
   - User understands delivery orders go to "Undeposited Funds - Third Party" (1095) ✅
   - When platform pays, it matches to GL 1095 (same as credit card/cash)
   - Don't need platform-specific commission/fee logic
   - Platform settlements are treated like any other deposit

3. **Semi-Automated Workflow (Perfect Balance)**
   - System suggests matches based on rules ✅
   - User reviews and confirms before finalizing
   - No fully automatic posting (user always approves)
   - Focus on "suggest → review → confirm" workflow

4. **Moderate Transaction Volume**
   - 50-60 transactions/month/location = ~2-3 per day
   - 7 credit card batches/week/location = 1 per day
   - Manageable volume, don't need heavy ML or optimization

### ⚠️ What Changes from Original Spec

| Original Spec | Tailored Approach |
|---------------|-------------------|
| POS-specific integrations (Square, Clover APIs) | ❌ Remove - Use generic DSS upload |
| Delivery platform APIs (DoorDash, Uber Eats connectors) | ❌ Remove - Treat as generic deposits |
| Fully automatic matching/posting | ❌ Remove - Always require confirmation |
| ML-assisted matching (Tier 4) | ⚠️ Defer to Phase 2 - Rules-based sufficient |
| Complex fee splitting logic | ❌ Simplify - User handles fees via adjustments |

### ✅ What Stays from Original Spec

- ✅ Statement-based reconciliation workflow
- ✅ Tier 0-2 matching (exact, fuzzy, composite)
- ✅ Rule engine with user confirmation
- ✅ Adjustment workflow (bank fees, interest, NSF, auto expense categorization)
- ✅ Background jobs (auto-sync, reminders)
- ✅ Audit trail and snapshots
- ✅ Multi-location support

---

## Core Workflow (Simplified)

### Daily Sales Summary Flow (Already Working ✅)
```
POS Sales (Any System)
    ↓
Manual DSS Entry or Upload
    ↓
Post DSS to GL
    ↓
DR: Undeposited Funds Cash (1091)           $100
DR: Undeposited Funds Credit Card (1090)    $500
DR: Undeposited Funds Third Party (1095)    $200  ← Uber Eats orders
CR: Revenue Accounts                        $800
```

### Bank Reconciliation Flow (To Build)
```
Bank Statement Import (CSV/OFX)
    ↓
System Matches Bank Deposits:
    ├─ $500 deposit → Suggests: Match to GL 1090 (Undeposited CC) [Rule: Daily CC Batch]
    ├─ $180 deposit → Suggests: Match to GL 1095 (Uber Eats settlement) [Rule: Third Party]
    ├─ $50 Chevron  → Suggests: Auto Expense GL 6500 [Rule: Recurring Vendor]
    ↓
User Reviews Suggestions:
    ├─ ✅ Confirm $500 CC batch match
    ├─ ✅ Confirm $180 Uber Eats match
    ├─ ✅ Confirm $50 auto expense
    ↓
User Finalizes Reconciliation
    ↓
System Creates Clearing JEs:
    DR: Bank Account 1010                   $730
    CR: Undeposited Funds CC (1090)         $500
    CR: Undeposited Funds Third Party (1095) $180
    CR: Auto Expense (6500)                 $50
```

---

## Revised Implementation Phases

### Phase 1A - Core Infrastructure (Week 1-2)
**Goal:** Statement workflow + basic matching with confirmation

**Deliverables:**
1. **Bank Statement Model**
   - Statement periods with open/close balance
   - Status: draft → in_progress → reconciled → locked
   - Link to bank account and date range

2. **Enhanced Transaction Matching (Tier 0-2)**
   - Tier 0: Exact amount + date match
   - Tier 1: Exact amount + date window (±3 days)
   - Tier 2: Composite matching (many-to-one, one-to-many)
   - Confidence scores for each match

3. **Rule Engine Foundation**
   - Create matching rules table
   - Rule types: "Recurring Deposit", "Recurring Expense", "Vendor Match"
   - Condition matching (description contains, amount equals, date pattern)
   - Action: Suggest GL account

4. **Confirmation Workflow UI**
   - Statement selection page
   - Transaction list with suggested matches
   - "Review & Confirm" button per transaction
   - Bulk confirm for multiple transactions
   - Balance verification before finalize

**Test Scenarios:**
- Import bank statement CSV
- System suggests matches for credit card batches
- User reviews and confirms
- Balance reconciles correctly

---

### Phase 1B - Restaurant-Specific Matching (Week 3-4)
**Goal:** Credit card batches, delivery deposits, recurring expenses

**Deliverables:**
1. **Credit Card Batch Deposit Rules**
   - Auto-detect daily deposits matching Undeposited CC (1090)
   - Handle processing fees automatically:
     - If bank deposit = $485 and Undeposited = $500
     - Suggest: Match + create $15 fee adjustment to GL 6510 (CC Fees)
   - User confirms both match and fee adjustment

2. **Third-Party Delivery Deposit Rules**
   - Auto-detect deposits matching Undeposited Third Party (1095)
   - Match to GL 1095 when platform pays
   - No commission logic (user already booked revenue net)

3. **Recurring Expense Auto-Categorization**
   - Rule: "Description contains 'CHEVRON' → GL 6500 Auto Expense"
   - Rule: "Description contains 'AT&T' → GL 6200 Phone"
   - Rule: "Description contains 'WASTE MGMT' → GL 6300 Utilities"
   - User confirms before posting

4. **Cash Deposit Matching**
   - Match to Undeposited Cash (1091)
   - Handle cash over/short:
     - If bank deposit = $99 and Undeposited = $100
     - Suggest: Match + create $1 adjustment to GL 6999 (Cash Over/Short)

**Test Scenarios:**
- Credit card batch with fees
- Uber Eats settlement deposit
- Chevron auto expense categorization
- Cash deposit with over/short

---

### Phase 1C - Full Reconciliation UI (Week 5-6)
**Goal:** Complete reconciliation workflow with audit trail

**Deliverables:**
1. **Statement Reconciliation Dashboard**
   - List of statements by period (monthly)
   - Status indicators (draft/in_progress/reconciled/locked)
   - Opening balance, transactions, closing balance
   - Difference amount (must be $0 to finalize)

2. **Transaction Matching Interface**
   - Left side: Bank transactions (from statement)
   - Right side: GL transactions (journal entry lines)
   - Drag-and-drop or click to match
   - Suggested matches highlighted in green
   - Confidence score badges
   - Match reason display

3. **Adjustment Workflow (Quick-Add)**
   - "Add Adjustment" button on unmatched transactions
   - Quick forms for common adjustments:
     - Bank fee → GL 6520
     - Interest income → GL 7100
     - NSF charge → GL 6530
     - Miscellaneous → Select GL
   - Adjustment creates journal entry immediately
   - User confirms before finalizing

4. **Finalize & Lock Process**
   - Balance guard: Can't finalize unless difference = $0
   - Review screen showing all matches and adjustments
   - Confirm button creates clearing journal entries
   - Statement status → reconciled
   - Immutable snapshot saved
   - Email notification to user

5. **Undo Workflow (With Approval)**
   - Only statements in "reconciled" status (not locked)
   - Undo reverses clearing journal entries
   - Audit log records who undid and why
   - Statement returns to "in_progress"

**Test Scenarios:**
- Full month reconciliation start to finish
- Balance doesn't match, add adjustment
- Finalize and lock statement
- Undo reconciliation and redo

---

### Phase 1D - Automation & Polish (Week 7-8)
**Goal:** Background jobs, reporting, testing, documentation

**Deliverables:**
1. **Background Jobs**
   - Nightly: Check for unreconciled transactions > 30 days
   - Weekly: Email reminder to reconcile outstanding statements
   - Monthly: Auto-lock statements older than 60 days (after user approval)
   - Optional: Plaid auto-sync (if user enables)

2. **Reporting**
   - Reconciliation history report (by period, by bank account)
   - Outstanding deposits/checks report
   - Bank account activity report (with drill-down)
   - Unmatched transactions report

3. **Rule Learning Feature**
   - When user manually matches a transaction, show:
     "Create rule for future matches? [Yes] [No]"
   - Auto-populate rule based on current match
   - User can edit and save rule

4. **Enhanced Search & Filters**
   - Filter by: Date range, amount range, matched/unmatched, GL account
   - Search by: Description, reference number, amount
   - Sort by: Date, amount, confidence score

5. **Comprehensive Testing**
   - Import 3-6 months of historical bank statements (user-provided)
   - Test all matching scenarios with real data
   - Verify balances reconcile correctly
   - Test edge cases (NSF, duplicate deposits, reversed transactions)
   - Performance testing with 500+ transactions

6. **Documentation & Training**
   - User guide: "How to Reconcile Bank Statements"
   - Video/screenshots: "Setting Up Matching Rules"
   - Troubleshooting guide: "When Balances Don't Match"
   - Admin guide: "Managing Reconciliation Settings"

**Test Scenarios:**
- Full UAT with 1 month of real bank statements
- Create 10+ matching rules for common transactions
- Test background jobs and notifications
- Performance test with 6 months of data

---

## Simplified Architecture

### Database Schema Changes

#### New Tables
```sql
-- Bank statements (periods)
CREATE TABLE bank_statements (
    id SERIAL PRIMARY KEY,
    bank_account_id INTEGER REFERENCES bank_accounts(id),
    statement_date DATE NOT NULL,
    opening_balance NUMERIC(15,2) NOT NULL,
    closing_balance NUMERIC(15,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',  -- draft/in_progress/reconciled/locked
    reconciled_by INTEGER REFERENCES users(id),
    reconciled_at TIMESTAMP,
    locked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Link transactions to statements
ALTER TABLE bank_transactions
ADD COLUMN statement_id INTEGER REFERENCES bank_statements(id);

-- Matching rules
CREATE TABLE bank_matching_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    rule_type VARCHAR(50),  -- 'recurring_deposit', 'recurring_expense', 'vendor_match'
    priority INTEGER DEFAULT 0,

    -- Conditions (JSON for flexibility)
    conditions JSONB,  -- {"description_contains": "CHEVRON", "amount_min": 40, "amount_max": 60}

    -- Actions
    action_type VARCHAR(50),  -- 'suggest_gl_account', 'auto_match'
    target_account_id INTEGER REFERENCES accounts(id),
    requires_confirmation BOOLEAN DEFAULT true,

    active BOOLEAN DEFAULT true,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Match confirmations (audit trail)
CREATE TABLE bank_transaction_matches (
    id SERIAL PRIMARY KEY,
    bank_transaction_id INTEGER REFERENCES bank_transactions(id),
    journal_entry_line_id INTEGER REFERENCES journal_entry_lines(id),
    match_type VARCHAR(50),  -- 'exact', 'fuzzy', 'composite', 'manual'
    confidence_score NUMERIC(5,2),
    matched_by_rule_id INTEGER REFERENCES bank_matching_rules(id),
    confirmed_by INTEGER REFERENCES users(id),
    confirmed_at TIMESTAMP DEFAULT NOW(),
    cleared_journal_entry_id INTEGER REFERENCES journal_entries(id)  -- The clearing JE created
);

-- Statement snapshots (immutable audit trail)
CREATE TABLE bank_statement_snapshots (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES bank_statements(id),
    snapshot_data JSONB,  -- Full state at time of reconciliation
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Modified Tables
```sql
-- Add confirmation workflow fields
ALTER TABLE bank_transactions
ADD COLUMN suggested_account_id INTEGER REFERENCES accounts(id),
ADD COLUMN suggested_by_rule_id INTEGER REFERENCES bank_matching_rules(id),
ADD COLUMN suggestion_confidence NUMERIC(5,2),
ADD COLUMN confirmed_by INTEGER REFERENCES users(id),
ADD COLUMN confirmed_at TIMESTAMP;
```

---

## Key Features - User Perspective

### 1. Statement Upload & Auto-Match
```
User Action: Upload October 2025 Chase Bank statement (CSV)

System Response:
✅ Imported 58 transactions
✅ Found 42 suggested matches (72% confidence average)
   - 7 credit card batches → Undeposited CC (1090) [95% confidence]
   - 4 third-party deposits → Undeposited Third Party (1095) [90% confidence]
   - 12 recurring expenses → Auto-categorized [85% confidence]
   - 19 other matches suggested [60-80% confidence]
⚠️ 16 transactions need manual review

[Review Suggestions] [Start Manual Matching]
```

### 2. Review & Confirm Suggestions
```
Transaction #1: $487.50 deposit on Oct 2
Suggested Match: Undeposited Funds Credit Card (1090) - $500.00
Match Reason: Daily credit card batch deposit
Confidence: 92% (amount close, date matches, recurring pattern)

Fee Adjustment Suggested:
Credit Card Processing Fee (6510): $12.50

[✅ Confirm Match + Fee] [✏️ Edit] [❌ Reject]
```

### 3. Manual Matching for Unknowns
```
Transaction #15: $52.75 debit - "OFFICE DEPOT #4521"
Status: No match found

Suggested Actions:
1. Create Expense:
   Account: [Select GL Account ▼]
   Description: Office supplies
   [Create & Match]

2. Search GL Transactions:
   [Amount: $52.75] [Date: ±7 days] [Search]

3. Create Matching Rule:
   When description contains "OFFICE DEPOT"
   → Categorize to GL 6400 (Office Supplies)
   [Save Rule]
```

### 4. Finalize Reconciliation
```
October 2025 Reconciliation Summary:

Opening Balance:     $12,458.23
+ Deposits:          $15,420.00
- Withdrawals:       $13,892.15
Closing Balance:     $13,986.08

Bank Statement:      $13,986.08
GL Balance:          $13,986.08
Difference:          $0.00 ✅

Matched Transactions: 58/58 (100%)
Adjustments Created:  3 (fees, interest)

[✅ Finalize & Lock] [View Detail] [Export Report]
```

---

## Success Criteria

### Week 2 Checkpoint
- ✅ Can import bank statement CSV
- ✅ System suggests matches for transactions
- ✅ User can confirm/reject suggestions
- ✅ Balance calculation works correctly

### Week 4 Checkpoint
- ✅ Credit card batch matching working (with fees)
- ✅ Uber Eats deposits matching to GL 1095
- ✅ Recurring expenses auto-categorized (Chevron, utilities)
- ✅ Can create matching rules

### Week 6 Checkpoint
- ✅ Full reconciliation workflow end-to-end
- ✅ Can finalize and lock statements
- ✅ Adjustment workflow functional
- ✅ Audit trail complete

### Week 8 - Production Ready
- ✅ Full UAT passed with real bank statements
- ✅ 10+ matching rules configured
- ✅ Background jobs running
- ✅ User documentation complete
- ✅ Performance validated (500+ transactions)

---

## Risk Mitigation

### Weekly Testing Sessions (Required)
- Week 2: Test statement import and basic matching
- Week 4: Test credit card batches and delivery deposits
- Week 6: Full reconciliation with real October data
- Week 8: Final UAT and production deployment

### Scope Protection
- No POS integrations (use DSS upload ✅)
- No delivery platform APIs (treat as deposits ✅)
- No fully automatic posting (always confirm ✅)
- Defer ML matching to Phase 2 (rules-based sufficient ✅)

### Data Requirements
- User provides 3-6 months of historical bank statements (CSV/OFX)
- User provides sample credit card batch reports
- User provides Uber Eats settlement examples

---

## Next Steps

1. ✅ User approval of this tailored plan
2. ✅ User provides sample data:
   - 1-2 months of bank statements (CSV or OFX)
   - Sample credit card batch report (Clover)
   - Sample Uber Eats settlement report
3. ✅ Begin Phase 1A development (Statement model + matching engine)
4. ✅ Schedule weekly testing session (same day/time each week)

---

## Questions Resolved

✅ **POS System:** Clover (but POS-agnostic via DSS upload)
✅ **Delivery Platforms:** Uber Eats (treated as deposits to GL 1095)
✅ **Transaction Volume:** 50-60/month/location, 7 CC batches/week
✅ **Data Availability:** Yes - historical bank statements available
✅ **Timeline Commitment:** Yes - #1 priority, weekly testing committed
✅ **Top Pain Points:** Automation with confirmation (semi-automatic)

**No scope changes needed. Plan is simplified and clearer. Ready to begin.**

---

**Prepared By:** Claude Code
**Date:** October 20, 2025
**Status:** ✅ Approved to Proceed
**Start Date:** October 21, 2025 (Week 1 of 8)
