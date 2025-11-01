#!/bin/bash
#
# AR Automation Runner
#
# Runs AR automation (recurring invoices + payment reminders) inside Docker container
# Add to crontab: 0 2 * * * /opt/restaurant-system/accounting/scripts/run_ar_automation.sh
#

# Ensure log directory exists
mkdir -p /var/log/accounting

# Run the automation script inside the Docker container
docker exec accounting-app python3 /app/scripts/ar_automation.py >> /var/log/accounting/ar_automation_cron.log 2>&1

# Log completion
echo "AR Automation completed at $(date)" >> /var/log/accounting/ar_automation_cron.log
