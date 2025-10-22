# Banking Dashboard - Complete Specification

## Executive Summary
Enterprise-grade banking dashboard for multi-location restaurant operations providing corporate-level visibility and location-level detail for cash management, reconciliation health, and cash flow analytics.

---

## 1. Summary Overview (Top-Level KPIs)

### Purpose
Provide immediate snapshot of overall cash position and banking health across all locations.

### Metrics

#### Primary KPIs (Hero Cards)
1. **Total Cash Balance**
   - Sum of all bank account balances across all locations
   - Color-coded: Green (positive), Red (negative)
   - Comparison: vs. yesterday, vs. last week
   - Data Source: `bank_accounts.current_balance`

2. **GL vs Bank Variance**
   - Difference between GL cash accounts and bank balances
   - Alert threshold: > $1,000 variance
   - Data Source: `SUM(bank_accounts.current_balance) - SUM(gl_balances WHERE account_type='BANK')`

3. **Reconciliation Rate**
   - Percentage of transactions reconciled in last 30 days
   - Target: > 95%
   - Formula: `(reconciled_count / total_count) * 100`
   - Data Source: `bank_transactions.status`

4. **Unreconciled Balance**
   - Total amount of unreconciled transactions
   - Age breakdown: 0-7 days, 8-30 days, 30+ days
   - Data Source: `SUM(bank_transactions.amount WHERE status='unreconciled')`

5. **Outstanding Items**
   - Checks in Transit: Count and total amount
   - Deposits in Transit: Count and total amount
   - Data Source: `bank_reconciliation_items WHERE type IN ('check', 'deposit_in_transit')`

6. **Bank Feed Status**
   - Connected: Count of accounts with active feeds
   - Disconnected: Count requiring reconnection
   - Last Sync: Most recent sync timestamp
   - Data Source: `bank_accounts.feed_status, feed_last_sync`

### Visual Layout
```
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│  Total Cash     │  GL vs Bank     │  Reconciliation │  Unreconciled   │
│  $X,XXX,XXX     │  Variance       │  Rate           │  Balance        │
│  ↑ +2.3% vs LW  │  $X,XXX         │  96.5%          │  $XX,XXX        │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
┌─────────────────┬─────────────────┬─────────────────────────────────────┐
│  Outstanding    │  Bank Feed      │  Last Reconciliation                │
│  Checks: $X,XXX │  Status         │  Most Recent: Yesterday             │
│  Deps: $X,XXX   │  ✓ 12 / ⚠ 1     │  Oldest Gap: 3 days ago (Location 2)│
└─────────────────┴─────────────────┴─────────────────────────────────────┘
```

---

## 2. Location-Level Detail Grid

### Purpose
Granular view of each restaurant's banking status for operational monitoring.

### Columns

| Column | Description | Data Source | Visual Treatment |
|--------|-------------|-------------|------------------|
| Location | Restaurant name | `areas.legal_name` | Bold text + icon |
| Bank Account | Last 4 digits | `bank_accounts.account_number` | Monospace font |
| Bank Balance | Current balance | `bank_accounts.current_balance` | Currency format |
| GL Balance | GL cash account | `SUM(gl_balances WHERE area_id=X)` | Currency format |
| Variance | Bank - GL | Calculated | Red if > $500 |
| Reconciliation % | Last 30 days | Calculated | Progress bar |
| Unmatched | Count of transactions | `COUNT(WHERE status='unreconciled')` | Badge |
| Last Recon | Date | `MAX(reconciliation_date)` | Relative time |
| Feed Status | Connection state | `bank_accounts.feed_status` | Icon: ✓/⚠/✗ |
| Actions | Quick links | N/A | Button group |

### Features
- Sortable columns
- Click row to drill into location detail
- Export to Excel
- Filter by: Location Group, Bank, Status
- Search by location name or account number

