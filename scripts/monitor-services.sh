#!/bin/bash

# Service Health Monitoring Script
# Checks all microservices and database health

ALERT_LOG="/opt/restaurant-system/logs/alerts.log"
SERVICES_DOWN=0

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

log_alert() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$ALERT_LOG"
}

log_alert "========================================="
log_alert "Service Health Check"
log_alert "========================================="

# Define services to check
SERVICES=(
    "https://rm.swhgrp.com/portal/health|Portal"
    "https://rm.swhgrp.com/inventory/health|Inventory"
    "https://rm.swhgrp.com/hr/health|HR"
    "https://rm.swhgrp.com/accounting/health|Accounting"
    "https://rm.swhgrp.com/events/health|Events"
    "https://rm.swhgrp.com/hub/health|Integration_Hub"
    "https://rm.swhgrp.com/files/health|Files"
    "https://rm.swhgrp.com/maintenance/health|Maintenance"
)

# Check each service
for service in "${SERVICES[@]}"; do
    IFS='|' read -r url name <<< "$service"

    # Try to reach the health endpoint (5 second timeout)
    if curl -s -f -m 5 "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name - OK${NC}"
        log_alert "OK: $name is healthy"
    else
        echo -e "${RED}✗ $name - DOWN${NC}"
        log_alert "CRITICAL: $name is DOWN or unhealthy"
        SERVICES_DOWN=$((SERVICES_DOWN + 1))
    fi
done

# Check Docker containers
log_alert "-----------------------------------"
log_alert "Docker Container Status:"

CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E "(portal|inventory|hr|accounting|events|hub|files|maintenance)")

for container in $CONTAINERS; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null | tr -d '\n' | xargs || echo "running")

    # If status is empty or contains only whitespace, set to "running"
    if [ -z "$STATUS" ] || [ "$STATUS" = "<no value>" ]; then
        STATUS="running"
    fi

    if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "running" ]; then
        echo -e "${GREEN}✓ $container - $STATUS${NC}"
        log_alert "OK: $container is $STATUS"
    else
        echo -e "${RED}✗ $container - $STATUS${NC}"
        log_alert "WARNING: $container is $STATUS"
    fi
done

# Check databases
log_alert "-----------------------------------"
log_alert "Database Status:"

DBS=("inventory-db" "accounting-db" "hr-db" "events-db" "hub-db" "maintenance-postgres")

for db in "${DBS[@]}"; do
    if docker exec $db pg_isready -q 2>/dev/null; then
        echo -e "${GREEN}✓ $db - accepting connections${NC}"
        log_alert "OK: $db is accepting connections"
    else
        echo -e "${RED}✗ $db - not responding${NC}"
        log_alert "CRITICAL: $db is not responding"
        SERVICES_DOWN=$((SERVICES_DOWN + 1))
    fi
done

log_alert "========================================="

if [ $SERVICES_DOWN -eq 0 ]; then
    echo -e "${GREEN}All services are healthy${NC}"
    log_alert "Summary: All services healthy"
    exit 0
else
    echo -e "${RED}${SERVICES_DOWN} service(s) are down or unhealthy${NC}"
    log_alert "Summary: ${SERVICES_DOWN} service(s) down or unhealthy"

    # TODO: Send email alert
    # echo "${SERVICES_DOWN} services are down" | \
    #   mail -s "Restaurant System - Service Alert" admin@swhgrp.com

    exit 2
fi
