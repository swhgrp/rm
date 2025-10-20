# Integration Hub - Deployment & Testing Guide

**Version:** 1.2.0
**Last Updated:** 2025-10-19

---

## Overview

This guide covers deploying the Integration Hub and testing the end-to-end invoice processing workflow.

---

## Prerequisites

- Docker and Docker Compose installed
- All three systems running: Inventory, Accounting, Integration Hub
- At least one location in inventory system
- At least one fiscal period open in accounting system
- Chart of accounts configured with inventory asset accounts (1400-1499)

---

## Deployment Steps

### 1. Build and Start Services

```bash
cd /opt/restaurant-system

# Build the integration hub image
docker-compose build integration-hub

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

Expected output:
```
NAME                STATUS              PORTS
integration-hub     Up                  -
hub-db             Up                  5432/tcp
inventory-app      Up                  -
accounting-app     Up                  -
nginx-proxy        Up                  80->80/tcp, 443->443/tcp
```

### 2. Run Database Migrations

```bash
# Run Integration Hub migrations
docker-compose exec integration-hub alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Seed category mappings
```

### 3. Verify Services are Running

```bash
# Check Integration Hub
curl http://localhost:8000/health
# Expected: {"status": "healthy", "service": "integration-hub", "version": "1.0.0"}

# Check Inventory API
curl http://inventory-app:8000/api/health
# Expected: {"status": "healthy"}

# Check Accounting API
curl http://accounting-app:8000/api/health
# Expected: {"status": "healthy"}
```

### 4. Access Integration Hub UI

Open browser:
- **Production:** `https://rm.swhgrp.com/hub/`
- **Local:** `http://localhost/hub/`

You should see the Integration Hub dashboard with:
- Total Invoices: 0
- Pending Mapping: 0
- Ready to Send: 0
- Sent: 0

---

## Initial Configuration

### 1. Verify Category Mappings

Navigate to: **Category Mappings** page

You should see 18 pre-configured categories:

| Category | Display Name | Asset Account | COGS Account | Waste Account |
|----------|--------------|---------------|--------------|---------------|
| produce | Produce | 1405 | 5105 | 7180 |
| dairy | Dairy | 1410 | 5110 | 7180 |
| poultry | Poultry | 1418 | 5118 | 7180 |
| beef | Beef | 1417 | 5117 | 7180 |
| seafood | Seafood | 1420 | 5120 | 7180 |
| pork | Pork | 1422 | 5122 | 7180 |
| lamb | Lamb | 1425 | 5125 | 7180 |
| dry_goods | Dry Goods | 1430 | 5130 | 7180 |
| frozen | Frozen Foods | 1435 | 5135 | 7180 |
| paper_goods | Paper Goods | 1440 | 5140 | - |
| cleaning_supplies | Cleaning Supplies | 1445 | 5145 | - |
| beverage_na | Non-Alcoholic Beverages | 1447 | 5147 | 7181 |
| beer_draft | Beer - Draft | 1450 | 5150 | 7182 |
| beer_bottled | Beer - Bottled/Canned | 1452 | 5152 | 7182 |
| wine | Wine | 1455 | 5155 | 7182 |
| liquor | Liquor/Spirits | 1460 | 5160 | 7182 |
| supplies | Supplies | 1465 | 5165 | - |
| merchandise | Merchandise | 1470 | 5170 | 7183 |

### 2. Create Test Vendor (Optional)

If testing with real data, you can create a vendor in the inventory system first, or let the hub auto-create it.

---

## End-to-End Testing

### Test Case 1: Simple Invoice (2 Items)

#### Step 1: Upload Invoice

1. Go to Integration Hub dashboard
2. Click **"Upload Invoice"** button
3. Fill in the form:
   - **Vendor Name:** US Foods
   - **Invoice Number:** TEST-001
   - **Invoice Date:** Today's date
   - **Total Amount:** 137.50
   - **Invoice PDF:** Upload any PDF file (dummy file is fine for testing)