### Visual Layout
```
┌──────────────────────────────────────────────────────────────────────────┐
│ Location Banking Detail                           [Filters] [Export CSV] │
├─────────┬───────┬──────────┬──────────┬─────────┬──────┬─────┬─────┬────┤
│Location │ Acct  │ Bank Bal │ GL Bal   │Variance │Recon%│Unm. │Last │Feed│
├─────────┼───────┼──────────┼──────────┼─────────┼──────┼─────┼─────┼────┤
│Seaside  │x1234  │$125,430  │$125,500  │-$70     │ 98%  │  3  │Today│ ✓  │
│Harbor   │x5678  │ $89,234  │ $89,100  │+$134    │ 95%  │  8  │1d ago│✓  │
│Downtown │x9012  │ $67,890  │ $68,500  │-$610 🔴 │ 92%  │ 12  │2d ago│⚠  │
└─────────┴───────┴──────────┴──────────┴─────────┴──────┴─────┴─────┴────┘
```

---

## 3. Cash Flow Metrics

### Purpose
Understand movement of money across time for liquidity planning.

### Visualizations

#### A. Inflow vs Outflow Chart (Line/Area)
- **Time Range**: Last 30 days (daily), Last 12 weeks (weekly), Last 12 months (monthly)
- **Metrics**:
  - Daily Cash Inflows (deposits, sales, transfers in)
  - Daily Cash Outflows (payments, expenses, transfers out)
  - Net Change
- **Data Source**: `bank_transactions` grouped by date and sign(amount)

#### B. Top Inflows Table
| Source | Amount | % of Total | Trend |
|--------|--------|------------|-------|
| Credit Card Sales | $XX,XXX | 45% | ↑ |
| Cash Deposits | $XX,XXX | 30% | → |
| ACH Receipts | $XX,XXX | 25% | ↓ |

#### C. Top Outflows Table
| Category | Amount | % of Total | Trend |
|----------|--------|------------|-------|
| Vendor Payments | $XX,XXX | 40% | ↑ |
| Payroll | $XX,XXX | 35% | → |
| Rent/Utilities | $XX,XXX | 15% | → |

#### D. Cash Burn Rate
- **Definition**: Average daily cash consumption
- **Calculation**: `(Total Outflows - Total Inflows) / Days`
- **Indicator**: Red if burn > $10K/day

#### E. Cash Runway
- **Definition**: Days until cash depleted at current burn rate
- **Calculation**: `Current Balance / Daily Burn Rate`
- **Alert**: < 30 days

### Visual Layout
```
┌───────────────────────────────────────────────────────────────┐
│ Cash Flow - Last 30 Days                 [Daily|Weekly|Monthly]│
│                                                                 │
│    Inflows ─────  Outflows ─────  Net ─────                   │
│  $                                                              │
│  │     /\                                                       │
│  │    /  \          ╱╲                                         │
│  │   /    \    ╱╲  ╱  \                                        │
│  │  /      \  ╱  \╱    \╱\                                     │
│  └──────────────────────────────> Days                         │
│                                                                 │
│  Avg Daily: Inflows $45K | Outflows $42K | Net +$3K           │
└───────────────────────────────────────────────────────────────┘
┌─────────────────────┬─────────────────────┬──────────────────┐
│ Top Inflows         │ Top Outflows        │ Cash Health      │
│ • CC Sales  $XXX    │ • Vendors   $XXX    │ Burn: $X,XXX/day │
│ • Cash Deps $XXX    │ • Payroll   $XXX    │ Runway: 120 days │
│ • ACH       $XXX    │ • Rent      $XXX    │ Status: Healthy✓ │
└─────────────────────┴─────────────────────┴──────────────────┘
```

---

## 4. Reconciliation Health & Alerts

### Purpose
Monitor accuracy, detect anomalies, and surface issues requiring attention.

### Metrics

#### A. Accounts Needing Attention (Priority List)
- **Criteria**:
  1. Unreconciled > 30 days
  2. Variance > $1,000
  3. Bank feed disconnected > 3 days
  4. No reconciliation in 7+ days
- **Display**: Sortable table with urgency indicator

#### B. Auto-Match Success Rate
- **Definition**: % of transactions matched automatically
- **Trend**: Last 30/60/90 days
- **Target**: > 80%
- **Data Source**: `COUNT(matched_automatically) / COUNT(total_transactions)`

#### C. Manual Adjustments
- **Count**: Number of manual journal entries
- **Amount**: Total $ amount of adjustments
- **Trend**: Increasing = process issue
- **Alert**: > 10 adjustments/week

#### D. Composite Match Frequency
- **Definition**: % of transactions matched using composite rules
- **Purpose**: Shows effectiveness of rule-based matching
- **Data Source**: `bank_transaction_matches WHERE match_type='composite'`

