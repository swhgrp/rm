# AR Automation Scripts

This directory contains scripts for automating Accounts Receivable (AR) processes.

## Scripts

### ar_automation.py
Main automation script that processes:
- **Recurring Invoices**: Automatically generates invoices from active templates when they are due
- **Payment Reminders**: Sends automated reminder emails for overdue invoices based on configured schedule

### run_ar_automation.sh
Shell wrapper script that runs the automation inside the Docker container.

## Setup

### 1. Ensure log directory exists
```bash
sudo mkdir -p /var/log/accounting
sudo chown $(whoami):$(whoami) /var/log/accounting
```

### 2. Test the automation manually
```bash
/opt/restaurant-system/accounting/scripts/run_ar_automation.sh
```

Check the log:
```bash
tail -f /var/log/accounting/ar_automation_cron.log
```

### 3. Add to crontab
Run daily at 2:00 AM:
```bash
crontab -e
```

Add this line:
```
0 2 * * * /opt/restaurant-system/accounting/scripts/run_ar_automation.sh
```

Alternatively, for more frequent testing, run every hour:
```
0 * * * * /opt/restaurant-system/accounting/scripts/run_ar_automation.sh
```

### 4. Verify cron is running
```bash
# Check crontab
crontab -l

# Check cron service status
sudo systemctl status cron

# Monitor logs
tail -f /var/log/accounting/ar_automation_cron.log
tail -f /var/log/accounting/ar_automation.log
```

## Configuration

### Recurring Invoices
Configure via the UI at: `/accounting/recurring-invoices`

- Create templates for customers with recurring billing
- Set frequency (weekly, monthly, quarterly, etc.)
- Configure email settings per template
- Pause/resume/cancel templates as needed

### Payment Reminders
Configure via Settings page at: `/accounting/settings`

Under "Payment Reminder Settings":
- Enable/disable automated reminders
- Set reminder schedule (days after due date)
  - First reminder: typically 7 days
  - Second reminder: typically 14 days
  - Final reminder: typically 30 days
- Configure email settings
- Set minimum invoice amount threshold

## How It Works

### Recurring Invoices
1. Script runs daily (or on configured schedule)
2. Finds all ACTIVE recurring invoice templates where `next_invoice_date <= today`
3. For each template:
   - Creates a new CustomerInvoice with DRAFT or SENT status
   - Copies line items from template
   - Calculates totals (subtotal, discount, tax)
   - Updates template's `next_invoice_date` based on frequency
   - If `auto_send_email` is enabled, sends invoice email to customer
   - Increments `invoices_generated` counter
   - Marks template as COMPLETED if `end_date` is reached

### Payment Reminders
1. Script runs daily
2. Finds all overdue invoices (due_date < today) with status SENT, PARTIALLY_PAID, or OVERDUE
3. For each overdue invoice:
   - Calculates days overdue
   - Checks if reminder should be sent based on configured schedule
   - Verifies reminder hasn't been sent recently (within last 24 hours)
   - Checks if invoice amount is above minimum threshold
   - Sends reminder email with PDF attachment
   - Logs reminder in `payment_reminders` table
   - Updates invoice status to OVERDUE if not already

## Monitoring

### View automation logs
```bash
# Main automation log (detailed)
tail -f /var/log/accounting/ar_automation.log

# Cron wrapper log
tail -f /var/log/accounting/ar_automation_cron.log
```

### Check for errors
```bash
grep ERROR /var/log/accounting/ar_automation.log
```

### View reminder statistics
Check the database:
```sql
-- Recent reminders sent
SELECT * FROM payment_reminders ORDER BY sent_at DESC LIMIT 20;

-- Reminder statistics by day
SELECT DATE(sent_at) as date,
       reminder_number,
       COUNT(*) as count,
       SUM(amount_due) as total_amount
FROM payment_reminders
GROUP BY DATE(sent_at), reminder_number
ORDER BY date DESC;
```

### View recurring invoice history
```sql
-- Recently generated recurring invoices
SELECT ci.invoice_number, ci.invoice_date, ci.total_amount,
       ri.template_name, c.customer_name
FROM customer_invoices ci
JOIN recurring_invoices ri ON ci.recurring_invoice_id = ri.id
JOIN customers c ON ci.customer_id = c.id
WHERE ci.created_at >= NOW() - INTERVAL '7 days'
ORDER BY ci.created_at DESC;
```

## Troubleshooting

### Automation not running
1. Check crontab: `crontab -l`
2. Check cron service: `sudo systemctl status cron`
3. Check script permissions: `ls -l /opt/restaurant-system/accounting/scripts/run_ar_automation.sh`
4. Test manually: `/opt/restaurant-system/accounting/scripts/run_ar_automation.sh`

### No invoices being generated
1. Check recurring invoice templates are ACTIVE
2. Verify `next_invoice_date` is in the past
3. Check logs for errors
4. Run manually to see detailed output

### No reminders being sent
1. Check reminders are enabled in Settings
2. Verify email settings are configured (SMTP)
3. Check there are overdue invoices
4. Verify customers have email addresses
5. Check logs for email errors

### Email delivery issues
1. Test email connection in Settings page
2. Check SMTP credentials are correct
3. Verify firewall allows outbound SMTP connections
4. Check spam/junk folders
5. Review email logs: `grep email /var/log/accounting/ar_automation.log`

## Manual Execution

You can also trigger these processes manually via API:

### Process Recurring Invoices
```bash
# Via Python
docker exec accounting-app python3 /app/scripts/ar_automation.py

# Or call the service directly in code
from accounting.services.recurring_invoice_service import RecurringInvoiceService
service = RecurringInvoiceService(db)
invoices = service.process_due_invoices()
```

### Process Payment Reminders
```python
from accounting.services.payment_reminder_service import PaymentReminderService
service = PaymentReminderService(db)
stats = service.process_overdue_invoices()
```

## Best Practices

1. **Test First**: Always test automation manually before adding to cron
2. **Monitor Logs**: Regularly review logs for errors or issues
3. **Email Verification**: Ensure customers have valid email addresses
4. **Template Management**: Keep recurring invoice templates up to date
5. **Reminder Cadence**: Adjust reminder schedule based on your business needs
6. **Backup Data**: Regularly backup the database before making configuration changes
