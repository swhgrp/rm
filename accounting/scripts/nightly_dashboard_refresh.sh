#!/bin/bash
#
# Nightly Dashboard Data Refresh
#
# This script runs the dashboard data population for yesterday's data
# Schedule with cron: 0 1 * * * /opt/restaurant-system/accounting/scripts/nightly_dashboard_refresh.sh
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="/opt/restaurant-system/logs"
LOG_FILE="$LOG_DIR/dashboard-refresh-$(date +%Y%m%d).log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

echo "========================================" | tee -a "$LOG_FILE"
echo "Dashboard Refresh Started: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Run inside Docker container
docker exec accounting-app python3 /app/scripts/populate_dashboard_data.py \
    --months 1 \
    --skip-summaries \
    --skip-expenses \
    2>&1 | tee -a "$LOG_FILE"

RESULT=$?

echo "========================================" | tee -a "$LOG_FILE"
echo "Dashboard Refresh Completed: $(date)" | tee -a "$LOG_FILE"
echo "Exit Code: $RESULT" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

exit $RESULT