#### E. Bank Feed Errors
- **Types**: Connection failed, authentication expired, parsing error
- **Count**: Last 7 days
- **Display**: Error log with retry action

### Visual Layout
```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ Accounts Needing Attention (4)                            │
├───────────┬──────────┬────────────┬───────────┬─────────────┤
│ Location  │ Account  │ Issue      │ Age       │ Action      │
├───────────┼──────────┼────────────┼───────────┼─────────────┤
│ Downtown  │ x9012    │ Unreconcile│ 12 days   │ [Reconcile] │
│ Harbor    │ x5678    │ Feed Down  │ 4 days    │ [Reconnect] │
└───────────┴──────────┴────────────┴───────────┴─────────────┘

┌────────────────────┬────────────────────┬─────────────────────┐
│ Auto-Match Rate    │ Manual Adjustments │ Bank Feed Health    │
│    85.2%           │   7 this week      │ ✓ 12 connected      │
│    ↑ vs last week  │   $2,450 total     │ ⚠ 1 needs attention │
│ [View Details]     │ [Review List]      │ [Check Feeds]       │
└────────────────────┴────────────────────┴─────────────────────┘
```

---

## 5. Multi-Account / Multi-Location Management

### Purpose
Show how cash and accounts are distributed; manage intercompany flows.

### Components

#### A. Cash Concentration Overview
- **Total System Cash**: All accounts combined
- **Cash by Entity**: Corporate, Location 1, Location 2, etc.
- **Visualization**: Treemap or stacked bar chart

#### B. Intercompany Transfers Summary
- **Pending Transfers**: Count and amount
- **Completed Today**: Count and amount
- **Failed/Rejected**: Count with reason
- **Data Source**: `intercompany_transfers` table

#### C. Account Ownership Mapping
- **Table**:
  - Bank Account
  - Owning Entity
  - GL Account Mapping
  - Purpose (Operating, Payroll, Reserve)
  - Authority Level (Who can access)

#### D. Access Permissions Matrix
- **Users**: Who has access to which accounts
- **Roles**: View only, Reconcile, Approve, Admin
- **Audit**: Last accessed by user

### Visual Layout
```
┌──────────────────────────────────────────────────────────────┐
│ Cash Distribution                                             │
│                                                               │
│  ┌────────────┐ ┌─────┐ ┌─────┐ ┌───────┐                   │
│  │ Corporate  │ │ Loc1 │ │ Loc2 │ │ Loc3  │                   │
│  │  $500K     │ │$125K │ │$89K  │ │$67K   │                   │
│  └────────────┘ └─────┘ └─────┘ └───────┘                   │
│   65%           16%      12%      9%                          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Intercompany Transfers                                        │
│ • Pending: 2 transfers ($15,000)                             │
│ • Completed Today: 5 transfers ($87,500)                     │
│ • Failed: None                                   [View All] │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Alerts & Automation Flags

### Purpose
Highlight critical issues requiring immediate attention.

### Alert Types

| Alert | Trigger | Severity | Action |
|-------|---------|----------|--------|
| Unreconciled > 30 days | Age check | 🔴 High | Email + Dashboard |
| Bank feed disconnected | Connection status | 🟠 Medium | Dashboard + Daily digest |
| Large variance | Abs(Bank - GL) > $5K | 🔴 High | Email + SMS |
| Unusual transaction | Amount > 3σ from mean | 🟡 Low | Dashboard flag |
| Successful auto-match | Confidence > 90% | 🟢 Info | Log only |
| Low cash balance | Balance < $10K | 🔴 High | Email CFO |
| Duplicate transaction | Same amount/vendor/date | 🟠 Medium | Dashboard review |

### Automation Flags

1. **Auto-Reconciled** ✓
   - Displayed on transactions matched automatically
   - Shows confidence score
   - User can review/override

2. **Needs Review** ⚠
   - Flagged by rules engine
   - Requires manual inspection
   - Assigned to user queue

3. **Pattern Detected** 🔁
   - Recurring transaction identified
   - Suggests GL account
   - Can create standing rule

### Visual Layout
```
┌──────────────────────────────────────────────────────────────┐
│ 🔴 Critical Alerts (2)                                        │
├──────────────────────────────────────────────────────────────┤
│ • Low Cash: Harbor location below $10K threshold             │
│   Action: [Review] [Dismiss] [Transfer Funds]               │
│                                                               │
│ • Large Variance: Downtown GL/Bank diff $6,240               │
│   Action: [Investigate] [Dismiss] [Create Adjustment]       │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ 🟡 Notifications (5)                                          │
│ • 3 transactions auto-matched (96% confidence)               │
│ • 2 unusual amounts detected                                 │
│ [View All]                                        [Mark Read] │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Historical & Predictive Insights

