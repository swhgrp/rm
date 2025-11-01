#!/bin/bash

# SSL Certificate Expiration Monitoring
# Checks SSL certificate expiration and alerts if expiring soon

DOMAIN="rm.swhgrp.com"
ALERT_LOG="/opt/restaurant-system/logs/alerts.log"
WARNING_DAYS=30
CRITICAL_DAYS=7

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

log_alert() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$ALERT_LOG"
}

log_alert "========================================="
log_alert "SSL Certificate Check - $DOMAIN"
log_alert "========================================="

# Get certificate expiration date
EXPIRY_DATE=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | \
    openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)

if [ -z "$EXPIRY_DATE" ]; then
    echo -e "${RED}ERROR: Could not retrieve SSL certificate${NC}"
    log_alert "ERROR: Could not retrieve SSL certificate for $DOMAIN"
    exit 2
fi

# Convert to epoch time
EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
CURRENT_EPOCH=$(date +%s)
DAYS_REMAINING=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))

log_alert "Certificate expires: $EXPIRY_DATE"
log_alert "Days remaining: $DAYS_REMAINING"

if [ "$DAYS_REMAINING" -le "$CRITICAL_DAYS" ]; then
    echo -e "${RED}CRITICAL: SSL certificate expires in ${DAYS_REMAINING} days${NC}"
    log_alert "CRITICAL: SSL certificate expires in ${DAYS_REMAINING} days"

    # TODO: Send email alert
    # echo "CRITICAL: SSL cert for $DOMAIN expires in $DAYS_REMAINING days" | \
    #   mail -s "Restaurant System - SSL Certificate Expiring" admin@swhgrp.com

    exit 2

elif [ "$DAYS_REMAINING" -le "$WARNING_DAYS" ]; then
    echo -e "${YELLOW}WARNING: SSL certificate expires in ${DAYS_REMAINING} days${NC}"
    log_alert "WARNING: SSL certificate expires in ${DAYS_REMAINING} days"
    exit 1

else
    echo -e "${GREEN}OK: SSL certificate valid for ${DAYS_REMAINING} days${NC}"
    log_alert "OK: SSL certificate valid for ${DAYS_REMAINING} days"
    exit 0
fi