4. Click **"Upload"**

**Expected Result:**
- Redirect to invoice detail page
- Status: "Pending" or "Mapping"
- Invoice header shows all details
- No line items yet (you'll add them manually for this test)

#### Step 2: Add Line Items Manually

Since we're testing, we need to manually add items to the hub_invoice_items table:

```sql
-- Connect to hub database
docker-compose exec hub-db psql -U hub_user -d integration_hub_db

-- Add test items
INSERT INTO hub_invoice_items
  (invoice_id, line_number, item_description, quantity, unit_of_measure, unit_price, line_total)
VALUES
  (1, 1, 'Chicken Breast - Fresh', 25.0, 'LB', 3.50, 87.50),
  (1, 2, 'Ground Beef - 80/20', 10.0, 'LB', 5.00, 50.00);
```

#### Step 3: Map Items

1. Go to **"Unmapped Items"** page
2. For each item, click **"Map"**
3. For "Chicken Breast":
   - **Category:** poultry
   - **Asset Account:** 1418
   - **COGS Account:** 5118
   - **Waste Account:** 7180
   - Click **"Save Mapping"**
4. For "Ground Beef":
   - **Category:** beef
   - **Asset Account:** 1417
   - **COGS Account:** 5117
   - **Waste Account:** 7180
   - Click **"Save Mapping"**

**Expected Result:**
- After mapping the last item, you should see: "Invoice is now ready to send"
- Invoice status changes to "Ready"
- Auto-send should trigger automatically in the background

#### Step 4: Verify Auto-Send

1. Go back to the invoice detail page
2. Check the **Sync Status** panel

**Expected Result:**
- **Inventory System:** ✅ Sent (ID: should show inventory invoice ID)
- **Accounting System:** ✅ Sent (JE ID: should show journal entry number like JE-000001)
- Status should be "Sent"

#### Step 5: Verify in Inventory System

```bash
# Check inventory database
docker-compose exec inventory-db psql -U inventory_user -d inventory_db

-- Check invoice was created
SELECT id, vendor_id, invoice_number, total, status
FROM invoices
WHERE invoice_number = 'TEST-001';

-- Check invoice items
SELECT description, quantity, unit_price, line_total
FROM invoice_items
WHERE invoice_id = (SELECT id FROM invoices WHERE invoice_number = 'TEST-001');
```

**Expected Result:**
```
 id | vendor_id | invoice_number | total  |  status
----+-----------+----------------+--------+----------
  X |     Y     |   TEST-001     | 137.50 | APPROVED
```

#### Step 6: Verify in Accounting System

```bash
# Check accounting database
docker-compose exec accounting-db psql -U accounting_user -d accounting_db

-- Check journal entry was created
SELECT id, entry_number, entry_date, description, status
FROM journal_entries
WHERE reference_type = 'hub_invoice' AND reference_id = 1;

-- Check journal entry lines
SELECT
  account_id,
  debit_amount,
  credit_amount,
  description
FROM journal_entry_lines
WHERE journal_entry_id = (
  SELECT id FROM journal_entries WHERE reference_type = 'hub_invoice' AND reference_id = 1
);
```

**Expected Result:**
```
Journal Entry:
 id | entry_number | entry_date | description                       | status
----+--------------+------------+-----------------------------------+--------
  X | JE-000001    | 2025-10-19 | Invoice TEST-001 from US Foods   | POSTED

Lines:
 account_id | debit_amount | credit_amount | description
------------+--------------+---------------+---------------------------
       1418 |        87.50 |          0.00 | Chicken Breast - Fresh
       1417 |        50.00 |          0.00 | Ground Beef - 80/20
       2010 |         0.00 |        137.50 | AP - US Foods
```

**Validation:**
- ✅ Total debits (137.50) = Total credits (137.50)
- ✅ Asset accounts (1418, 1417) are debited
- ✅ AP account (2010) is credited
- ✅ Entry is POSTED

---

### Test Case 2: Partial Failure & Retry

#### Simulate Failure

To test retry logic, we can temporarily stop one service:

```bash
# Stop accounting service
docker-compose stop accounting-app

# Try to send an invoice
# Expected: Invoice status = "partial", inventory_sent = TRUE, accounting_sent = FALSE
```

#### Test Retry

```bash
# Restart accounting service
docker-compose start accounting-app

# In Hub UI, go to invoice detail page
# Click "Retry Accounting Only"

# Expected: accounting_sent changes to TRUE, status changes to "sent"
```

---

### Test Case 3: New Vendor Auto-Creation

#### Test Steps

1. Upload invoice with vendor name: "New Vendor Test Inc"
2. Map items and send
3. Check inventory database:

```sql
SELECT id, name FROM vendors WHERE name = 'New Vendor Test Inc';
```

**Expected Result:**
- Vendor is automatically created
- Invoice is linked to the new vendor

---

### Test Case 4: Weighted Average Cost Calculation

#### Setup

1. Create a master item in inventory with:
   - Current quantity: 10 LB
   - Current cost: $3.00/LB
   - Current value: $30.00

2. Upload invoice with:
   - Same item: 20 LB @ $4.00/LB = $80.00

#### Expected Calculation

```
Current value: 10 LB × $3.00 = $30.00
New value:     20 LB × $4.00 = $80.00
Total value:                  $110.00
Total quantity: 10 + 20 = 30 LB

New weighted average cost: $110.00 ÷ 30 LB = $3.67/LB
```

#### Verification

```sql
SELECT
  name,
  current_quantity,
  current_cost
FROM master_items
WHERE id = [item_id];
```

**Expected Result:**
```
 name            | current_quantity | current_cost
-----------------+------------------+--------------
 [Item Name]     |            30.00 |         3.67
```

---

## Troubleshooting

### Issue: Auto-send not triggering

**Symptoms:**
- Invoice status is "ready" but not sending
- Sync status shows "Not Sent" for both systems

**Solutions:**
1. Check logs:
```bash
docker-compose logs integration-hub --tail=50
```

2. Manual send:
   - Go to invoice detail page
   - Click "Send to Both Systems" button

3. Check API connectivity:
```bash
# From hub container
docker-compose exec integration-hub curl http://inventory-app:8000/api/health
docker-compose exec integration-hub curl http://accounting-app:8000/api/health
```

### Issue: "No open fiscal period found"

**Symptoms:**
- Accounting send fails with error about fiscal period

**Solution:**
- Create an open fiscal period in accounting system
- Period must include the invoice date

```sql
-- Check fiscal periods
SELECT * FROM fiscal_periods WHERE status = 'OPEN';

-- If none exist, create one (via accounting UI or SQL)
```

### Issue: "Account ID not found"

**Symptoms:**
- Accounting send fails with "Account ID XXXX not found"

**Solution:**
- Verify GL accounts exist in accounting system
- Update category mappings with correct account IDs

```sql
-- Check accounts
SELECT id, account_number, account_name FROM accounts
WHERE account_number IN (1418, 1417, 2010);
```

### Issue: Invoice status stuck in "mapping"

**Symptoms:**
- All items appear mapped but status doesn't change to "ready"

**Solution:**
- Check database for unmapped items:
```sql
SELECT * FROM hub_invoice_items
WHERE invoice_id = [id] AND is_mapped = FALSE;
```

- Manually update if needed:
```sql
UPDATE hub_invoices SET status = 'ready' WHERE id = [id];
```

---

## Monitoring & Logs

### View Logs

```bash
# Integration Hub logs
docker-compose logs integration-hub -f

# Inventory logs
docker-compose logs inventory-app -f

# Accounting logs
docker-compose logs accounting-app -f
```

### Key Log Messages to Watch For

**Success:**
```
INFO: Sending invoice INV-12345 to inventory system
INFO: Successfully sent invoice INV-12345 to inventory. ID: 123
INFO: Sending journal entry for invoice INV-12345 to accounting system
INFO: Successfully sent JE for invoice INV-12345 to accounting. JE ID: 45
```

**Errors:**
```
ERROR: HTTP error sending to inventory: 500 - Internal Server Error
ERROR: Request error sending to accounting: Connection refused
ERROR: Unexpected error: ...
```

### Database Monitoring

```sql
-- Hub: Check invoice status distribution
SELECT status, COUNT(*)
FROM hub_invoices
GROUP BY status;

-- Hub: Check recent errors
SELECT
  id,
  invoice_number,
  inventory_error,
  accounting_error
FROM hub_invoices
WHERE status = 'error'
ORDER BY created_at DESC
LIMIT 10;

-- Hub: Check sync success rate
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN sent_to_inventory THEN 1 ELSE 0 END) as inv_sent,
  SUM(CASE WHEN sent_to_accounting THEN 1 ELSE 0 END) as acct_sent,
  SUM(CASE WHEN sent_to_inventory AND sent_to_accounting THEN 1 ELSE 0 END) as both_sent
FROM hub_invoices;
```

---

## Performance Considerations

### Parallel Processing

The hub sends to both systems in parallel. Expected timing:
- Sequential (old way): 2-4 seconds total
- Parallel (hub way): 1-2 seconds total (50% faster)

### Database Connections

The hub maintains persistent HTTP connections to both systems using connection pooling.

### Retry Logic

- Automatic: Triggers when last item is mapped
- Manual: User can retry via UI
- System: No automatic retry loop (prevents hammering failed services)

---

## Security Considerations

### System User

Currently using user ID = 1 as system user. For production:

1. Create dedicated system user in both systems:
```sql
-- Inventory
INSERT INTO users (username, email, role, is_active)
VALUES ('system_hub', 'noreply+hub@swhgrp.com', 'admin', true);

-- Accounting
INSERT INTO users (username, email, role_id, is_active)
VALUES ('system_hub', 'noreply+hub@swhgrp.com', 1, true);
```

2. Update endpoints to use this user ID

### API Authentication

Currently the `/from-hub` endpoints have no authentication. For production:

1. Add API key authentication
2. Configure hub with API keys
3. Validate keys in endpoints

---

## Backup & Recovery

### Backup Hub Database

```bash
# Backup hub database
docker-compose exec hub-db pg_dump -U hub_user integration_hub_db > hub_backup.sql

# Restore
docker-compose exec -T hub-db psql -U hub_user integration_hub_db < hub_backup.sql
```

### Resync After Failure

If invoices are stuck in "partial" or "error" status:

1. Identify failed invoices:
```sql
SELECT id, invoice_number, status, inventory_error, accounting_error
FROM hub_invoices
WHERE status IN ('partial', 'error')
ORDER BY created_at DESC;
```

2. Fix underlying issues (service down, fiscal period closed, etc.)

3. Retry via UI or API:
```bash
curl -X POST http://localhost:8000/api/invoices/{id}/retry?system=both
```

---

## Production Checklist

Before going live:

- [ ] All services running and healthy
- [ ] Database migrations complete
- [ ] Category mappings configured and verified
- [ ] Test invoice processed successfully end-to-end
- [ ] Weighted average cost calculation verified
- [ ] Journal entry balances verified
- [ ] Error handling tested (partial failures, retries)
- [ ] Logs monitoring configured
- [ ] Backup strategy in place
- [ ] System user created (not using ID 1)
- [ ] API authentication added (if required)
- [ ] Documentation reviewed with team
- [ ] Training completed for users

---

## Support

For issues or questions:
- Check logs first (most issues are connectivity or configuration)
- Review this guide's Troubleshooting section
- Check [INTEGRATION_HUB_STATUS.md](../status/INTEGRATION_HUB_STATUS.md) for known limitations
- Verify all prerequisites are met

---

**Last Updated:** 2025-10-19
**Maintainer:** Claude
**Version:** 1.2.0