### Purpose
Show trends and forecasts for proactive cash management.

### Visualizations

#### A. 90-Day Cash Balance Trend
- **Line chart**: Daily ending balance per location
- **Overlay**: Moving average (7-day, 30-day)
- **Annotations**: Major events (payroll, tax payments)

#### B. Reconciliation Accuracy Over Time
- **Metric**: % reconciled within 3 days
- **Trend**: Last 12 weeks
- **Target line**: 95%

#### C. Expected vs Actual Deposit Timing
- **Purpose**: Detect delays in deposit processing
- **Metric**: Variance in days between sale date and deposit
- **Alert**: Variance > 2 days

#### D. Forecasted Cash Position
- **Model**: Linear regression on 90-day history
- **Projection**: Next 30 days
- **Confidence interval**: 80% band
- **Factors**: Seasonality, recurring payments, planned expenses

#### E. Aging of Unreconciled Items
- **Buckets**: 0-7 days, 8-14 days, 15-30 days, 30+ days
- **Stacked bar chart** by time bucket
- **Trend**: Decreasing = healthy

### Visual Layout
```
┌──────────────────────────────────────────────────────────────┐
│ Cash Balance Trend - Last 90 Days                            │
│  $                                                            │
│  │                              ╱───────                      │
│  │                    ╱────────╱                              │
│  │          ╱────────╱                                        │
│  │    ╱────╱                                                  │
│  └────────────────────────────────────────────> Days         │
│  Jan        Feb         Mar         Apr                      │
│                                                               │
│  Current: $781K | Peak: $850K (Mar 15) | Low: $620K (Feb 3) │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Forecasted Cash Position - Next 30 Days                      │
│  $                                                            │
│  │                                        ╱╱╱╱               │
│  │                              ────────╱╱╱╱╱                │
│  │                    ────────╱╱╱╱╱╱╱╱                       │
│  └────────────────────────────────────────> Days             │
│  Today   +7d    +14d    +21d    +30d                         │
│                                                               │
│  Projected: $820K ± $45K | Confidence: 78% | Model: Linear  │
│  📊 Based on 90-day history + recurring payment schedule     │
└──────────────────────────────────────────────────────────────┘
```

---

## Proposed UI Layout

### Desktop View (1920x1080)

