# Bank Reconciliation - Gap Analysis & Implementation Plan

**Date:** 2025-10-20
**Current Status:** Basic matching implemented (~30% of full spec)
**Target:** Full restaurant-aware bank reconciliation system

---

## 📊 What We Have (Current Implementation)

### ✅ Database Schema - Partially Complete
- [x] `bank_accounts` - Basic account info with GL linkage
- [x] `bank_transactions` - Individual transaction records
- [x] `bank_statement_imports` - Import tracking
- [x] `bank_reconciliations` - Reconciliation headers
- [x] `bank_reconciliation_items` - Line item clearings
- [x] `bank_matching_rules` - Basic rule engine

### ✅ Features Implemented
1. **Bank Account Management**
   - Create/edit/view bank accounts
   - Link to GL accounts
   - Plaid configuration fields (not active)

2. **Transaction Import**
   - CSV import
   - OFX/QFX parsing (code exists)
   - Basic deduplication by Plaid ID

3. **Simple Matching**
   - **Tier 0-1 only**: Exact amount + date window matching
   - Manual match/unmatch via UI
   - Match to journal entry lines
   - Confidence scoring (40pts amount, 30pts date, 30pts description)
   - Fuzzy string matching using rapidfuzz

4. **UI Components**
   - Bank accounts list
   - Transaction list with matched column
   - Transaction detail modal
   - Find Matches button with suggestions
   - Match/Unmatch buttons with confirmation

### ❌ Major Gaps

#### 1. **No Bank Statement Model**
- Missing `bank_statement` table with opening/closing balances
- No statement status workflow (draft → in_progress → reconciled → locked)
- Transactions not grouped by statement period

#### 2. **Limited Matching Engine**
- **Missing Tier 2**: Many-to-one, one-to-many composite matches
- **Missing Tier 3**: Advanced rule-based matching with actions
- **Missing Tier 4**: ML-assisted suggestions
- No tolerance settings (fee tolerance, date windows per account)
- No idempotency hash (allows duplicates)

#### 3. **No Restaurant-Specific Logic**
- ❌ Credit card batch deposit handling
- ❌ Undeposited Funds clearing
- ❌ Delivery platform net deposits (DoorDash, Uber Eats)
- ❌ Cash over/short adjustments
- ❌ Tips payable tracking
- ❌ Inter-bank transfer pairing

#### 4. **No Adjustment Workflow**
- Can't create bank fees from reconciliation UI
- Can't post interest income
- Can't handle NSF/chargebacks
- Can't auto-create rounding adjustments

#### 5. **Incomplete Reconciliation Workflow**
- No opening balance verification
- No real-time difference display
- No balance guard (prevent finalize if out of balance)
- No snapshot/audit trail of cleared pairs
- No undo reconciliation
- No period lock integration

#### 6. **Missing Rule Features**
- Rules can't have multiple conditions
- Rules can't perform actions (only suggest)
- No "Create rule from match" feature
- No rule priority/ordering

#### 7. **No Background Jobs**
- No auto-sync with Plaid
- No reminder emails for unmatched transactions
- No monthly lock checks

#### 8. **Limited APIs**
- No `/bank/statements/{id}/auto-match` endpoint
- No `/bank/statements/{id}/reconcile` endpoint
- No `/bank/adjustments` endpoint

---

## 🎯 Implementation Priority (Phase 1 MVP)

### Phase 1A - Core Infrastructure (Week 1-2)
1. **Add Bank Statement Model**
   - Create `bank_statements` table
   - Link transactions to statements
   - Statement workflow (draft/in_progress/reconciled/locked)
   - Opening/closing balance tracking

2. **Enhanced Matching Engine**
   - Implement Tier 2 (many-to-one, one-to-many)
   - Tolerance settings per account
   - Idempotency hash on transactions
   - Match snapshot/audit trail

3. **Adjustment Workflow**
   - Bank fee quick-add
   - Interest income quick-add
   - Rounding adjustments
   - All create proper JEs with source=bank_rec

### Phase 1B - Restaurant Features (Week 3-4)
4. **Credit Card Batch Deposits**
   - Match to Undeposited Funds
   - Auto-create fee adjustments
   - Handle delayed deposits

