#!/bin/bash
# Automated DSS Review & Post
# Runs nightly to review verified POS sales entries and auto-post clean ones
#
# Cron: 0 5 * * * /opt/restaurant-system/accounting/scripts/run_dss_review.sh

LOG_DIR="/opt/restaurant-system/logs"
LOG_FILE="$LOG_DIR/dss-review.log"
mkdir -p "$LOG_DIR"

echo "========================================" >> "$LOG_FILE"
echo "DSS Review started: $(date)" >> "$LOG_FILE"

cd /opt/restaurant-system

docker compose exec -T accounting-app python scripts/dss_review_and_post.py >> "$LOG_FILE" 2>&1

echo "DSS Review finished: $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
