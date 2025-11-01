#!/bin/bash

# Disk Space Monitoring Script
# Monitors disk usage and sends alerts when thresholds are exceeded

ALERT_LOG="/opt/restaurant-system/logs/alerts.log"
THRESHOLD_WARNING=80
THRESHOLD_CRITICAL=90

# Create log directory
mkdir -p "/opt/restaurant-system/logs"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

log_alert() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$ALERT_LOG"
}

# Check disk usage
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

log_alert "========================================="
log_alert "Disk Space Check"
log_alert "========================================="
log_alert "Current disk usage: ${DISK_USAGE}%"

if [ "$DISK_USAGE" -ge "$THRESHOLD_CRITICAL" ]; then
    echo -e "${RED}CRITICAL: Disk usage is at ${DISK_USAGE}%${NC}"
    log_alert "CRITICAL: Disk usage at ${DISK_USAGE}% (threshold: ${THRESHOLD_CRITICAL}%)"

    # Show largest directories
    log_alert "Largest directories:"
    du -sh /opt/* 2>/dev/null | sort -hr | head -5 | while read line; do
        log_alert "  $line"
    done

    # TODO: Send email alert
    # echo "CRITICAL: Disk usage at ${DISK_USAGE}%" | mail -s "Restaurant System - Disk Space Critical" admin@swhgrp.com

    exit 2

elif [ "$DISK_USAGE" -ge "$THRESHOLD_WARNING" ]; then
    echo -e "${YELLOW}WARNING: Disk usage is at ${DISK_USAGE}%${NC}"
    log_alert "WARNING: Disk usage at ${DISK_USAGE}% (threshold: ${THRESHOLD_WARNING}%)"

    # Show largest directories
    log_alert "Largest directories:"
    du -sh /opt/* 2>/dev/null | sort -hr | head -5 | while read line; do
        log_alert "  $line"
    done

    exit 1

else
    echo -e "${GREEN}OK: Disk usage is at ${DISK_USAGE}%${NC}"
    log_alert "OK: Disk usage at ${DISK_USAGE}%"
    exit 0
fi
