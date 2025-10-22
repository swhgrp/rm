# Hybrid Bank Reconciliation - Design Document

**Date:** 2025-10-20
**Status:** Approved by User - Ready to Build
**Approach:** Transaction-First with Optional Statement Wrapper

---

## 🎯 Core Concept

**Hybrid Model:** Combine the best of both approaches:
1. **Transaction-First UI** - Like user's current system (screenshot)
2. **Optional Statement Wrapper** - For audit compliance and month-end close
3. **Smart Matching** - Vendor recognition + open bills + learned patterns

---

## 📊 User's Current Workflow (From Screenshot)

### What Works Well:
```
1. Bank transactions imported
2. For each transaction:
   ├─ Known vendor? → Show "Reconcile X" (X open bills)
   ├─ Learned pattern? → Suggest GL account
   └─ Unknown? → "Set Partner" or "Set Account"
3. User clicks action → Modal shows options
4. User selects match → Confirms
5. Transaction marked reconciled ✅
```

### Key Features from Screenshot:
- ✅ Vendor recognition ("Gold Coast Linen Service")
- ✅ Open bills count ("Reconcile 9")
- ✅ 100% match highlighting in modal
- ✅ Multi-bill selection (multiple bills → one payment)
- ✅ GL selection fallback for unknowns
- ✅ Learned suggestions from manual matches

---

## 🏗️ Hybrid Architecture

### Layer 1: Transaction Matching (Primary UX)
```
User imports bank statement
    ↓
For each transaction, system analyzes:
    1. Vendor Recognition
       - Extract vendor from description
       - Find in vendors table
       - Show open bills count

    2. Bill Matching (for expenses)
       - Find unpaid vendor bills
       - Calculate exact matches (amount + date window)
       - Highlight 100% matches

    3. Deposit Matching (for income)
       - Composite matching (multi-day deposits)
       - Undeposited Funds clearing
       - Customer invoice matching

    4. Pattern Recognition
       - Check learned rules
       - Suggest GL account
       - Show confidence score

    5. Fallback
       - No match found
       - User selects GL or vendor manually
```

### Layer 2: Statement Wrapper (Optional)
```
User creates statement (optional):
    - Statement period: Oct 1-31, 2025
    - Opening balance: $12,458.23
    - Closing balance: $13,986.08
    - Import transactions → Assigns to statement

Benefits:
    ✅ Balance verification
    ✅ Month-end close
    ✅ Lock periods (audit compliance)
    ✅ Snapshot for records

Flexibility:
    - Can match transactions WITHOUT creating statement
    - Statement is just a grouping/verification wrapper
    - Can create statement retroactively
```

---

## 🎨 UI Design (Based on Screenshot)

### Main Transaction List View

```
┌────────────────────────────────────────────────────────────────────────┐
│ Bank Matching - 1022 Checking (Oct 2025)                    1-80/100   │
├────────────────────────────────────────────────────────────────────────┤
│ Date   Description                    Partner/Type         Action      Amount    │
├────────────────────────────────────────────────────────────────────────┤
│ Oct 10  DEPOSIT ID NUMBER 102259     Credit Card          ✓ Matched   $ 494.25  │
│         Matched to: Undeposited Funds CC (99%)                         │
│         [View Details]                                                 │
├────────────────────────────────────────────────────────────────────────┤
│ Oct 07  GOLD COAST LINEN SERV        Gold Coast Linen     Reconcile 9 $ -71.56  │
│         FL 10/07                     Service               [View Bills]│
│         Suggested: 1 exact match found                                 │
├────────────────────────────────────────────────────────────────────────┤
│ Oct 06  ORIG CO NAME:CAPITAL ONE     Unknown              Set Partner  $ -800.00 │
│         ORIG ID:9279744380...                             Set Account  │
│         [Expand Details ▼]                                             │
├────────────────────────────────────────────────────────────────────────┤
│ Oct 04  GORDON FOOD SERV             Gordon Food Service  Reconcile 4 $ -781.37  │
│         ORIG ID:1381249848                                [View Bills] │
│         Suggested: Multiple matches available                          │
└────────────────────────────────────────────────────────────────────────┘
```

