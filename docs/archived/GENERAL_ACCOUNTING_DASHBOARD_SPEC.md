

# General Accounting Dashboard - Technical Specification

**Created:** 2025-10-22
**Status:** In Progress
**Completion:** Database Schema Complete (30%)

---

## Overview

The General Accounting Dashboard provides real-time financial oversight and accounting health monitoring for the SW Hospitality Group's restaurant operations. It complements the existing Banking Dashboard with comprehensive financial tracking, performance analysis, and multi-location management.

---

## Architecture

### Database Schema ✅ COMPLETE

**Tables Created:**
1. `daily_financial_snapshots` - Daily aggregated metrics
2. `monthly_performance_summaries` - Closed month performance
3. `dashboard_alerts` - System-generated alerts
4. `expense_category_summaries` - Top expense tracking

### Service Layer (In Progress)

**Services to Create:**
1. `DashboardMetricsService` - Calculate real-time metrics
2. `DashboardAlertService` - Generate and manage alerts
3. `PerformanceAnalysisService` - Historical trends and comparisons

### API Layer (Planned)

**Endpoints:**
- `GET /api/dashboard/summary` - Executive summary
- `GET /api/dashboard/metrics/mtd` - Month-to-date metrics
- `GET /api/dashboard/metrics/ytd` - Year-to-date metrics
- `GET /api/dashboard/alerts` - Active alerts
- `GET /api/dashboard/trends/{period}` - Historical trends
- `GET /api/dashboard/locations` - Multi-location comparison
- `POST /api/dashboard/alerts/{id}/acknowledge` - Acknowledge alert
- `POST /api/dashboard/alerts/{id}/resolve` - Resolve alert

---

## Data Sources

### 1. Daily Sales Summary (DSS)
- Real-time sales data from POS
- Food, beverage, alcohol breakouts
- Transaction counts
- GL account mapping

### 2. General Ledger
- Posted journal entries
- Account balances
- COGS, expenses, revenue
- Multi-location tagging

### 3. Banking Module
- Current bank balances
- Reconciliation status
- Pending transactions
- Cash flow data

### 4. Accounts Payable
- Open invoices
- Aging buckets (0-30, 31-60, 61-90, 90+)
- Vendor balances
- Payment status

### 5. Month-End Close Data
- Closed period summaries
- Labor % from payroll
- Prior period comparisons
- Budget vs actual

---

## Dashboard Widgets

### 1. Executive Financial Summary

**Metrics:**
- Net Income (MTD, YTD, vs Prior)
- Total Revenue (current month, % change)
- Gross Profit Margin
- Operating Margin
- Prime Cost %
- Top 5 Expense Categories

**Visualizations:**
- Revenue by location (bar chart)
- Net income trend (line chart)
- Expense breakdown (pie chart)

**Data Refresh:** Real-time (current day + last closed day)

### 2. Real-Time Financial Tracking

**Metrics:**
- Daily Sales Summary (today + MTD)
- COGS % (real-time calculation)
- Current Bank Balances (sum of all accounts)
- Cash Flow Forecast (bank + open AP)
- AP Aging Summary
- Unposted Journals Count
- Bank Reconciliation Status

**Visualizations:**
- Daily sales trend (sparkline)
- COGS % gauge
- AP aging stacked bar
- Cash runway indicator

**Data Refresh:** Hourly during business hours, daily otherwise

### 3. Month-End & Historical Analysis

**Metrics:**
- P&L Snapshot (last closed month)
- Labor % (from closeout)
- 6-Month Revenue Trend
- 6-Month COGS % Trend
- 6-Month Net Income Margin
- 6-Month Labor % Trend
- Variance vs Budget
- Variance vs Prior Year

**Visualizations:**
- Multi-line trend charts
- Variance waterfall
- Period comparison table

**Data Refresh:** Daily (uses closed period data)

### 4. Inventory & COGS Management

**Metrics:**
- Current Inventory Value (if available)
- COGS % by Category (Food, Beverage, Supplies)
- Theoretical vs Actual COGS
- Last Inventory Date
- Variance Warnings

**Visualizations:**
- COGS comparison bar chart
- Variance indicator

**Data Refresh:** Daily

### 5. Multi-Location Financial Overview

**Metrics (per location):**
- Revenue
- Gross Profit %
- Net Income
- COGS %
- Labor %
- Prime Cost %
- Ranking by metric