5. **Delivery Platform Integration**
   - Net deposit matching
   - Auto-split fees/commissions
   - Platform-specific rules

6. **Cash Handling**
   - Cash over/short detection
   - Auto-suggest adjustments

### Phase 1C - Reconciliation Workflow (Week 5-6)
7. **Full Reconciliation UI**
   - Statement-based workflow
   - Real-time difference display
   - Balance guard
   - Finalize with snapshot
   - Undo with approval

8. **Enhanced Rule Engine**
   - Multi-condition rules
   - Action execution
   - "Learn from match" feature

---

## 📈 Comparison: Current vs. Target

| Feature | Current | Target | Gap |
|---------|---------|--------|-----|
| **Schema Completeness** | 60% | 100% | Missing statements, match snapshots, enhanced rules |
| **Matching Tiers** | Tier 0-1 | Tier 0-4 | Missing composite, advanced rules, ML |
| **Restaurant Features** | 0% | 100% | No POS, delivery, cash logic |
| **Adjustment Workflow** | 0% | 100% | Can't create JEs from recon UI |
| **Auto-Match Rate** | ~40% | 80%+ | Need better matching + rules |
| **Audit Trail** | Partial | Full | Missing snapshots, period locks |
| **UI Workflow** | Basic | Complete | Missing statement view, difference display |

---

## 🏗️ Architectural Decisions

### Keep What Works
✅ Current database structure is solid foundation
✅ Match to `journal_entry_lines` (not `journal_entries`) is correct
✅ Confidence scoring approach is good
✅ Fuzzy matching library (rapidfuzz) works well

### Major Changes Needed
🔄 **Add statement-centric workflow** - Group transactions by statement period
🔄 **Implement composite matching** - Handle batch deposits properly
🔄 **Add tolerance tiers** - Different rules for card batches vs checks
🔄 **Build adjustment creator** - Quick-add JEs from reconciliation screen
🔄 **Add snapshot system** - Immutable audit trail of cleared pairs

### Restaurant-Specific Additions
🆕 **Undeposited Funds integration** - Track from DSS to bank deposit
🆕 **Processor net handling** - Auto-calculate fees for card batches
🆕 **Platform reconciliation** - DoorDash, Uber Eats workflows
🆕 **Cash variance tracking** - Link to DSS cash deposits

---

## 🚀 Next Steps

1. **Review this analysis** with user to confirm priorities
2. **Design complete schema** for Phase 1A
3. **Implement statement model** and migration
4. **Build enhanced matching engine** with Tier 2
5. **Create adjustment workflow** UI + API
6. **Test with real restaurant data** (POS batches, delivery deposits)

---

## 📝 Questions for User

1. **Priority Order**: Start with statements + matching engine, or restaurant features first?
2. **Plaid Integration**: Do you want Phase 1 MVP or wait until Phase 2?
3. **DSS Integration**: Are Daily Sales Summary records ready for linking?
4. **Multi-Location**: Do different locations use different bank accounts?
5. **Delivery Platforms**: Which platforms do you use? (DoorDash, Uber Eats, Grubhub)

---

## 📚 Reference: Spec Requirements vs Current

### Spec Asked For:
- **6 core tables** (bank_account, bank_statement, bank_statement_line, bank_match, bank_rule, reconciliation items)
- **5-tier matching** (Tier 0-4 with ML)
- **Restaurant workflows** (POS, delivery, cash, tips)
- **Adjustment creator** (quick-add from UI)
- **Full audit** (snapshots, period locks, RBAC)
- **Background jobs** (auto-sync, reminders, locks)

### We Have:
- **6 basic tables** ✅ (but missing statement model details)
- **2-tier matching** ⚠️ (Tier 0-1 only)
- **0 restaurant workflows** ❌
- **0 adjustment workflow** ❌
- **Partial audit** ⚠️ (logs yes, snapshots no)
- **0 background jobs** ❌

**Gap Severity: MODERATE-HIGH**
Current system handles ~30% of spec requirements.
Need significant work to reach production-ready restaurant reconciliation.