### Modal 1: Open Bills (Click "Reconcile 9")

```
┌──────────────────────────────────────────────────────────────────┐
│ Match to Open Bills - Gold Coast Linen Service            [X]    │
├──────────────────────────────────────────────────────────────────┤
│ Bank Transaction: Oct 07, 2025                                   │
│ Amount: $ -71.56                                                 │
│ Description: GOLD COAST LINEN SERV FL 10/07                      │
│                                                                  │
│ Open Bills for Gold Coast Linen Service:           1-9 of 9     │
│                                                                  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ✅ BILL/2025/10/0003   10/02/2025   $ -71.56   100% Match │  │
│ │ ☐  BILL/2025/10/0002   10/09/2025   $ -73.33              │  │
│ │ ☐  BILL/2025/08/0012   08/28/2025   $ -73.63              │  │
│ │ ☐  RBILL/2025/06/0001  06/06/2025   $  68.82   (Credit)   │  │
│ │ ☐  BILL/2025/06/0007   06/05/2025   $ -68.82              │  │
│ │ ☐  BNK1/2025/04/0441   04/29/2025   $  65.62   (Credit)   │  │
│ │ ☐  BILL/2025/04/0011   04/24/2025   $ -65.62              │  │
│ │ ☐  BILL/2025/04/0005   04/10/2025   $ -65.62              │  │
│ │ ☐  BILL/2025/03/0010   03/17/2025   $ -68.64              │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Selected Bills:                                                  │
│ • BILL/2025/10/0003 .................................. $ -71.56  │
│                                                                  │
│ Total Selected: $ -71.56                                         │
│ Bank Amount:    $ -71.56                                         │
│ Difference:     $   0.00 ✅                                      │
│                                                                  │
│ [Cancel]                                      [Confirm Match]    │
└──────────────────────────────────────────────────────────────────┘
```

### Modal 2: Set Account (Unknown Transaction)

```
┌──────────────────────────────────────────────────────────────────┐
│ Categorize Transaction                                     [X]    │
├──────────────────────────────────────────────────────────────────┤
│ Bank Transaction: Oct 06, 2025                                   │
│ Amount: $ -800.00                                                │
│ Description: ORIG CO NAME:CAPITAL ONE ORIG ID:9279744380...      │
│                                                                  │
│ Select GL Account:                                               │
│ ┌──────────────────────────────────────────────────────┐         │
│ │ [Search accounts... 🔍]                               │         │
│ │                                                       │         │
│ │ Recent:                                               │         │
│ │ 6510 - Credit Card Processing Fees                    │         │
│ │ 6520 - Bank Fees                                      │         │
│ │ 6500 - Auto Expense                                   │         │
│ │                                                       │         │
│ │ All Accounts:                                         │         │
│ │ 5000 - Cost of Goods Sold                             │         │
│ │ 6000 - Operating Expenses                             │         │
│ │   6100 - Rent                                         │         │
│ │   6200 - Utilities                                    │         │
│ │   6500 - Auto Expense                                 │         │
│ │   6510 - Credit Card Processing Fees ←                │         │
│ └──────────────────────────────────────────────────────┘         │
│                                                                  │
│ Or Select Vendor:                                                │
│ [Search vendors... 🔍]                                            │
│                                                                  │
│ ☑ Create matching rule for future:                              │
│   When description contains "CAPITAL ONE"                        │
│   → Suggest GL 6510 (Credit Card Processing Fees)               │
│                                                                  │
│ [Cancel]                                      [Confirm]          │
└──────────────────────────────────────────────────────────────────┘
```

### Modal 3: Composite Match (Multi-Day Deposit)