**Performance Flags:**
- 🔴 Sales down >10% vs last month
- 🟡 COGS > target by 2%
- 🟡 AP aging > 45 days average
- 🟢 All metrics within targets

**Visualizations:**
- Location comparison table
- Heat map
- Ranking list

**Data Refresh:** Daily

### 6. Accounting Health & Automation Alerts

**Alert Types:**

| Alert Type | Severity | Threshold | Action |
|-----------|----------|-----------|--------|
| Unposted Journal Entries | Warning | Count > 0 | Link to journal entry page |
| Pending Bank Reconciliations | Critical | Days > 3 | Link to reconciliation |
| Missing DSS GL Mappings | Warning | Count > 0 | Link to DSS mapping page |
| GL Balance Outlier | Warning | >2σ from average | Link to account detail |
| Sales Drop | Critical | >10% decrease | Review operations |
| COGS High | Warning | >2% above target | Review inventory |
| AP Aging High | Warning | Avg age > 45 days | Review payables |
| Missing Inventory | Info | Last count > 7 days | Schedule inventory |
| Negative Cash | Critical | Any account | Review cash management |
| Period Not Closed | Warning | 5+ days after month-end | Complete close |

**Visualizations:**
- Alert list with priority
- Alert count by severity
- Resolution time metrics

**Data Refresh:** Hourly

### 7. Reporting & Period Controls

**Features:**
- Month-end close progress checklist
- GL lock/unlock status
- Quick links to reports:
  - P&L by Location
  - Consolidated P&L
  - Balance Sheet
  - Cash Flow Statement
  - Trial Balance
- Export options (Excel, PDF)
- Period selection
- Date range filters

---

## Calculation Logic

### Net Income (MTD)
```
Revenue (current month DSS + GL revenue accounts)
- COGS (GL COGS accounts)
- Operating Expenses (GL expense accounts)
= Net Income
```

### COGS %
```
(Total COGS / Total Revenue) * 100
```

### Gross Profit Margin
```
((Revenue - COGS) / Revenue) * 100
```

### Operating Margin
```
((Revenue - COGS - Operating Expenses) / Revenue) * 100
```

### Prime Cost %
```
((COGS + Labor Expense) / Revenue) * 100
```

### Cash Flow Forecast
```
Current Bank Balances
- Open AP (unpaid invoices)
+ Open AR (unpaid customer invoices)
= Projected Cash
```

### AP Aging Buckets
```
0-30 days: invoice_date within last 30 days
31-60 days: invoice_date 31-60 days ago
61-90 days: invoice_date 61-90 days ago
90+ days: invoice_date > 90 days ago
```

---

## Alert Generation Logic

### Unposted Journals
```sql
SELECT COUNT(*)
FROM journal_entries
WHERE status = 'DRAFT'
AND created_at < CURRENT_DATE - INTERVAL '1 day'
```

### Pending Reconciliations
```sql
SELECT ba.id, ba.account_name,
       MAX(bt.transaction_date) as last_reconciled
FROM bank_accounts ba
LEFT JOIN bank_transactions bt ON bt.bank_account_id = ba.id
  AND bt.status = 'reconciled'
WHERE ba.is_active = TRUE
GROUP BY ba.id
HAVING MAX(bt.transaction_date) < CURRENT_DATE - INTERVAL '3 days'
OR MAX(bt.transaction_date) IS NULL
```

### Sales Drop
```sql
-- Compare current month to prior month
SELECT area_id,
       SUM(CASE WHEN snapshot_date >= DATE_TRUNC('month', CURRENT_DATE)
                THEN total_sales ELSE 0 END) as current_month_sales,
       SUM(CASE WHEN snapshot_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
                 AND snapshot_date < DATE_TRUNC('month', CURRENT_DATE)
                THEN total_sales ELSE 0 END) as prior_month_sales
FROM daily_financial_snapshots
GROUP BY area_id
HAVING (current_month_sales - prior_month_sales) / prior_month_sales < -0.10
```

### COGS High
```sql
-- Current month COGS % vs target (e.g., 32%)
SELECT area_id,
       AVG(cogs_percentage) as avg_cogs_pct
FROM daily_financial_snapshots
WHERE snapshot_date >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY area_id
HAVING AVG(cogs_percentage) > 32 + 2  -- Target + 2%
```

---

## Multi-Location Logic

