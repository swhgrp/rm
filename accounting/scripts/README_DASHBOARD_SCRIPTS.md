# Dashboard Data Population Scripts

This directory contains scripts for populating and maintaining the General Accounting Dashboard data.

## Scripts

### 1. `populate_dashboard_data.py`

**Purpose:** Backfills dashboard tables with historical data from General Ledger entries.

**Tables Populated:**
- `daily_financial_snapshots` - Daily aggregated financial metrics
- `monthly_performance_summaries` - Closed month performance tracking
- `expense_category_summaries` - Top expense categories by month
- `dashboard_alerts` - System-generated alerts

**Usage:**

```bash
# Backfill last 12 months for all locations
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py

# Backfill last 6 months
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 6

# Backfill for specific location only
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --area-id 1

# Skip certain tables
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --skip-snapshots
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --skip-summaries
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --skip-expenses
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --skip-alerts
```

**Options:**
- `--months <N>` - Number of months to backfill (default: 12)
- `--area-id <ID>` - Process specific area only (default: all areas)
- `--skip-snapshots` - Skip daily financial snapshots
- `--skip-summaries` - Skip monthly performance summaries
- `--skip-expenses` - Skip expense category summaries
- `--skip-alerts` - Skip alert generation

**What It Does:**

1. **Daily Snapshots:**
   - Aggregates journal entries by day and location
   - Calculates sales, COGS, expenses, net income
   - Calculates COGS%, Labor%, Gross Margin%
   - Stores transaction counts and average check
   - Records cash, AP, and AR balances

2. **Monthly Summaries:**
   - Aggregates daily snapshots into monthly totals
   - Calculates prime cost (COGS% + Labor%)
   - Compares to prior month (variance %)
   - Marks closed vs open periods

3. **Expense Summaries:**
   - Categorizes expenses (Labor, Rent, Utilities, etc.)
   - Ranks top 5 expenses by amount
   - Calculates % of revenue
   - Tracks month-to-date and YTD totals

4. **Alert Generation:**
   - Checks for unposted journal entries
   - Checks for overdue bank reconciliations
   - Checks for high COGS% (>35%)
   - Checks for high aged payables (90+ days)
   - Checks for negative cash balances

**Performance:**
- Processes ~1,000 days in ~5-10 minutes
- Uses batch inserts and commits
- Skips existing records (idempotent)

---

### 2. `nightly_dashboard_refresh.sh`

**Purpose:** Runs nightly to populate yesterday's dashboard data.

**Schedule:** Daily at 1:00 AM

```bash
# Add to crontab
0 1 * * * /opt/restaurant-system/accounting/scripts/nightly_dashboard_refresh.sh
```

**What It Does:**
- Runs populate script for last 1 month (updates recent data)
- Skips monthly summaries and expenses (runs monthly instead)
- Logs output to `/opt/restaurant-system/logs/dashboard-refresh-YYYYMMDD.log`
- Exits with error code if script fails

**Manual Run:**
```bash
/opt/restaurant-system/accounting/scripts/nightly_dashboard_refresh.sh
```

---

### 3. `monthly_dashboard_close.sh`

**Purpose:** Runs monthly to aggregate closed month data.

**Schedule:** 1st of each month at 2:00 AM

```bash
# Add to crontab
0 2 1 * * /opt/restaurant-system/accounting/scripts/monthly_dashboard_close.sh
```

**What It Does:**
- Runs populate script for last 2 months
- Skips daily snapshots (already populated nightly)
- Creates monthly summaries and expense summaries
- Ranks expenses and calculates comparisons
- Logs output to `/opt/restaurant-system/logs/dashboard-monthly-YYYYMMDD.log`

**Manual Run:**
```bash
/opt/restaurant-system/accounting/scripts/monthly_dashboard_close.sh
```

---

## Initial Setup

### Step 1: Backfill Historical Data

Before using the dashboard, populate historical data:

```bash
# Backfill last 12 months
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 12

# Check progress
docker logs accounting-app --tail 50
```

**Expected Output:**
```
🚀 Starting dashboard data population for last 12 months...
📅 Date range: 2024-10-22 to 2025-10-22
📍 Processing 6 location(s)

📊 Populating daily financial snapshots...
  Progress: 25.0% (100 snapshots created)
  Progress: 50.0% (200 snapshots created)
  Progress: 75.0% (300 snapshots created)
✅ Created 365 daily snapshots

📈 Populating monthly performance summaries...
✅ Created 72 monthly summaries

💰 Populating expense category summaries...
✅ Created 540 expense summaries

⚠️  Generating dashboard alerts...
✅ Generated 12 alerts

✅ Dashboard data population complete!
```

**Estimated Time:**
- 6 locations × 365 days = ~10 minutes
- 6 locations × 12 months × 9 categories = ~2 minutes
- Total: ~15 minutes for 1 year of data

### Step 2: Set Up Cron Jobs

Add to system crontab:

```bash
# Edit crontab
sudo crontab -e

# Add these lines:
0 1 * * * /opt/restaurant-system/accounting/scripts/nightly_dashboard_refresh.sh
0 2 1 * * /opt/restaurant-system/accounting/scripts/monthly_dashboard_close.sh
```

**Verify Cron Jobs:**
```bash
sudo crontab -l
```

### Step 3: Verify Dashboard Data

Check if data was populated:

