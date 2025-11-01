#!/bin/bash

# Dashboard Status Generator
# Generates JSON status data for monitoring dashboard

# Output JSON header
echo "Content-Type: application/json"
echo ""

# Start JSON
echo "{"
echo '  "timestamp": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",'
echo '  "generated_at": "'$(date "+%Y-%m-%d %H:%M:%S")'",'

# System Info
echo '  "system": {'
UPTIME=$(uptime -p)
LOAD=$(uptime | awk -F'load average:' '{print $2}' | xargs)
echo "    \"uptime\": \"$UPTIME\","
echo "    \"load_average\": \"$LOAD\","

# Disk space
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
echo "    \"disk_usage_percent\": $DISK_USAGE,"
echo "    \"disk_free\": \"$DISK_FREE\","

# Memory
MEM_TOTAL=$(free -h | awk 'NR==2 {print $2}')
MEM_USED=$(free -h | awk 'NR==2 {print $3}')
MEM_FREE=$(free -h | awk 'NR==2 {print $4}')
echo "    \"memory_total\": \"$MEM_TOTAL\","
echo "    \"memory_used\": \"$MEM_USED\","
echo "    \"memory_free\": \"$MEM_FREE\""
echo '  },'

# Services
echo '  "services": {'

SERVICES=("portal-app" "inventory-app" "hr-app" "accounting-app" "events-app" "integration-hub" "files-app")
SERVICE_COUNT=0
TOTAL_SERVICES=${#SERVICES[@]}

for service in "${SERVICES[@]}"; do
    SERVICE_COUNT=$((SERVICE_COUNT + 1))

    if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
        STATUS="running"
        UPTIME_SECS=$(docker inspect --format='{{.State.StartedAt}}' $service 2>/dev/null | xargs -I {} date -d {} +%s 2>/dev/null || echo 0)
        CURRENT_SECS=$(date +%s)
        UPTIME_MINS=$(( ($CURRENT_SECS - $UPTIME_SECS) / 60 ))

        # Get health status if available
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' $service 2>/dev/null || echo "no_healthcheck" | tr -d '\n')
        HEALTH=$(echo "$HEALTH" | tr -d '\n' | xargs)
        if [ "$HEALTH" = "no_healthcheck" ] || [ -z "$HEALTH" ]; then
            HEALTH="running"
        fi
    else
        STATUS="stopped"
        UPTIME_MINS=0
        HEALTH="stopped"
    fi

    echo "    \"$service\": {"
    echo "      \"status\": \"$STATUS\","
    echo "      \"health\": \"$HEALTH\","
    echo "      \"uptime_minutes\": $UPTIME_MINS"

    if [ $SERVICE_COUNT -lt $TOTAL_SERVICES ]; then
        echo "    },"
    else
        echo "    }"
    fi
done

echo '  },'

# Databases
echo '  "databases": {'

DBS=("inventory-db" "accounting-db" "hr-db" "events-db" "hub-db")
DB_COUNT=0
TOTAL_DBS=${#DBS[@]}

for db in "${DBS[@]}"; do
    DB_COUNT=$((DB_COUNT + 1))

    if docker exec $db pg_isready -q 2>/dev/null; then
        STATUS="healthy"
        # Get database size
        case $db in
            "inventory-db")
                SIZE=$(docker exec $db psql -U inventory_user -d inventory_db -t -c "SELECT pg_size_pretty(pg_database_size('inventory_db'));" 2>/dev/null | xargs || echo "unknown")
                ;;
            "accounting-db")
                SIZE=$(docker exec $db psql -U accounting_user -d accounting_db -t -c "SELECT pg_size_pretty(pg_database_size('accounting_db'));" 2>/dev/null | xargs || echo "unknown")
                ;;
            "hr-db")
                SIZE=$(docker exec $db psql -U hr_user -d hr_db -t -c "SELECT pg_size_pretty(pg_database_size('hr_db'));" 2>/dev/null | xargs || echo "unknown")
                ;;
            "events-db")
                SIZE=$(docker exec $db psql -U events_user -d events_db -t -c "SELECT pg_size_pretty(pg_database_size('events_db'));" 2>/dev/null | xargs || echo "unknown")
                ;;
            "hub-db")
                SIZE=$(docker exec $db psql -U hub_user -d integration_hub_db -t -c "SELECT pg_size_pretty(pg_database_size('integration_hub_db'));" 2>/dev/null | xargs || echo "unknown")
                ;;
        esac
    else
        STATUS="down"
        SIZE="unknown"
    fi

    echo "    \"$db\": {"
    echo "      \"status\": \"$STATUS\","
    echo "      \"size\": \"$SIZE\""

    if [ $DB_COUNT -lt $TOTAL_DBS ]; then
        echo "    },"
    else
        echo "    }"
    fi
done

echo '  },'

# Backups
echo '  "backups": {'

BACKUP_DIR="/opt/restaurant-system/backups"
LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)

if [ -n "$LATEST_BACKUP" ]; then
    BACKUP_DATE=$(stat -c %y "$LATEST_BACKUP" | cut -d' ' -f1,2 | cut -d'.' -f1)
    BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l)
    BACKUP_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

    echo "    \"latest_backup\": \"$BACKUP_DATE\","
    echo "    \"total_backups\": $BACKUP_COUNT,"
    echo "    \"total_size\": \"$BACKUP_SIZE\","
    echo "    \"status\": \"ok\""
else
    echo "    \"latest_backup\": \"never\","
    echo "    \"total_backups\": 0,"
    echo "    \"total_size\": \"0\","
    echo "    \"status\": \"warning\""
fi

echo '  },'

# SSL Certificate
echo '  "ssl": {'

DOMAIN="rm.swhgrp.com"
EXPIRY_DATE=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | \
    openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)

if [ -n "$EXPIRY_DATE" ]; then
    EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
    CURRENT_EPOCH=$(date +%s)
    DAYS_REMAINING=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))

    if [ $DAYS_REMAINING -le 7 ]; then
        SSL_STATUS="critical"
    elif [ $DAYS_REMAINING -le 30 ]; then
        SSL_STATUS="warning"
    else
        SSL_STATUS="ok"
    fi

    echo "    \"expiry_date\": \"$EXPIRY_DATE\","
    echo "    \"days_remaining\": $DAYS_REMAINING,"
    echo "    \"status\": \"$SSL_STATUS\""
else
    echo "    \"expiry_date\": \"unknown\","
    echo "    \"days_remaining\": 0,"
    echo "    \"status\": \"error\""
fi

echo '  }'

# End JSON
echo "}"