### Consolidated View
```sql
-- Sum all locations
SELECT SUM(total_sales) as total_sales,
       SUM(total_cogs) as total_cogs,
       SUM(total_expenses) as total_expenses
FROM daily_financial_snapshots
WHERE snapshot_date = CURRENT_DATE
```

### Individual Location View
```sql
-- Filter by area_id
SELECT *
FROM daily_financial_snapshots
WHERE snapshot_date = CURRENT_DATE
AND area_id = :area_id
```

### Location Ranking
```sql
-- Rank by revenue
SELECT area_id,
       SUM(total_sales) as total_sales,
       RANK() OVER (ORDER BY SUM(total_sales) DESC) as rank
FROM daily_financial_snapshots
WHERE snapshot_date >= DATE_TRUNC('month', CURRENT_DATE)
GROUP BY area_id
```

---

## Data Refresh Schedule

| Data Type | Refresh Frequency | Method |
|-----------|------------------|---------|
| Daily Sales | Real-time | On DSS import |
| Bank Balances | Hourly | API sync or manual |
| GL Balances | On journal post | Event-driven |
| AP Aging | Daily at midnight | Cron job |
| Alerts | Hourly | Cron job |
| Monthly Summaries | On month close | Manual trigger |
| Expense Categories | Daily at midnight | Cron job |

---

## UI/UX Design

### Layout
- Full-width dashboard (no sidebar initially visible)
- Card-based widgets (Bootstrap cards)
- Collapsible sections
- Responsive grid (3 columns on desktop, 1 on mobile)
- Dark theme matching existing UI

### Color Scheme
- Positive metrics: Green (#2ea043)
- Negative metrics: Red (#f85149)
- Neutral: Blue (#58a6ff)
- Warning: Yellow (#d29922)
- Background: Dark (#0d1117)

### Interactive Elements
- Hover tooltips for metrics
- Clickable cards navigate to detail pages
- Expandable alert details
- Location filter dropdown
- Date range picker
- Export buttons

---

## Performance Considerations

### Caching Strategy
- Cache dashboard metrics for 5 minutes
- Cache historical trends for 1 hour
- Cache closed period data indefinitely
- Invalidate on data updates

### Database Optimization
- Indexes on snapshot_date, area_id, period_month
- Materialized views for complex aggregations
- Denormalized summaries for faster reads
- Partition daily snapshots by month

### Query Optimization
- Use aggregate functions at database level
- Limit data range (last 6 months for trends)
- Use EXPLAIN ANALYZE for slow queries
- Consider Redis for real-time metrics

---

## Security & Access Control

### Permissions
- **Accounting Staff**: Full access to all locations
- **Location Managers**: Access to their location only
- **Executives**: Consolidated view + all locations
- **Read-Only Users**: View only, no exports

### Data Filtering
- Automatically filter by user's assigned locations
- Admin users bypass location filters
- Audit log for data exports

---

## Testing Plan

### Unit Tests
- Service layer calculations
- Alert generation logic
- Data aggregation functions

### Integration Tests
- API endpoints
- Database queries
- Data refresh jobs

### UI Tests
- Widget rendering
- Interactive elements
- Responsive design
- Data visualization accuracy

### Performance Tests
- Load time < 2 seconds
- Query execution < 500ms
- Concurrent users: 50+

---

## Implementation Status

### ✅ Completed
1. Database schema design
2. Alembic migration
3. SQLAlchemy models
4. Model enums and relationships

### 🔄 In Progress
1. Pydantic schemas
2. Dashboard service layer
3. API endpoints

### ⏳ Pending
1. Dashboard HTML template
2. JavaScript widgets
3. Data visualization charts
4. Alert management UI
5. Automated refresh jobs
6. Testing
7. Documentation

---

## Next Steps

1. **Create Pydantic Schemas** - Request/response models for API
2. **Implement Service Layer** - Business logic for calculations and alerts
3. **Build API Endpoints** - RESTful APIs for dashboard data
4. **Create Dashboard UI** - HTML template with widgets
5. **Add Navigation** - Make dashboard the default landing page
6. **Implement Cron Jobs** - Automated data refresh
7. **Test with Sample Data** - Verify calculations and UI
8. **Update Documentation** - User guide and API docs

---

**Estimated Completion Time:** 6-8 hours total
**Current Progress:** 30% (2 hours invested)
**Remaining Work:** 4-6 hours