```
┌──────────────────────────────────────────────────────────────────┐
│ Match Deposit - Composite Match                           [X]    │
├──────────────────────────────────────────────────────────────────┤
│ Bank Transaction: Oct 10, 2025                                   │
│ Amount: $ 494.25                                                 │
│ Description: DEPOSIT ID NUMBER 102259                            │
│                                                                  │
│ Suggested Match (99% confidence):                                │
│ Undeposited Funds - Credit Card                                  │
│                                                                  │
│ GL Entries to Clear:                                             │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ✅ DSS-20251008  10/08/2025  $ 150.00  Credit card sales  │  │
│ │ ✅ DSS-20251009  10/09/2025  $ 200.00  Credit card sales  │  │
│ │ ✅ DSS-20251010  10/10/2025  $ 144.25  Credit card sales  │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Total GL Amount: $ 494.25                                        │
│ Bank Amount:     $ 494.25                                        │
│ Difference:      $   0.00 ✅ (Exact Match!)                      │
│                                                                  │
│ [Cancel]                                      [Confirm Match]    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔧 API Endpoints to Build/Enhance

### 1. Vendor Recognition
```python
GET /api/bank-transactions/{id}/recognize-vendor

Response:
{
  "transaction_id": 42,
  "extracted_vendor_name": "Gold Coast Linen",
  "matched_vendor": {
    "id": 15,
    "name": "Gold Coast Linen Service",
    "confidence": 95.0
  },
  "open_bills_count": 9,
  "has_exact_match": true
}
```

### 2. Open Bills Lookup
```python
GET /api/bank-transactions/{id}/open-bills

Response:
{
  "vendor": {
    "id": 15,
    "name": "Gold Coast Linen Service"
  },
  "bank_amount": -71.56,
  "open_bills": [
    {
      "id": 123,
      "bill_number": "BILL/2025/10/0003",
      "date": "2025-10-02",
      "amount_due": -71.56,
      "match_type": "exact",
      "match_confidence": 100.0,
      "is_exact_match": true
    },
    {
      "id": 124,
      "bill_number": "BILL/2025/10/0002",
      "date": "2025-10-09",
      "amount_due": -73.33,
      "match_type": "close",
      "match_confidence": 75.0,
      "is_exact_match": false
    },
    // ... more bills
  ],
  "total_bills": 9,
  "exact_matches": 1
}
```

### 3. Multi-Bill Matching
```python
POST /api/bank-transactions/{id}/match-bills
{
  "bill_ids": [123, 124],  // Can be multiple
  "total_amount": -145.12,
  "create_clearing_je": true
}

Response:
{
  "match_id": 456,
  "matched_bills": [
    {"bill_id": 123, "amount": -71.56},
    {"bill_id": 124, "amount": -73.56}
  ],
  "clearing_journal_entry_id": 789,
  "status": "confirmed"
}
```

### 4. GL Account Selection
```python
POST /api/bank-transactions/{id}/categorize
{
  "gl_account_id": 6510,
  "create_rule": true,
  "rule_pattern": "CAPITAL ONE"
}

Response:
{
  "journal_entry_id": 890,
  "rule_created": true,
  "rule_id": 12
}
```

### 5. Enhanced Match Suggestions (Already Built - Enhance)
```python
GET /api/bank-statements/transactions/{id}/suggest-matches

# Add vendor bill suggestions to existing response
Response:
{
  "suggestions": [
    {
      "match_type": "vendor_bill",  // NEW TYPE
      "vendor_id": 15,
      "vendor_name": "Gold Coast Linen Service",
      "open_bills_count": 9,
      "exact_matches_count": 1,
      "confidence_score": 100.0,
      "match_reason": "Exact bill match found"
    },
    {
      "match_type": "composite",  // EXISTING
      "confidence_score": 99.0,
      // ... existing fields
    }
  ]
}
```

---

## 🗄️ Database Schema Updates

### Vendor Bill Status Field (Already exists?)
```sql
-- Check if vendor_bills table has what we need
SELECT
  id,
  bill_number,
  vendor_id,
  total_amount,
  amount_due,  -- Remaining balance
  status       -- unpaid, partial, paid
FROM vendor_bills
WHERE status IN ('unpaid', 'partial')
  AND vendor_id = 15;
