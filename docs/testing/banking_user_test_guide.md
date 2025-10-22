# Banking Module - User Testing Guide

## Prerequisites
- You must be logged into the accounting system at https://rm.swhgrp.com/accounting
- Test bank account "Test Chase Business Checking" has been created with ID 2
- 8 test transactions have been loaded (Jan 15-20, 2025)

---

## Test 1: View Bank Accounts List

### Steps:
1. Click **Banking** in the left navigation menu
2. Click **Bank Accounts**

### Expected Results:
- ✅ Page loads successfully
- ✅ You see at least 2 bank accounts:
  - "Seaside Checking"
  - "Test Chase Business Checking"
- ✅ Test account shows:
  - Balance: $10,500.00
  - Unreconciled: 8 transactions
  - Status: Active badge
  - Sync: Manual (upload icon)

### Screenshot Areas:
- Account cards with balances
- Unreconciled transaction count badge

---

## Test 2: View Bank Account Details

### Steps:
1. From Bank Accounts list, click **View** button on "Test Chase Business Checking"

### Expected Results:
- ✅ Detail page loads
- ✅ Header shows account name and status
- ✅ Four stat cards display:
  - Current Balance: $10,500.00
  - Unreconciled: 8 transactions
  - Last Sync: Never
  - Last Reconciliation: Never
- ✅ Transactions table shows 8 rows:
  1. ATM Withdrawal: -$200.00 (Jan 20)
  2. Check #1002 - Utilities: -$345.00 (Jan 19)
  3. Monthly Bank Fee: -$15.00 (Jan 18)
  4. Customer Payment: $1,200.00 (Jan 18)
  5. Wire Transfer: -$2,500.00 (Jan 17)
  6. Amazon Purchase: -$89.99 (Jan 16)
  7. Check #1001: -$150.50 (Jan 16)
  8. Payroll Deposit: $5,000.00 (Jan 15)

### Try These Features:
- ✅ Click on a transaction to view details
- ✅ Use search box to filter transactions
- ✅ Try date filters

---

## Test 3: Create New Bank Account

### Steps:
1. From Bank Accounts list, click **Add Bank Account** button
2. Fill in the form:
   - **Account Name:** "My Test Savings Account"
   - **Account Type:** Savings
   - **Bank/Institution:** "Wells Fargo"
   - **GL Account:** Select any asset account (e.g., "1010 - Checking Account")
   - **Opening Balance:** 5000.00
   - **Sync Method:** Manual Import
3. Click **Save Account**

### Expected Results:
- ✅ Modal closes
- ✅ Success message appears
- ✅ New account appears in the account list
- ✅ GL Account dropdown shows proper account names (not "undefined")

### What to Check:
- GL Account dropdown has real account names like "1005 - Cash on Hand"
- All fields save correctly
- Account card shows opening balance

---

## Test 4: Import CSV Statement

### Steps:
1. Download the test CSV file from `/tmp/sample_chase_statement.csv`
2. Go to "Test Chase Business Checking" detail page
3. Click **Import Statement** button
4. Select:
   - **File Format:** Chase CSV (or Auto-detect)
   - **Statement File:** Choose the downloaded CSV file
5. Click **Import**

### Expected Results:
- ✅ Progress bar appears
- ✅ Success message: "10 transaction(s) imported"
- ✅ Duplicate message if any transactions overlap
- ✅ Transaction count increases from 8 to 18 (or shows duplicates skipped)
- ✅ Transactions appear in the table

### What to Check:
- New transactions appear in the list
- Dates are correctly parsed
- Amounts show correct positive/negative
- Check numbers are captured
- No duplicates created

---

## Test 5: Create a Reconciliation

### Steps:
1. From "Test Chase Business Checking" detail page, click **Reconcile** button
   OR navigate to Banking → Reconciliations → Start Reconciliation
