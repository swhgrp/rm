# Banking & Bank Reconciliation - Complete User Manual

**SW Hospitality Group - Accounting System**
**Version:** 1.0
**Last Updated:** October 21, 2025
**Status:** Production Ready

---

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Bank Account Setup](#bank-account-setup)
4. [Creating Bank Reconciliations](#creating-bank-reconciliations)
5. [Reconciliation Workspace Overview](#reconciliation-workspace-overview)
6. [Reconciliation Workflow](#reconciliation-workflow)
7. [Auto-Match Feature](#auto-match-feature)
8. [Bank Adjustments](#bank-adjustments)
9. [Composite Matching](#composite-matching)
10. [Finalizing Reconciliations](#finalizing-reconciliations)
11. [Common Scenarios](#common-scenarios)
12. [Troubleshooting](#troubleshooting)
13. [Best Practices](#best-practices)

---

## Introduction

### What is Bank Reconciliation?

Bank reconciliation is the accounting process of comparing your company's bank statement to your internal accounting records (General Ledger) to ensure they match. This process helps:

- **Detect errors** in your books or bank statement
- **Identify fraudulent transactions**
- **Ensure accurate cash balances**
- **Catch bank fees, interest, and other adjustments**
- **Verify all transactions are recorded**

### How the System Works

The accounting system provides a **dual-panel reconciliation workspace** where you:

1. **Left Panel:** View and clear General Ledger (GL) transactions
2. **Right Panel:** View and clear Bank Statement transactions
3. **Match transactions** between both sides
4. **Create adjustments** for bank fees, interest, etc.
5. **Balance and lock** when everything reconciles

---

## Getting Started

### Prerequisites

Before you begin reconciling, ensure:

1. ✅ **Bank account exists** in the system
2. ✅ **GL account linked** to the bank account (e.g., 1021 - Checking Account)
3. ✅ **Journal entries posted** for the period you're reconciling
4. ✅ **Bank statement** available (paper or PDF)

### Accessing Banking Features

**Navigation Path:**
```
Accounting System → Banking → Bank Accounts
```

**URL:** `https://rm.swhgrp.com/accounting/bank-accounts`

---

## Bank Account Setup

### Step 1: Create a Bank Account

1. Navigate to **Banking → Bank Accounts**
2. Click **"+ Add Bank Account"** button
3. Fill in the required fields:

| Field | Description | Example |
|-------|-------------|---------|
| **Account Name** | Descriptive name | "Chase Business Checking" |
| **Bank Name** | Name of the bank | "Chase Bank" |
| **Account Number** | Last 4 digits recommended | "****1234" |
| **Routing Number** | Bank routing number | "021000021" |
| **Account Type** | Checking, Savings, etc. | "Checking" |
| **GL Account** | Linked GL account | "1021 - Checking Account" |
| **Currency** | USD, CAD, etc. | "USD" |
| **Status** | Active/Inactive | "Active" |

4. Click **"Save"**

### Step 2: Verify GL Account Link

**Important:** The bank account MUST be linked to a GL account. This is the account that appears in your General Ledger for all checking deposits and payments.

**To Verify:**
1. Go to **General Ledger → Chart of Accounts**
2. Find your checking account (e.g., 1021)
3. Note the account number - you'll need this for linking

---

## Creating Bank Reconciliations

### When to Reconcile

Reconcile your bank accounts:
- **Monthly** (at minimum)
- **After receiving bank statement**
- **Before month-end close**
- **When discrepancies are suspected**

### Step 1: Start a New Reconciliation

1. Navigate to **Banking → Bank Accounts**
2. Click on the bank account you want to reconcile
3. Click **"+ New Reconciliation"** button

### Step 2: Enter Statement Information

Fill in the reconciliation details from your bank statement:

| Field | Description | Where to Find on Statement |
|-------|-------------|---------------------------|
| **Statement Date** | Ending date of statement | Top right corner of statement |
| **Beginning Balance** | Starting balance | "Beginning Balance" or previous ending balance |
| **Ending Balance** | Ending balance | "Ending Balance" on statement |
| **Statement Period** | Date range | Top of statement |

**Example:**
```
Statement Date:     October 31, 2025
Beginning Balance:  $25,000.00
Ending Balance:     $27,808.63
Statement Period:   Oct 1, 2025 - Oct 31, 2025
```

### Step 3: Save and Open Workspace

1. Click **"Create Reconciliation"**
2. System automatically opens the **Reconciliation Workspace**

---

## Reconciliation Workspace Overview

### Layout

The workspace is divided into three main sections:

```
┌─────────────────────────────────────────────────────────────┐
│  RECONCILIATION HEADER                                      │
│  Bank: Chase Business Checking | Period: Oct 1-31, 2025    │
│  Beginning: $25,000.00 | Ending: $27,808.63 | Diff: $0.00  │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────────┬──────────────────────────────┐
│  GENERAL LEDGER ENTRIES      │  BANK TRANSACTIONS           │
│  (Left Panel)                │  (Right Panel)               │
│                              │                              │
│  ☐ JE-100 | 10/05 | $500.00 │  ☐ Deposit | 10/05 | $500.00│
│  ☐ JE-101 | 10/12 | $750.00 │  ☐ Check #1001 | -$250.00   │
│  ☐ JE-102 | 10/15 |-$250.00 │  ☐ Bank Fee | -$25.00       │
│                              │                              │
│  [Clear Selected]            │  [Clear Selected]            │
└──────────────────────────────┴──────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ACTIONS                                                     │
│  [Auto-Match] [Lock Reconciliation]                         │
└─────────────────────────────────────────────────────────────┘
```

### Header Information

**Reconciliation Details:**
- Bank account name
- Statement period
- Beginning balance (from your opening entry)
- Ending balance (from bank statement)
- **Difference** - Must be $0.00 to lock

**Balance Calculation:**
```
Difference = Statement Ending Balance - Cleared Balance
```

### Left Panel: General Ledger Entries

Shows journal entry lines that affect the bank's GL account (e.g., 1021).

**Columns:**
- **Checkbox** - Select to clear
- **Date** - Transaction date
- **JE Number** - Journal entry reference
- **Account** - GL account number and name
- **Area** - Location/restaurant
- **Description** - Transaction description
- **Amount** - Debit (positive) or Credit (negative)
- **Status** - Cleared/Uncleared

**Entry Types You'll See:**
- ✅ **Deposits** - Cash/CC sales, customer payments (positive amounts)
- ✅ **Payments** - Vendor checks, ACH payments (negative amounts)
- ✅ **Transfers** - Between bank accounts
- ✅ **Adjustments** - Fees, interest, corrections

### Right Panel: Bank Transactions

Shows transactions from your bank statement.

**Columns:**
- **Checkbox** - Select to clear
- **Date** - Transaction date
- **Description** - From bank statement
- **Type** - Deposit, Withdrawal, Fee, Interest, etc.
- **Check #** - If applicable
- **Amount** - Positive (deposits) or Negative (withdrawals)
- **Status** - Cleared/Uncleared
- **Actions** - Match, Adjust buttons

**Transaction Types:**
- 💰 **Deposits** (Green) - Money in
- 💸 **Withdrawals** (Red) - Money out
- 🏦 **Fees** - Bank charges
- 💵 **Interest** - Interest earned
- 📄 **Checks** - Check numbers displayed

---

## Reconciliation Workflow

### The Basic Process

```
1. Enter Statement Info
   ↓
2. Review GL Entries
   ↓
3. Review Bank Transactions
   ↓
4. Match Transactions (Auto or Manual)
   ↓
5. Add Adjustments (fees, interest, etc.)
   ↓
6. Verify Balance (Difference = $0.00)
   ↓
7. Lock Reconciliation
```

### Step-by-Step Instructions

#### STEP 1: Review Both Sides

**General Ledger (Left Panel):**
1. Review all GL entries for the period
2. Verify amounts match your expectations
3. Note any unusual transactions

**Bank Transactions (Right Panel):**
1. Compare to your bank statement
2. Ensure all bank transactions are listed
3. Note any bank fees, interest, or unknown transactions

#### STEP 2: Match Transactions

You have three options:

**Option A: Auto-Match (Recommended First)**
1. Click **"Auto-Match"** button
2. System finds potential matches based on:
   - Exact amount match
   - Date proximity (±7 days)
   - Description similarity
3. Review suggested matches
4. System shows confidence scores
5. Accept or reject each match

**Option B: Manual Clearing (One-by-One)**
1. Find matching transactions on both sides
2. Check the box on the GL entry
3. Check the box on the bank transaction
4. Click **"Clear Selected"** on each panel
5. Transactions marked as cleared

**Option C: Bulk Clearing**
1. Select multiple transactions on one side
2. Click **"Clear Selected"**
3. All selected items marked as cleared

#### STEP 3: Handle Unmatched Items

After auto-match and manual clearing, you'll have unmatched items. These typically fall into categories:

**A. Bank Fees/Interest** (needs adjustment)
- Monthly maintenance fee
- Wire transfer fees
- NSF charges
- Interest income

**Action:** Use [Bank Adjustments](#bank-adjustments) feature

**B. Timing Differences** (reconciling items)
- Outstanding checks (in GL, not yet cleared bank)
- Deposits in transit (in GL, not yet on statement)

**Action:** Leave uncleared - will clear next month

**C. Missing GL Entries** (needs recording)
- Automatic payments you forgot to record
- Direct deposits
- Vendor ACH debits

**Action:** Create journal entry first, then match

**D. Errors** (needs correction)
- Wrong amounts entered
- Duplicate entries
- Coding errors

**Action:** Create correcting journal entry

#### STEP 4: Create Adjustments

For bank fees, interest, and other bank-initiated transactions:

1. Find the unmatched bank transaction
2. Click **"Add Adjustment"** button
3. Fill in the adjustment modal (see [Bank Adjustments](#bank-adjustments))
4. Click **"Create Adjustment"**
5. Transaction automatically cleared

#### STEP 5: Verify Balance

Watch the **Difference** amount in the header:

```
Ending Balance:    $27,808.63  (from bank statement)
Cleared Balance:   $27,808.63  (GL + Bank cleared items)
─────────────────────────────
Difference:        $0.00       ✅ Ready to lock!
```

**If Difference ≠ $0.00:**
- Recheck uncleared items
- Verify you entered correct ending balance
- Look for duplicate clearings
- Check for missed transactions

#### STEP 6: Lock Reconciliation

Once difference = $0.00:

1. Click **"Lock Reconciliation"** button
2. Confirm the lock
3. Reconciliation status changes to "Locked"
4. No further changes allowed (prevents tampering)

**To Unlock:**
- Contact system administrator
- Requires approval
- Creates audit trail

---

## Auto-Match Feature

### How Auto-Match Works

The system uses intelligent matching algorithms to find potential matches between GL entries and bank transactions.

**Matching Criteria:**
1. **Exact Amount Match** (highest priority)
2. **Date Proximity** (within ±7 days)
3. **Description Similarity** (fuzzy text matching)
4. **Pattern Recognition** (check numbers, ACH, recurring)

**Confidence Scores:**
- **90-100%** - Very high confidence (exact amount + date + description)
- **70-89%** - High confidence (exact amount + date or description)
- **50-69%** - Medium confidence (amount match only)
- **<50%** - Low confidence (weak match, review carefully)

### Using Auto-Match

**Step 1: Click Auto-Match Button**
```
[Auto-Match] button in action bar
```

**Step 2: Review Suggestions**

System displays suggested matches in a modal:

```
┌─────────────────────────────────────────────────────────────┐
│  AUTO-MATCH SUGGESTIONS                                     │
├─────────────────────────────────────────────────────────────┤
│  Match 1 of 8                        Confidence: 95% ✅     │
│                                                              │
│  GL: JE-205 | 10/05/2025 | Credit Card Deposit | $1,847.50 │
│  Bank: 10/05/2025 | CC BATCH DEPOSIT | $1,847.50          │
│                                                              │
│  [Accept Match]  [Skip]  [Reject All]                       │
└─────────────────────────────────────────────────────────────┘
```

**Step 3: Accept or Skip**
- **Accept** - Marks both sides as cleared
- **Skip** - Move to next suggestion
- **Reject All** - Close without accepting any

**Step 4: Repeat**
Continue until all high-confidence matches are reviewed.

### Auto-Match Tips

✅ **Best Practices:**
- Run auto-match FIRST before manual clearing
- Accept high-confidence matches (>90%)
- Review medium-confidence matches (70-89%) carefully
- Skip low-confidence matches (<70%) and match manually

❌ **Common Mistakes:**
- Blindly accepting all suggestions without review
- Not verifying amounts and dates
- Matching wrong transactions just to balance

---

## Bank Adjustments

### What Are Bank Adjustments?

Bank adjustments are transactions that appear on your **bank statement** but don't yet exist in your **General Ledger**.

**Common Examples:**
- Monthly bank fees
- Wire transfer charges
- Interest income
- NSF (bounced check) charges
- Automatic payments you forgot to record

### When to Use Adjustments

Use the adjustment feature when you have a bank transaction that:
1. ✅ Appears on the bank statement
2. ✅ Does NOT have a matching GL entry
3. ✅ Was initiated by the bank (not by you)
4. ✅ Needs to be recorded in your books

### How to Create an Adjustment

**Step 1: Identify the Transaction**

In the reconciliation workspace, find an unmatched bank transaction:
```
☐ 10/28/2025 | MONTHLY ACCOUNT MAINTENANCE FEE | -$25.00
   [Add Adjustment] button appears
```

**Step 2: Click "Add Adjustment"**

The Bank Adjustment modal opens:

```
┌─────────────────────────────────────────────────────────────┐
│  ⊕ ADD BANK ADJUSTMENT                                   [X]│
├─────────────────────────────────────────────────────────────┤
│  ℹ️  Transaction: MONTHLY ACCOUNT MAINTENANCE FEE           │
│      Amount: $25.00                                         │
│                                                              │
│  Adjustment Type                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ -- Select Type --                                ▼   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  GL Account                                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ -- Select Account --                             ▼   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Description                                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ MONTHLY ACCOUNT MAINTENANCE FEE                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Transaction Date                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 10/28/2025                                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Amount                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 25                                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Journal Entry Preview:                                     │
│  Select all fields to see preview                           │
│                                                              │
│  [Cancel]                         [✓ Create Adjustment]     │
└─────────────────────────────────────────────────────────────┘
```

**Step 3: Select Adjustment Type**

Choose from predefined types:

| Type | When to Use | Auto-Populates GL Account |
|------|-------------|---------------------------|
| **Bank Fee** | Monthly fees, maintenance charges | 7425 - Bank Charges |
| **Interest** | Interest earned on account | 9330 - Interest Income |
| **NSF Charge** | Bounced check fees | 7525 - Late Fees |
| **Service Charge** | One-time bank charges | 7425 - Bank Charges |
| **Wire Fee** | Wire transfer fees | 7425 - Bank Charges |
| **Other Income** | Miscellaneous income | 9330 - Interest Income |
| **Other Expense** | Miscellaneous expenses | 7140 - Vendor delivery charge |
| **Custom** | Anything else | Shows all expense/income accounts |

**Step 4: Verify GL Account**

The GL Account field auto-populates based on the adjustment type.

**For "Bank Fee" example:**
```
GL Account: 7425 - Bank Charges  ✅ (auto-selected)
```

**If you selected "Custom":**
- Dropdown shows all expense and income accounts
- Select the appropriate account manually

**Step 5: Review Journal Entry Preview**

Once all fields are filled, the preview appears:

```
Journal Entry Preview:
┌────────────────────────────────────────────┐
│  DR  7425 - Bank Charges         $25.00   │
│  CR  1021 - Checking Account     $25.00   │
└────────────────────────────────────────────┘
```

**Verify:**
- ✅ Debit and Credit are correct
- ✅ Amounts match
- ✅ GL accounts are appropriate

**Step 6: Create Adjustment**

1. Click **"Create Adjustment"** button
2. System creates journal entry automatically
3. Success message appears:
   ```
   Bank adjustment created!
   Journal Entry: JE-2025-042
   Transaction marked as cleared
   ```
4. Modal closes
5. Workspace refreshes
6. Transaction now shows as cleared

### Adjustment Examples

#### Example 1: Bank Fee

**Bank Transaction:**
```
Date: 10/28/2025
Description: MONTHLY ACCOUNT MAINTENANCE FEE
Amount: -$25.00
```

**Adjustment:**
- Type: Bank Fee
- GL Account: 7425 - Bank Charges
- Journal Entry Created:
  ```
  DR 7425 Bank Charges           $25.00
  CR 1021 Checking Account       $25.00
  ```

**Result:** Expense recorded, checking account reduced

---

#### Example 2: Interest Income

**Bank Transaction:**
```
Date: 10/31/2025
Description: INTEREST EARNED - OCTOBER 2025
Amount: +$12.50
```

**Adjustment:**
- Type: Interest
- GL Account: 9330 - Interest Income
- Journal Entry Created:
  ```
  DR 1021 Checking Account       $12.50
  CR 9330 Interest Income        $12.50
  ```

**Result:** Income recorded, checking account increased

---

#### Example 3: Custom Expense (Gas Purchase)

**Bank Transaction:**
```
Date: 10/08/2025
Description: DEBIT CARD - CHEVRON #4521 SAN DIEGO CA
Amount: -$127.45
```

**Adjustment:**
- Type: Custom
- GL Account: (manually select) 6500 - Auto Expense
- Journal Entry Created:
  ```
  DR 6500 Auto Expense           $127.45
  CR 1021 Checking Account       $127.45
  ```

**Result:** Auto expense recorded, checking account reduced

---

#### Example 4: Recurring Utility (Phone Bill)

**Bank Transaction:**
```
Date: 10/14/2025
Description: ACH DEBIT - AT&T BUSINESS SERVICES
Amount: -$189.99
```

**Adjustment:**
- Type: Custom
- GL Account: (manually select) 6200 - Telephone Expense
- Journal Entry Created:
  ```
  DR 6200 Telephone Expense      $189.99
  CR 1021 Checking Account       $189.99
  ```

**Result:** Telephone expense recorded, checking account reduced

---

### Adjustment Tips

✅ **Best Practices:**
- Use predefined types when possible (faster, consistent)
- Verify GL accounts are correct before creating
- Add detailed descriptions for future reference
- Review journal entry preview before confirming

❌ **Common Mistakes:**
- Using "Custom" for everything (bypasses smart defaults)
- Wrong GL account selection
- Not reviewing JE preview
- Duplicate adjustments (creates duplicate expenses)

---

## Composite Matching

### What is Composite Matching?

Composite matching allows you to match **multiple GL entries to ONE bank transaction**.

**Common Use Case:**
```
Bank Statement:
  Oct 15: Credit Card Deposit  $3,500.00  (one line)

General Ledger:
  Oct 12: Daily CC Sales       $1,200.00  (JE-101)
  Oct 13: Daily CC Sales       $1,150.00  (JE-102)
  Oct 14: Daily CC Sales       $1,150.00  (JE-103)
  Total:                       $3,500.00  (three lines)
```

Without composite matching, you can't match these because it's 3-to-1.

### When to Use Composite Matching

Use composite matching when:
1. ✅ Multiple small GL entries add up to one bank deposit
2. ✅ Credit card batches (multiple days → 1 deposit)
3. ✅ Cash deposits (multiple cash bags → 1 bank deposit)
4. ✅ Third-party delivery settlements (multiple days → 1 settlement)

### How to Use Composite Matching

**Step 1: Identify the Deposit**

Find a bank deposit that represents multiple GL entries:
```
☐ 10/15/2025 | CREDIT CARD BATCH DEPOSIT | $3,500.00
   [Match Composite] button appears
```

**Step 2: Click "Match Composite"**

The Composite Matching modal opens:

```
┌─────────────────────────────────────────────────────────────┐
│  COMPOSITE MATCH - CREDIT CARD DEPOSIT                   [X]│
├─────────────────────────────────────────────────────────────┤
│  Bank Deposit Info:                                         │
│  Date: 10/15/2025                                           │
│  Description: CREDIT CARD BATCH DEPOSIT                     │
│  Amount: $3,500.00                                          │
├─────────────────────────────────────────────────────────────┤
│  Filter Undeposited Lines:                                  │
│  GL Account: [1090 - Undeposited CC] ▼                      │
│  Date Range: [10/08/2025] to [10/15/2025]                  │
│  [Search]                                                    │
├─────────────────────────────────────────────────────────────┤
│  Select GL Lines to Match:                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ☐ Date    JE#    Account  Area  Description   Amount │  │
│  │ ☑ 10/12  JE-101  1090    SG01  Daily CC Sales $1,200 │  │
│  │ ☑ 10/13  JE-102  1090    SG01  Daily CC Sales $1,150 │  │
│  │ ☑ 10/14  JE-103  1090    SG01  Daily CC Sales $1,150 │  │
│  └──────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  Matching Summary:                                          │
│  Bank Amount:      $3,500.00                                │
│  Selected Total:   $3,500.00                                │
│  Difference:       $0.00  ✅                                │
│                                                              │
│  [Cancel]      [✓ Confirm Match & Create Clearing Entry]   │
└─────────────────────────────────────────────────────────────┘
```

**Step 3: Filter Undeposited Lines**

Set filters to find the GL entries:

| Filter | Purpose | Default |
|--------|---------|---------|
| **GL Account** | Undeposited account to search | 1090 - Undeposited CC |
| **Start Date** | Beginning of date range | 7 days before deposit |
| **End Date** | End of date range | Deposit date |

**Step 4: Click "Search"**

System loads matching GL lines from undeposited accounts.

**Step 5: Select GL Lines**

Click checkboxes to select lines to match:
- Click individual checkboxes
- Click rows to toggle selection
- Use "Select All" for all lines

**Watch the Matching Summary:**
```
Bank Amount:     $3,500.00  (fixed)
Selected Total:  $3,500.00  (updates as you select)
Difference:      $0.00      (must be $0.00 to confirm)
```

**Step 6: Verify Match**

Ensure:
- ✅ Difference = $0.00
- ✅ All correct lines selected
- ✅ Amounts add up exactly

**Step 7: Confirm Match**

1. Click **"Confirm Match & Create Clearing Entry"**
2. System creates:
   - Composite match records (links GL lines to bank transaction)
   - Clearing journal entry automatically
3. Success message:
   ```
   Composite match created!
   Journal Entry: JE-2025-043
   Matched 3 lines to deposit
   ```

### Clearing Journal Entry

The system automatically creates a clearing entry to move funds from Undeposited to Checking:

**Example:**
```
JE-2025-043 | 10/15/2025 | Composite match clearing

DR 1021 Checking Account           $3,500.00
CR 1090 Undeposited CC              $3,500.00

Description: "Composite match clearing - Deposit $3,500.00 matched to 3 DSS entries"
```

**Why This Entry?**

When you record daily sales:
```
DR 1090 Undeposited CC    $1,200.00
CR 4000 Sales             $1,200.00
```

This puts money in "Undeposited" - meaning you have cash/CC slips but haven't deposited yet.

When the bank deposit clears:
```
DR 1021 Checking          $3,500.00
CR 1090 Undeposited CC    $3,500.00
```

This moves the money from "Undeposited" to "Checking" - matching reality.

### Composite Matching Tips

✅ **Best Practices:**
- Use undeposited accounts (1090, 1091, 1095) for daily sales
- Match deposits to the correct GL account (CC vs Cash vs Delivery)
- Verify dates make sense (sales before deposit)
- Double-check amounts add up exactly

❌ **Common Mistakes:**
- Selecting lines from wrong GL account
- Including lines that are too old
- Mismatching amounts (difference ≠ $0)
- Not creating clearing entry (system does this automatically)

---

## Finalizing Reconciliations

### Pre-Lock Checklist

Before locking, verify:

- [ ] All transactions reviewed
- [ ] Auto-match run and suggestions accepted/rejected
- [ ] Manual matches completed
- [ ] Bank adjustments created for fees/interest
- [ ] Composite matches created where needed
- [ ] **Difference = $0.00**
- [ ] Outstanding checks and deposits in transit are reasonable
- [ ] No obvious errors or duplicates

### Locking the Reconciliation

**Step 1: Verify Balance**

Check the header:
```
Difference: $0.00  ✅
```

If not $0.00, do NOT lock. Find the discrepancy first.

**Step 2: Click "Lock Reconciliation"**

Button appears in the action bar when difference = $0.00.

**Step 3: Confirm Lock**

```
┌─────────────────────────────────────────────────────────────┐
│  CONFIRM LOCK                                               │
├─────────────────────────────────────────────────────────────┤
│  Are you sure you want to lock this reconciliation?         │
│                                                              │
│  Once locked, no changes can be made without admin          │
│  approval.                                                   │
│                                                              │
│  Statement Date: October 31, 2025                           │
│  Ending Balance: $27,808.63                                 │
│  Difference: $0.00                                          │
│                                                              │
│  [Cancel]                                        [Lock]      │
└─────────────────────────────────────────────────────────────┘
```

**Step 4: Locked Confirmation**

```
✅ Reconciliation Locked Successfully

Status: Locked
Locked By: John Smith
Locked Date: 10/31/2025 3:45 PM
```

### What Happens When Locked?

1. ✅ Status changes to "Locked"
2. ✅ No edits allowed
3. ✅ Transactions cannot be un-cleared
4. ✅ Provides audit trail
5. ✅ Prevents tampering
6. ✅ Creates permanent record

### Unlocking a Reconciliation

**When Needed:**
- Error discovered after locking
- Need to add missed transaction
- Correction required

**How to Unlock:**
1. Contact system administrator
2. Provide reason for unlock
3. Admin reviews and approves
4. Admin unlocks in system
5. **Audit trail created** (who, when, why)

**Important:** Unlocking creates an audit record. Use sparingly and only when necessary.

---

## Common Scenarios

### Scenario 1: Outstanding Checks

**Situation:**
You wrote checks that haven't cleared the bank yet.

**What You See:**
- GL Entry: Check #1005 to Sysco Foods (-$1,250.00) ✅ Recorded in GL
- Bank Statement: No matching transaction ❌

**What to Do:**
1. Leave the GL entry **uncleared**
2. Do NOT create an adjustment
3. This is normal - it's a **reconciling item**
4. Will clear on next month's reconciliation when check clears bank

**Balance Impact:**
```
GL Cleared Balance:    $26,500.00  (doesn't include check)
Bank Ending Balance:   $27,750.00  (check hasn't cleared yet)
Difference:            $1,250.00   (the outstanding check)
```

**Note:** Outstanding checks are OK. They're timing differences, not errors.

---

### Scenario 2: Deposits in Transit

**Situation:**
You deposited money at the end of the month, but it doesn't appear on the bank statement yet.

**What You See:**
- GL Entry: Cash Deposit $850.00 ✅ Recorded in GL
- Bank Statement: No matching transaction ❌

**What to Do:**
1. Leave the GL entry **uncleared**
2. Do NOT create an adjustment
3. This is normal - it's a **reconciling item**
4. Will clear on next month's reconciliation

**Balance Impact:**
```
GL Cleared Balance:    $28,650.00  (includes deposit)
Bank Ending Balance:   $27,800.00  (deposit not there yet)
Difference:            -$850.00    (the deposit in transit)
```

---

### Scenario 3: Bank Error

**Situation:**
The bank made a mistake - charged you twice for the same fee.

**What You See:**
- Bank Statement: Bank Fee (-$25.00) ✅ Correct
- Bank Statement: Bank Fee (-$25.00) ❌ Duplicate!

**What to Do:**
1. **DO NOT** create adjustment for the duplicate
2. Leave it uncleared
3. Contact your bank immediately
4. Bank will issue a credit/reversal
5. When reversal appears, match it to the duplicate

**Alternative:**
If bank confirms it's their error but won't show on statement:
1. Create a manual journal entry for the reversal
2. Match the duplicate fee to the reversal entry

---

### Scenario 4: Missed Journal Entry

**Situation:**
You forgot to record a payment in your GL.

**What You See:**
- Bank Statement: ACH Payment to Verizon (-$215.00) ✅
- GL: No matching entry ❌

**What to Do:**
1. **Exit reconciliation workspace**
2. Go to **General Ledger → Journal Entries**
3. Create a new journal entry:
   ```
   DR 6200 Telephone Expense    $215.00
   CR 1021 Checking Account     $215.00
   ```
4. Post the entry
5. **Return to reconciliation workspace**
6. Match the new GL entry to the bank transaction

**Do NOT use Bank Adjustment for this!**
Adjustments are for bank-initiated transactions only.

---

### Scenario 5: Wrong Amount Entered

**Situation:**
You entered the wrong amount in a journal entry.

**What You See:**
- GL Entry: Vendor Payment $500.00 ❌ (should be $550.00)
- Bank Statement: Check #1010 cleared for $550.00 ✅

**What to Do:**
1. **Do NOT try to match** - amounts don't match
2. Create a **correcting journal entry**:
   ```
   DR 6000 Expenses             $50.00
   CR 1021 Checking Account     $50.00
   Description: "Correction - Check #1010 actual $550, recorded $500"
   ```
3. Now you have:
   - Original entry: $500.00
   - Correction: $50.00
   - **Total: $550.00** ✅
4. Use **composite matching** to match both GL entries to the $550 bank transaction

---

### Scenario 6: Credit Card Processing Fees

**Situation:**
You deposited $2,000 in credit card sales, but bank only shows $1,940 (they took $60 fee).

**What You See:**
- GL Entry: Undeposited CC $2,000.00 ✅
- Bank Statement: CC Batch Deposit $1,940.00 ✅

**What to Do:**

**Option A: Manual Adjustment (Recommended)**
1. Create journal entry for the fee:
   ```
   DR 7420 Credit Card Fees     $60.00
   CR 1090 Undeposited CC       $60.00
   ```
2. Now Undeposited CC = $1,940 (matches bank)
3. Match the $1,940 GL balance to the $1,940 bank deposit

**Option B: Use Bank Adjustment**
1. Click "Add Adjustment" on the bank transaction
2. Type: Custom
3. GL Account: 7420 - Credit Card Fees
4. Amount: $60.00
5. Creates the adjustment automatically

**Result:**
```
GL Entries:
  Undeposited CC         $2,000.00  DR
  CC Fees                $60.00     DR
  Checking              $1,940.00   CR (net)
```

---

## Troubleshooting

### Issue: Difference Won't Zero Out

**Symptom:**
No matter what you clear, the difference never reaches $0.00.

**Possible Causes:**

1. **Wrong Ending Balance Entered**
   - **Fix:** Edit reconciliation, verify ending balance from statement

2. **Outstanding Checks/Deposits**
   - **Fix:** These are normal - leave them uncleared

3. **Duplicate Clearing**
   - **Fix:** Uncheck duplicates, clear once only

4. **Missing Transaction**
   - **Fix:** Look for bank transactions without GL entries

5. **Math Error**
   - **Fix:** Manually add up cleared items to verify totals

**Debugging Steps:**
```
1. Calculate manually:
   Beginning Balance:        $25,000.00
   + Deposits cleared:       +$8,500.00
   - Withdrawals cleared:    -$5,691.37
   = Expected Ending:        $27,808.63

2. Compare to bank statement ending balance
3. Find the discrepancy
```

---

### Issue: Auto-Match Finds Nothing

**Symptom:**
Click "Auto-Match" but it says "No matches found."

**Possible Causes:**

1. **All Transactions Already Cleared**
   - **Fix:** Nothing to do - this is good!

2. **Date Mismatch Too Large**
   - **Fix:** Auto-match looks ±7 days. Manual match if dates are far apart.

3. **Amount Differences**
   - **Fix:** GL and bank amounts don't match (fees, errors, etc.)

4. **No GL Entries Exist**
   - **Fix:** Record missing journal entries first

**Workaround:**
Use manual clearing for mismatched dates or amounts.

---

### Issue: Can't Lock Reconciliation

**Symptom:**
"Lock Reconciliation" button is disabled/grayed out.

**Possible Causes:**

1. **Difference ≠ $0.00**
   - **Fix:** Balance the reconciliation first

2. **Already Locked**
   - **Fix:** Check status - if locked, need to unlock first

3. **Insufficient Permissions**
   - **Fix:** Contact administrator for access

**Check:**
Look at the header - difference must show $0.00 exactly.

---

### Issue: Bank Transaction Shows Twice

**Symptom:**
Same transaction appears multiple times in bank panel.

**Possible Causes:**

1. **Duplicate Import**
   - **Fix:** Delete duplicate bank transactions

2. **Bank Actually Charged Twice**
   - **Fix:** Contact bank for reversal

3. **Different Transactions with Same Amount**
   - **Fix:** Verify dates and descriptions - they might be different

**How to Delete:**
1. Find the duplicate
2. Right-click → Delete (if permissions allow)
3. Or contact administrator

---

### Issue: GL Entry Missing from Workspace

**Symptom:**
You know a GL entry exists, but it doesn't appear in the workspace.

**Possible Causes:**

1. **Wrong GL Account**
   - Entry affects account other than the bank account (e.g., 1022 instead of 1021)
   - **Fix:** Verify which GL account the entry posted to

2. **Wrong Date Range**
   - Entry dated outside the reconciliation period
   - **Fix:** Check entry date vs. statement period

3. **Entry Not Posted**
   - Entry still in "Draft" status
   - **Fix:** Post the journal entry

4. **Already Cleared**
   - Entry cleared in previous reconciliation
   - **Fix:** Check reconciliation history

**Verification:**
1. Go to General Ledger → Account Detail for 1021
2. Search for the transaction
3. Verify date, amount, status

---

## Best Practices

### Monthly Reconciliation Schedule

**Recommended Timeline:**
```
Day 1-3:   Receive bank statement
Day 4:     Start reconciliation
Day 5-7:   Complete matching and adjustments
Day 8:     Lock reconciliation
Day 9-10:  Review and month-end close
```

**Don't Wait:**
- Reconcile as soon as statement available
- Easier to remember transactions when fresh
- Allows time to fix errors before month-end close

---

### Organization Tips

**Before You Start:**
1. ✅ Gather bank statement (paper or PDF)
2. ✅ Review prior month's reconciliation
3. ✅ Note outstanding checks from last month
4. ✅ Have GL account numbers handy
5. ✅ Set aside 1-2 hours of uninterrupted time

**During Reconciliation:**
1. ✅ Run auto-match first
2. ✅ Clear obvious matches
3. ✅ Group similar transactions (fees together, deposits together)
4. ✅ Use bank statement as checklist - mark off each line as matched
5. ✅ Save frequently (workspace auto-saves, but refresh to be safe)

**After Reconciliation:**
1. ✅ Print or save PDF of final reconciliation
2. ✅ Note outstanding checks/deposits for next month
3. ✅ File bank statement with reconciliation report
4. ✅ Document any unusual items

---

### Accuracy Best Practices

✅ **Do:**
- Reconcile monthly (at minimum)
- Verify beginning balance matches prior ending balance
- Review all transactions, even if auto-matched
- Create adjustments for all bank fees and interest
- Lock reconciliation when complete
- Keep documentation of reconciling items

❌ **Don't:**
- Rush through reconciliation to make it balance
- Force matches that don't make sense
- Ignore small differences ("close enough")
- Lock with outstanding difference
- Skip months (creates compounding errors)
- Clear transactions without verifying amounts

---

### Security Best Practices

**Access Control:**
- Only authorized users should reconcile
- Separate duties: person recording transactions ≠ person reconciling
- Require approval for unlocking locked reconciliations

**Audit Trail:**
- System tracks who cleared what and when
- Locked reconciliations prevent tampering
- Unlock requires admin approval with reason

**Documentation:**
- Keep bank statements (paper or digital) for 7 years
- Print/PDF final reconciliation reports
- Document reasons for adjustments and corrections

---

### Efficiency Tips

**Keyboard Shortcuts:**
- `Space` - Toggle checkbox selection
- `Ctrl+A` - Select all (in table)
- `Esc` - Close modals
- `Tab` - Navigate fields

**Workflow Hacks:**
1. Use two monitors - bank statement on one, workspace on other
2. Print bank statement and physically check off items as matched
3. Create recurring adjustments template for monthly fees
4. Use consistent naming for journal entries (easier to auto-match)

**Time Savers:**
- Pre-code bank downloads if your bank provides CSV
- Create vendor rules for recurring payments
- Use composite matching for credit card batches
- Set up auto-match to run on statement import

---

## Summary

### Key Takeaways

✅ **Reconciliation is critical** for accurate financial reporting
✅ **Auto-match saves time** - use it first
✅ **Bank adjustments** record bank-initiated transactions
✅ **Composite matching** handles multiple GL lines → 1 bank deposit
✅ **Difference must be $0.00** before locking
✅ **Outstanding items are normal** - timing differences
✅ **Lock reconciliations** to prevent changes and maintain audit trail

### The Golden Rule

> **Your cleared balance must equal the bank's ending balance. If it doesn't, find out why. Never force a reconciliation to balance.**

---

## Support and Resources

### Need Help?

**System Administrator:**
- Email: admin@swhgrp.com
- Phone: (555) 123-4567

**Accounting Department:**
- Email: accounting@swhgrp.com
- Phone: (555) 123-4568

**Training Materials:**
- [Video Tutorial: Basic Reconciliation](#) (15 minutes)
- [Video Tutorial: Bank Adjustments](#) (5 minutes)
- [Video Tutorial: Composite Matching](#) (10 minutes)

**Documentation:**
- `/docs/banking/` - All banking documentation
- `/docs/testing/banking_user_test_guide.md` - Testing guide
- `/docs/banking/PHASE_1B_COMPLETION_SUMMARY.md` - Technical summary

---

**End of Manual**
**Version 1.0 | October 21, 2025**
**© 2025 SW Hospitality Group - Accounting System**