```bash
# Connect to database
docker exec accounting-db psql -U accounting_user -d accounting_db

# Check daily snapshots
SELECT COUNT(*), MIN(snapshot_date), MAX(snapshot_date)
FROM daily_financial_snapshots;

# Check monthly summaries
SELECT COUNT(*), MIN(period_month), MAX(period_month)
FROM monthly_performance_summaries;

# Check expense summaries
SELECT COUNT(*) FROM expense_category_summaries;

# Check alerts
SELECT COUNT(*), severity FROM dashboard_alerts
WHERE is_active = true
GROUP BY severity;
```

### Step 4: Test Dashboard

1. Navigate to: https://rm.swhgrp.com/accounting/
2. Dashboard should display with populated metrics
3. Select different locations from dropdown
4. Verify all widgets show data
5. Check trend chart displays 6-month history

---

## Troubleshooting

### Dashboard Shows Zeros

**Cause:** Data not yet populated

**Solution:**
```bash
# Run population script
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 12

# Check for errors
docker logs accounting-app --tail 100
```

### Script Fails with Database Error

**Cause:** Database connection or permission issue

**Solution:**
```bash
# Check database is running
docker ps | grep accounting-db

# Check database credentials in .env
docker exec accounting-app env | grep DATABASE

# Test database connection
docker exec accounting-app python3 -c "from accounting.core.config import settings; print(settings.DATABASE_URL)"
```

### Alerts Not Generating

**Cause:** Alert generation skipped or no conditions met

**Solution:**
```bash
# Run alert generation only
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py \
    --skip-snapshots --skip-summaries --skip-expenses

# Check alert conditions (requires actual issues to exist)
# - Unposted journal entries
# - Overdue reconciliations
# - High COGS%
# - Aged payables
# - Negative cash
```

### Cron Jobs Not Running

**Cause:** Cron not configured or script permissions

**Solution:**
```bash
# Check crontab
sudo crontab -l

# Check script permissions
ls -la /opt/restaurant-system/accounting/scripts/*.sh

# Make executable
chmod +x /opt/restaurant-system/accounting/scripts/*.sh

# Check cron logs
sudo tail -f /var/log/syslog | grep CRON
```

### Duplicate Data / Script Runs Twice

**Cause:** Script is idempotent but may update existing records

**Solution:**
```bash
# Clear dashboard tables and re-run
docker exec accounting-db psql -U accounting_user -d accounting_db <<EOF
TRUNCATE TABLE daily_financial_snapshots CASCADE;
TRUNCATE TABLE monthly_performance_summaries CASCADE;
TRUNCATE TABLE expense_category_summaries CASCADE;
UPDATE dashboard_alerts SET is_active = false WHERE is_resolved = false;
EOF

# Re-run population
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 12
```

---

## Performance Optimization

### Large Data Volumes (1000+ days)

If processing large date ranges:

1. **Run in batches:**
   ```bash
   # Process 3 months at a time
   docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 3
   docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 6
   docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 12
   ```

2. **Process locations separately:**
   ```bash
   for area_id in 1 2 3 4 5 6; do
       docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py \
           --months 12 --area-id $area_id
   done
   ```

3. **Run during off-hours:**
   - Schedule initial backfill at night
   - Use `nice` command to reduce CPU priority
   ```bash
   nice -n 10 docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py --months 12
   ```

### Database Indexing

Ensure indexes exist for fast queries:

```sql
-- Check existing indexes
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('daily_financial_snapshots', 'monthly_performance_summaries');

-- Add missing indexes if needed
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date_area
ON daily_financial_snapshots(snapshot_date, area_id);

CREATE INDEX IF NOT EXISTS idx_monthly_summaries_month_area
ON monthly_performance_summaries(period_month, area_id);
```

---

## Monitoring

### Check Script Execution

```bash
# View last run logs
tail -100 /opt/restaurant-system/logs/dashboard-refresh-$(date +%Y%m%d).log

# View monthly logs
tail -100 /opt/restaurant-system/logs/dashboard-monthly-$(date +%Y%m%d).log

# Monitor real-time
tail -f /opt/restaurant-system/logs/dashboard-refresh-$(date +%Y%m%d).log
```

### Database Table Sizes

```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename IN (
    'daily_financial_snapshots',
    'monthly_performance_summaries',
    'expense_category_summaries',
    'dashboard_alerts'
)
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Alert Summary

```sql
SELECT
    alert_type,
    severity,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE is_acknowledged = false) as unacknowledged,
    COUNT(*) FILTER (WHERE is_resolved = false) as unresolved
FROM dashboard_alerts
WHERE is_active = true
GROUP BY alert_type, severity
ORDER BY severity, count DESC;
```

---

## Maintenance

### Monthly Tasks

1. **Review Alerts:** Check for persistent alerts that need action
2. **Verify Data Accuracy:** Spot-check dashboard metrics vs manual calculations
3. **Check Logs:** Review cron job logs for errors
4. **Clean Old Logs:** Remove logs older than 30 days

```bash
# Clean old logs
find /opt/restaurant-system/logs -name "dashboard-*.log" -mtime +30 -delete
```

### Quarterly Tasks

1. **Performance Review:** Check script execution times
2. **Data Validation:** Compare dashboard totals to financial statements
3. **Archive Old Data:** Move snapshots older than 2 years to archive table

### Annual Tasks

1. **Recalculate Historical Data:** Re-run population for prior year to capture any GL adjustments
2. **Review Alert Thresholds:** Adjust COGS%, aging, and other alert thresholds
3. **Optimize Queries:** Review slow query logs and add indexes if needed

---

## Support

For issues or questions:
- Check logs in `/opt/restaurant-system/logs/`
- Review database table contents
- Check script output for error messages
- Consult [GENERAL_DASHBOARD_IMPLEMENTATION.md](../../docs/status/GENERAL_DASHBOARD_IMPLEMENTATION.md)
