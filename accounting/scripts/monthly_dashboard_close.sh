#!/bin/bash
#
# Monthly Dashboard Data Aggregation
#
# This script runs monthly aggregation on the 1st of each month
# Schedule with cron: 0 2 1 * * /opt/restaurant-system/accounting/scripts/monthly_dashboard_close.sh
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="/opt/restaurant-system/logs"
LOG_FILE="$LOG_DIR/dashboard-monthly-$(date +%Y%m%d).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Dashboard Aggregation Started: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Run inside Docker container - process last month only
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py \
    --months 2 \
    --skip-snapshots \
    2>&1 | tee -a "$LOG_FILE"

RESULT=$?

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Dashboard Aggregation Completed: $(date)" | tee -a "$LOG_FILE"
echo "Exit Code: $RESULT" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

exit $RESULT
