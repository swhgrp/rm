#!/bin/bash

# Dashboard Status Generator
# Generates JSON status data for monitoring dashboard

# Force EST/EDT timezone for consistent timestamps
export TZ="America/New_York"

# Output JSON header
echo "Content-Type: application/json"
echo ""

# Start JSON
echo "{"
echo '  "timestamp": "'$(date "+%Y-%m-%d %H:%M:%S")'",'
echo '  "generated_at": "'$(date "+%Y-%m-%d %H:%M:%S %Z")'",'

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

# Nginx Status
echo '  "nginx": {'
if docker ps --format '{{.Names}}' | grep -q "^nginx-mailcow$"; then
    NGINX_STATUS="running"
    NGINX_UPTIME_SECS=$(docker inspect --format='{{.State.StartedAt}}' nginx-mailcow 2>/dev/null | xargs -I {} date -d {} +%s 2>/dev/null || echo 0)
    CURRENT_SECS=$(date +%s)
    NGINX_UPTIME_MINS=$(( ($CURRENT_SECS - $NGINX_UPTIME_SECS) / 60 ))

    # Check if nginx is responding
    if curl -sk https://rm.swhgrp.com > /dev/null 2>&1; then
        NGINX_HEALTH="healthy"
    else
        NGINX_HEALTH="unhealthy"
    fi
else
    NGINX_STATUS="stopped"
    NGINX_UPTIME_MINS=0
    NGINX_HEALTH="stopped"
fi

echo "    \"status\": \"$NGINX_STATUS\","
echo "    \"health\": \"$NGINX_HEALTH\","
echo "    \"uptime_minutes\": $NGINX_UPTIME_MINS"
echo '  },'

# Services
echo '  "services": {'

SERVICES=("portal-app" "inventory-app" "hr-app" "accounting-app" "events-app" "integration-hub" "files-app" "websites-app")
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

# Databases with connection counts
echo '  "databases": {'