```
┌─────────────────────────────────────────────────────────────────┐
│ [Nav] Banking Dashboard                     [Location ▼] [User] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌─────┬─────┬─────┬─────┐  ← Section 1: Summary KPIs (6 cards) │
│ │ $   │ Var │ %   │ Unr │                                       │
│ └─────┴─────┴─────┴─────┘                                       │
│ ┌─────┬─────┬─────────────┐                                     │
│ │ Out │Feed │ Last Recon  │                                     │
│ └─────┴─────┴─────────────┘                                     │
│                                                                  │
│ ┌─────────────────────────────────────┐ ┌──────────────────┐   │
│ │ Location Detail Grid (Table)        │ │ Alerts (2)       │   │← Section 2
│ │ [Sortable columns, search, export]  │ │ Critical items   │   │
│ └─────────────────────────────────────┘ └──────────────────┘   │
│                                                                  │
│ ┌──────────────────────────────┐ ┌────────────────────────────┐│
│ │ Cash Flow Chart (Line/Area)  │ │ Cash Distribution (Pie)    ││← Section 3
│ │ Inflows vs Outflows          │ │ By Location                ││
│ └──────────────────────────────┘ └────────────────────────────┘│
│                                                                  │
│ ┌──────────────┬──────────────┬──────────────┬──────────────┐  │
│ │ Top Inflows  │Top Outflows  │Recon Health  │Auto-Match %  │  │← Section 4
│ └──────────────┴──────────────┴──────────────┴──────────────┘  │
│                                                                  │
│ ┌──────────────────────────────────────────────────────────┐   │
│ │ 90-Day Cash Trend + 30-Day Forecast (Combined Chart)     │   │← Section 7
│ └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Responsive Behavior
- **Tablet (768px)**: Stack cards 2-column, collapse charts
- **Mobile (375px)**: Single column, summary cards only, "View Details" buttons

---

## Data Model

### Core Tables Required

#### 1. `bank_accounts`
```sql
id, area_id, account_number, account_name, bank_name, routing_number,
current_balance, gl_account_id, account_type, is_active,
feed_provider, feed_status, feed_last_sync, feed_error_message,
created_at, updated_at
```

#### 2. `bank_transactions`
```sql
id, bank_account_id, transaction_date, post_date, description, amount,
transaction_type, status (unreconciled|reconciled|void),
matched_journal_entry_id, matched_vendor_bill_id, matched_customer_invoice_id,
suggested_account_id, confidence_score, is_auto_matched, matched_at,
created_at, updated_at
```

#### 3. `bank_reconciliations`
```sql
id, bank_account_id, reconciliation_date, statement_date,
statement_ending_balance, gl_ending_balance, difference,
reconciled_by_user_id, status, notes,
created_at, updated_at
```

#### 4. `bank_reconciliation_items`
```sql
id, reconciliation_id, item_type (check|deposit_in_transit|adjustment),
description, amount, date, cleared,
created_at, updated_at
```

#### 5. `intercompany_transfers`
```sql
id, from_account_id, to_account_id, amount, transfer_date, status,
from_gl_account_id, to_gl_account_id, description,
created_by_user_id, approved_by_user_id,
created_at, updated_at
```

#### 6. `dashboard_alerts`
```sql
id, alert_type, severity, entity_type, entity_id, message, status,
triggered_at, acknowledged_at, acknowledged_by_user_id,
created_at, updated_at
```

#### 7. `bank_feed_logs`
```sql
id, bank_account_id, sync_started_at, sync_completed_at, status,
transactions_fetched, transactions_created, error_message,
created_at
```

### Derived/Computed Fields

#### Cash Flow Metrics (Aggregate Queries)
```sql
-- Daily inflows
SELECT DATE(transaction_date) as date, SUM(amount)
FROM bank_transactions
WHERE amount > 0 AND status != 'void'
GROUP BY DATE(transaction_date);

-- Daily outflows
SELECT DATE(transaction_date) as date, ABS(SUM(amount))
FROM bank_transactions
WHERE amount < 0 AND status != 'void'
GROUP BY DATE(transaction_date);

-- Reconciliation rate
SELECT
  COUNT(CASE WHEN status = 'reconciled' THEN 1 END) * 100.0 / COUNT(*) as recon_pct
FROM bank_transactions
WHERE transaction_date >= CURRENT_DATE - INTERVAL '30 days';
```

#### GL vs Bank Variance
```sql
SELECT
  ba.id, ba.account_name,
  ba.current_balance as bank_balance,
  COALESCE(gb.balance, 0) as gl_balance,
  ba.current_balance - COALESCE(gb.balance, 0) as variance
FROM bank_accounts ba
LEFT JOIN (
  SELECT account_id, SUM(debit_amount - credit_amount) as balance
  FROM gl_balances
  WHERE account_id IN (SELECT gl_account_id FROM bank_accounts)
  GROUP BY account_id
) gb ON ba.gl_account_id = gb.account_id;
```

---

## API Endpoints Needed

### Dashboard Data Endpoints

```python
# Summary KPIs
GET /api/banking-dashboard/summary
  → Returns: total_cash, variance, recon_rate, unreconciled_balance, outstanding_items, feed_status

# Location detail grid
GET /api/banking-dashboard/locations
  → Returns: Array of {location, account, bank_bal, gl_bal, variance, recon_pct, unmatched, last_recon, feed_status}

# Cash flow metrics
GET /api/banking-dashboard/cash-flow?period=30d
  → Returns: {daily_inflows: [], daily_outflows: [], top_inflows: [], top_outflows: [], burn_rate, runway}

# Reconciliation health
GET /api/banking-dashboard/recon-health
  → Returns: {accounts_needing_attention: [], auto_match_rate, manual_adjustments, feed_errors: []}

# Alerts
GET /api/banking-dashboard/alerts?severity=high
  → Returns: Array of {id, type, severity, message, entity, triggered_at}