2. Fill in reconciliation form:
   - **Bank Account:** Test Chase Business Checking
   - **Statement Date:** 01/31/2025
   - **Reconciliation Date:** (today's date - should be pre-filled)
   - **Beginning Balance:** 10000.00
   - **Ending Balance:** 10500.00 (matches the net of all transactions)
3. Click **Start Reconciliation**

### Expected Results:
- ✅ Reconciliation workspace loads
- ✅ Header shows account name and status
- ✅ Four summary cards display:
  - Statement Balance: $10,500.00
  - Book Balance: (calculated from GL)
  - Cleared Balance: $0.00 (initially)
  - Difference: (some amount)
- ✅ Left panel shows bank transactions (8 or 18 depending on import test)
- ✅ Right panel shows GL entries
- ✅ All transactions have checkboxes

---

## Test 6: Reconcile Transactions

### Steps:
1. In the left panel (Bank Transactions):
   - Check the box next to "Payroll Deposit: $5,000.00"
   - Check "Customer Payment: $1,200.00"
   - Click **Clear Selected** button
2. Watch the summary cards update
3. Continue selecting and clearing transactions until difference = $0.00
4. Once balanced, click **Lock** button

### Expected Results:
- ✅ Transactions turn blue/green when cleared
- ✅ Checkboxes become disabled after clearing
- ✅ Cleared Balance updates in real-time
- ✅ Difference recalculates automatically
- ✅ When difference = $0.00:
  - Difference card shows green checkmark
  - Lock button becomes enabled
- ✅ Clicking Lock shows confirmation
- ✅ After locking, redirects to reconciliations list
- ✅ Locked reconciliation shows status "locked" badge

### What to Check:
- Checkboxes work smoothly
- Balance math is correct
- Can't accidentally double-clear a transaction
- Outstanding checks/deposits section updates
- Lock prevents further editing

---

## Test 7: View Reconciliation History

### Steps:
1. Navigate to Banking → Reconciliations
2. View the list of reconciliations

### Expected Results:
- ✅ Locked reconciliation appears in the list
- ✅ Shows correct dates
- ✅ Shows balances and difference
- ✅ Status shows "locked" badge
- ✅ Can filter by account, status, date
- ✅ Locked reconciliations only have "View" button (no delete)

---

## Test 8: Filters and Search

### Steps:
1. Go to Bank Accounts list
2. Try filtering:
   - By status (Active/Inactive)
   - By sync method (Manual/Plaid)
   - By location
   - Search by account name
3. Go to Bank Account detail page
4. Try filtering transactions:
   - By status (Matched/Unmatched/Reconciled)
   - By type (Debit/Credit/Check/Fee)
   - By date range
   - Search by description

### Expected Results:
- ✅ Filters work instantly (no page refresh)
- ✅ Multiple filters can be combined
- ✅ Search is case-insensitive
- ✅ Clear button resets all filters

---

## Test 9: UI/UX Quality Checks

### Check These Aspects:
- ✅ Dark theme consistent across all banking pages
- ✅ Icons are professional Bootstrap Icons (not inconsistent)
- ✅ Mobile responsive (try resizing browser)
- ✅ Loading states show spinners
- ✅ Empty states have helpful messages
- ✅ Error messages are clear
- ✅ Success messages appear and disappear
- ✅ Navigation breadcrumbs work
- ✅ Back buttons function correctly
- ✅ Modals close on Esc key
- ✅ Forms validate required fields

---

## Test 10: Edge Cases

### Try These Scenarios:
1. **Negative Balance:** Create account with negative opening balance
2. **Zero Balance:** Import statement with $0.00 transactions
3. **Large Numbers:** Test with amounts like $1,234,567.89
4. **Special Characters:** Account names with &, ', " characters
5. **Long Descriptions:** Import transaction with 200+ character description
6. **Duplicate Import:** Import same CSV file twice
7. **Wrong Format:** Try importing a non-CSV file
8. **Cancel Actions:** Start reconciliation, then navigate away (should save draft)

---

## Known Limitations

1. **Plaid Sync:** Requires Plaid API credentials to be configured (currently manual only)
2. **Auto-Match:** Requires journal entries in GL to match against
3. **OFX/QFX:** Requires files exported from bank (Chase Web Connect format)

---

## Reporting Issues

If you find any issues, please report:
- **What:** Clear description of the issue
- **Where:** Which page/feature
- **Steps:** How to reproduce
- **Expected:** What should happen
- **Actual:** What actually happened
- **Screenshot:** If applicable

---

## Success Criteria

✅ All 10 tests pass
✅ No console errors in browser
✅ Performance is acceptable
✅ UI matches existing accounting system design
✅ Data saves correctly to database
✅ Reconciliation math is accurate

---

## Additional Features to Explore

Once basic tests pass, try:
- Creating multiple reconciliations for same account
- Viewing reconciliation reports
- Exporting data
- Using keyboard shortcuts
- Testing with different user roles (if applicable)

---

**Test Completion Date:** _____________

**Tested By:** _____________

**Overall Status:** ⬜ PASS  ⬜ FAIL  ⬜ NEEDS WORK

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________