DBS=("inventory-db" "accounting-db" "hr-db" "events-db" "hub-db" "websites-db")
DB_COUNT=0
TOTAL_DBS=${#DBS[@]}

for db in "${DBS[@]}"; do
    DB_COUNT=$((DB_COUNT + 1))

    if docker exec $db pg_isready -q 2>/dev/null; then
        STATUS="healthy"
        # Get database size and connection count
        case $db in
            "inventory-db")
                SIZE=$(docker exec $db psql -U inventory_user -d inventory_db -t -c "SELECT pg_size_pretty(pg_database_size('inventory_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U inventory_user -d inventory_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='inventory_db';" 2>/dev/null | xargs || echo 0)
                ;;
            "accounting-db")
                SIZE=$(docker exec $db psql -U accounting_user -d accounting_db -t -c "SELECT pg_size_pretty(pg_database_size('accounting_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U accounting_user -d accounting_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='accounting_db';" 2>/dev/null | xargs || echo 0)
                ;;
            "hr-db")
                SIZE=$(docker exec $db psql -U hr_user -d hr_db -t -c "SELECT pg_size_pretty(pg_database_size('hr_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U hr_user -d hr_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='hr_db';" 2>/dev/null | xargs || echo 0)
                ;;
            "events-db")
                SIZE=$(docker exec $db psql -U events_user -d events_db -t -c "SELECT pg_size_pretty(pg_database_size('events_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U events_user -d events_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='events_db';" 2>/dev/null | xargs || echo 0)
                ;;
            "hub-db")
                SIZE=$(docker exec $db psql -U hub_user -d integration_hub_db -t -c "SELECT pg_size_pretty(pg_database_size('integration_hub_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U hub_user -d integration_hub_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='integration_hub_db';" 2>/dev/null | xargs || echo 0)
                ;;
            "websites-db")
                SIZE=$(docker exec $db psql -U websites_user -d websites_db -t -c "SELECT pg_size_pretty(pg_database_size('websites_db'));" 2>/dev/null | xargs || echo "unknown")
                CONNECTIONS=$(docker exec $db psql -U websites_user -d websites_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='websites_db';" 2>/dev/null | xargs || echo 0)
                ;;
        esac
    else
        STATUS="down"
        SIZE="unknown"
        CONNECTIONS=0
    fi

    echo "    \"$db\": {"
    echo "      \"status\": \"$STATUS\","
    echo "      \"size\": \"$SIZE\","
    echo "      \"connections\": $CONNECTIONS"

    if [ $DB_COUNT -lt $TOTAL_DBS ]; then
        echo "    },"
    else
        echo "    }"
    fi
done

echo '  },'

# Backup Details (per database)
echo '  "backup_details": {'

BACKUP_DIR="/opt/restaurant-system/backups"
DB_NAMES=("inventory_db" "accounting_db" "hr_db" "events_db" "integration_hub_db" "websites_db")
DETAIL_COUNT=0
TOTAL_DETAILS=${#DB_NAMES[@]}

for dbname in "${DB_NAMES[@]}"; do
    DETAIL_COUNT=$((DETAIL_COUNT + 1))

    # Find most recent backup for this database
    LATEST=$(ls -t "$BACKUP_DIR/${dbname}_"*.sql.gz 2>/dev/null | head -1)

    if [ -n "$LATEST" ]; then
        # Get timestamp with timezone name (EST/EDT)
        BACKUP_DATE=$(TZ="America/New_York" date -r "$LATEST" "+%Y-%m-%d %H:%M:%S %Z")
        BACKUP_SIZE=$(du -h "$LATEST" 2>/dev/null | cut -f1)
        BACKUP_COUNT=$(ls -1 "$BACKUP_DIR/${dbname}_"*.sql.gz 2>/dev/null | wc -l)
        BACKUP_STATUS="ok"
    else
        BACKUP_DATE="never"
        BACKUP_SIZE="0"
        BACKUP_COUNT=0
        BACKUP_STATUS="missing"
    fi

    echo "    \"$dbname\": {"
    echo "      \"latest_backup\": \"$BACKUP_DATE\","
    echo "      \"backup_count\": $BACKUP_COUNT,"
    echo "      \"latest_size\": \"$BACKUP_SIZE\","
    echo "      \"status\": \"$BACKUP_STATUS\""

    if [ $DETAIL_COUNT -lt $TOTAL_DETAILS ]; then
        echo "    },"
    else
        echo "    }"
    fi
done

echo '  },'

# Overall Backups Summary
echo '  "backups": {'

LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)

if [ -n "$LATEST_BACKUP" ]; then
    # Get timestamp with timezone name (EST/EDT)
    BACKUP_DATE=$(TZ="America/New_York" date -r "$LATEST_BACKUP" "+%Y-%m-%d %H:%M:%S %Z")
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

# Network Status (check if containers can reach each other)
echo '  "network": {'

# Check if restaurant-network exists and has containers
NETWORK_EXISTS=$(docker network ls --format '{{.Name}}' | grep -c "^restaurant-network$")
if [ "$NETWORK_EXISTS" -eq 1 ]; then
    NETWORK_STATUS="connected"
    CONTAINER_COUNT=$(docker network inspect restaurant-network --format='{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null | wc -w)

    # Test network connectivity - can portal reach a database?
    if docker exec portal-app ping -c 1 -W 2 hr-db > /dev/null 2>&1; then
        NETWORK_HEALTH="healthy"
    else
        NETWORK_HEALTH="degraded"
    fi
else
    NETWORK_STATUS="missing"
    NETWORK_HEALTH="error"
    CONTAINER_COUNT=0
fi

echo "    \"status\": \"$NETWORK_STATUS\","
echo "    \"health\": \"$NETWORK_HEALTH\","
echo "    \"containers\": $CONTAINER_COUNT"
echo '  },'

# Recent Errors from Logs
echo '  "recent_errors": ['

LOG_DIR="/opt/restaurant-system/logs"
ERROR_COUNT=0

# Get last 10 errors from monitoring log (last hour)
if [ -f "$LOG_DIR/monitoring.log" ]; then
    ERRORS=$(grep -i "CRITICAL\|ERROR\|FAIL" "$LOG_DIR/monitoring.log" 2>/dev/null | tail -10)

    while IFS= read -r line; do
        if [ -n "$line" ]; then
            if [ $ERROR_COUNT -gt 0 ]; then
                echo ","
            fi
            # Escape quotes in the log line
            ESCAPED_LINE=$(echo "$line" | sed 's/"/\\"/g' | sed 's/$//')
            echo -n "    \"$ESCAPED_LINE\""
            ERROR_COUNT=$((ERROR_COUNT + 1))
        fi
    done <<< "$ERRORS"
fi

if [ $ERROR_COUNT -eq 0 ]; then
    echo -n "    \"No recent errors\""
fi

echo ""
echo '  ],'

# Recent Alerts
echo '  "recent_alerts": ['

ALERT_COUNT=0

# Get last 5 alerts from alerts log
if [ -f "$LOG_DIR/alerts.log" ]; then
    ALERTS=$(tail -5 "$LOG_DIR/alerts.log" 2>/dev/null)

    while IFS= read -r line; do
        if [ -n "$line" ]; then
            if [ $ALERT_COUNT -gt 0 ]; then
                echo ","
            fi
            # Escape quotes in the alert line
            ESCAPED_LINE=$(echo "$line" | sed 's/"/\\"/g' | sed 's/$//')
            echo -n "    \"$ESCAPED_LINE\""
            ALERT_COUNT=$((ALERT_COUNT + 1))
        fi
    done <<< "$ALERTS"
fi

if [ $ALERT_COUNT -eq 0 ]; then
    echo -n "    \"No recent alerts\""
fi

echo ""
echo '  ],'

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