# Historical trends
GET /api/banking-dashboard/trends?period=90d
  → Returns: {cash_trend: [], recon_accuracy: [], deposit_timing: []}

# Forecast
GET /api/banking-dashboard/forecast?days=30
  → Returns: {projected_balance: [], confidence_interval, model_type}
```

---

## Workflow Automations

### 1. Auto-Reconciliation Engine
**Trigger**: New bank transaction imported
**Actions**:
1. Check for exact amount + date match with GL entries
2. Apply vendor recognition
3. Check pattern matching rules
4. If confidence > 90%, auto-match and mark reconciled
5. If confidence 70-90%, suggest match (manual approval)
6. If confidence < 70%, flag for manual review

### 2. Bank Feed Monitor
**Schedule**: Every hour
**Actions**:
1. Check all accounts with `feed_status = 'connected'`
2. If `feed_last_sync > 24 hours`, trigger sync
3. If sync fails 3x, set `feed_status = 'error'` and create alert
4. Send daily digest of feed health

### 3. Reconciliation Reminder
**Schedule**: Daily at 9 AM
**Actions**:
1. Find accounts with `last_reconciliation_date > 7 days`
2. Calculate unreconciled transaction count
3. Send email to assigned accountant with summary
4. Create dashboard alert if > 30 days

### 4. Variance Alert
**Trigger**: Nightly batch job
**Actions**:
1. Calculate GL vs Bank variance for all accounts
2. If variance > $5,000, create high-priority alert
3. If variance > $1,000, create medium-priority alert
4. Send email to controller if critical threshold breached

### 5. Cash Forecast Update
**Schedule**: Daily at midnight
**Actions**:
1. Fetch last 90 days of transaction data
2. Run linear regression model
3. Calculate 30-day forecast with confidence intervals
4. Store results in cache table for fast dashboard loading
5. If projected balance < $10K within forecast period, create alert

### 6. Duplicate Detection
**Trigger**: New transaction created
**Actions**:
1. Check for existing transactions with same:
   - Amount (exact)
   - Vendor/description (fuzzy match > 85%)
   - Date (within ±2 days)
2. If match found, flag as potential duplicate
3. Add to review queue

### 7. Pattern Learning
**Trigger**: User manually matches transaction
**Actions**:
1. Extract pattern (vendor, amount range, GL account)
2. Store in `gl_learning` tables
3. Increment confidence score for this pattern
4. Apply pattern to future similar transactions

---

## Implementation Priority

### Phase 1: Foundation (Week 1-2)
- ✅ Basic dashboard layout
- ✅ Summary KPIs section
- ✅ Location detail grid
- Database schema updates
- Core API endpoints

### Phase 2: Analytics (Week 3-4)
- Cash flow metrics
- Reconciliation health monitoring
- Historical trend charts
- Basic alerts system

### Phase 3: Intelligence (Week 5-6)
- Auto-reconciliation engine
- Pattern learning
- Forecasting model
- Advanced alerts

### Phase 4: Automation (Week 7-8)
- Bank feed integration
- Scheduled jobs
- Email notifications
- Workflow automations

---

## Success Metrics

1. **Reconciliation Time**: Reduce from 4 hours/week to 1 hour/week per location
2. **Auto-Match Rate**: Achieve 85%+ automated matching
3. **Variance Detection**: Identify GL/Bank mismatches within 24 hours
4. **Cash Visibility**: Real-time cash position accuracy within $100
5. **User Adoption**: 100% of accounting staff using dashboard daily

---

## Technical Stack

- **Frontend**: Existing HTML/JS with Chart.js, DataTables.js for grids
- **Backend**: FastAPI (existing)
- **Database**: PostgreSQL (existing)
- **Caching**: Redis for forecast/aggregated data
- **Scheduling**: APScheduler for background jobs
- **Notifications**: SendGrid for email, Twilio for SMS (optional)

---

## Security Considerations

1. **Role-Based Access**: Controllers see all locations, managers see own location only
2. **Audit Logging**: All reconciliations, adjustments logged with user ID
3. **Bank Feed Security**: Encrypted credentials, OAuth tokens refreshed automatically
4. **Data Masking**: Partial account numbers in non-admin views
5. **Approval Workflows**: Large adjustments require dual approval

---

*End of Specification*