```

### Bank Transaction to Vendor Bill Link
```sql
-- New table to track bill payments
CREATE TABLE bank_transaction_bill_matches (
  id SERIAL PRIMARY KEY,
  bank_transaction_id INTEGER REFERENCES bank_transactions(id),
  vendor_bill_id INTEGER REFERENCES vendor_bills(id),
  matched_amount NUMERIC(15,2),  -- Can be partial
  confirmed_by INTEGER REFERENCES users(id),
  confirmed_at TIMESTAMP DEFAULT NOW(),
  clearing_journal_entry_id INTEGER REFERENCES journal_entries(id)
);
```

---

## 🎯 Implementation Plan

### Phase 1: Vendor Recognition (Day 3)
- [ ] Build vendor extraction from description
- [ ] API: GET /recognize-vendor
- [ ] API: GET /open-bills
- [ ] Test with real vendor names

### Phase 2: Bill Matching (Day 4)
- [ ] API: POST /match-bills (single and multi)
- [ ] Create clearing journal entries
- [ ] Update vendor bill status
- [ ] Test payment matching

### Phase 3: UI - Transaction List (Day 5)
- [ ] Build main transaction list view
- [ ] Show vendor badges ("Reconcile X")
- [ ] Show match suggestions
- [ ] Status indicators (matched/unmatched)

### Phase 4: UI - Modals (Day 6)
- [ ] Open bills modal with checkboxes
- [ ] 100% match highlighting
- [ ] GL account selection modal
- [ ] Composite match modal

### Phase 5: Integration & Testing (Day 7)
- [ ] Connect UI to APIs
- [ ] Test full workflow
- [ ] Import real bank statement
- [ ] Test with real vendor bills

---

## 📋 Data Flow Example

### Example: Match "Gold Coast Linen" Payment

```
1. User sees transaction:
   Oct 07  GOLD COAST LINEN SERV FL 10/07  $ -71.56

2. System recognizes vendor:
   GET /api/bank-transactions/42/recognize-vendor
   → Returns: vendor_id=15, open_bills_count=9

3. UI shows:
   Gold Coast Linen Service  [Reconcile 9]

4. User clicks "Reconcile 9":
   GET /api/bank-transactions/42/open-bills
   → Returns: 9 bills, highlights BILL/2025/10/0003 (100% match)

5. User sees modal:
   ✅ BILL/2025/10/0003  $ -71.56  100% Match

6. User clicks "Confirm Match":
   POST /api/bank-transactions/42/match-bills
   {
     "bill_ids": [123],
     "total_amount": -71.56
   }

7. System creates:
   - BankTransactionBillMatch record
   - Clearing JE:
     DR 2215 Accounts Payable  $71.56
     CR 1010 Bank Account             $71.56
   - Updates vendor_bill.status = 'paid'
   - Updates bank_transaction.status = 'reconciled'

8. Done! ✅
```

---

## 🎨 Visual Indicators

### Transaction Status:
- 🟢 **Green** - Matched and confirmed
- 🔵 **Blue** - Suggested match available (high confidence)
- 🟡 **Yellow** - Suggested match available (low confidence)
- ⚪ **Gray** - No match found, needs manual action

### Match Confidence Badges:
- 🟢 **100%** - Exact match (amount + date)
- 🔵 **90-99%** - Very likely match
- 🟡 **70-89%** - Probable match
- ⚫ **<70%** - Possible match (review carefully)

### Action Buttons:
- **Reconcile X** - X open bills available
- **View Bills** - See all open bills
- **Set Partner** - Select vendor manually
- **Set Account** - Select GL account
- **View Details** - Expand transaction info

---

## ✅ Success Criteria

### User Experience:
- [ ] Can match 80% of transactions in <10 seconds each
- [ ] Exact matches highlighted automatically
- [ ] Multi-bill payments work smoothly
- [ ] Learn from manual matches (rules created)
- [ ] No typing for known vendors

### Technical:
- [ ] <500ms response for vendor recognition
- [ ] <1s response for open bills lookup
- [ ] Proper audit trail for all matches
- [ ] Balance verification accurate
- [ ] Can handle 100+ transactions per statement

### Business Value:
- [ ] Reduces reconciliation time by 70%
- [ ] Eliminates manual GL lookups for known vendors
- [ ] Prevents duplicate payments
- [ ] Maintains audit compliance
- [ ] Learns and improves over time

---

**Status:** Ready to Build! 🚀

**Next Step:** Implement vendor recognition API
