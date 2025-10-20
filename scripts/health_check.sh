#!/bin/bash
#
# System Health Check Script
# Monitors Docker services, disk space, database connections, and application health
# Sends alerts when issues are detected
#

# Configuration
COMPOSE_FILE="/opt/restaurant-system/docker-compose.yml"
LOG_FILE="/opt/restaurant-system/logs/health_check.log"
ALERT_LOG="/opt/restaurant-system/logs/alerts.log"
DISK_THRESHOLD=85
MEMORY_THRESHOLD=90

# Email configuration
ALERT_EMAIL="admin@swhgrp.com"
SMTP_HOST="smtp.swhgrp.com"
SMTP_PORT="2555"
SMTP_USER="admin"
SMTP_FROM="admin@swhgrp.com"
SYSTEM_NAME="SW Restaurant Management System"

# Create log directory if it doesn't exist
mkdir -p "/opt/restaurant-system/logs"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to send email alert
send_email_alert() {
    local subject="$1"
    local body="$2"

    # Create email body with HTML formatting
    local email_body="Subject: ${subject}
From: ${SMTP_FROM}
To: ${ALERT_EMAIL}
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8

<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .alert { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }
        .critical { background-color: #f8d7da; border-left: 4px solid #dc3545; }
        .info { background-color: #d1ecf1; border-left: 4px solid #0dcaf0; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
    </style>
</head>
<body>
    <h2>🚨 ${SYSTEM_NAME} Alert</h2>
    <div class='alert critical'>
        <strong>Alert Time:</strong> $(date '+%Y-%m-%d %H:%M:%S')<br>
        <strong>Server:</strong> $(hostname)<br>
    </div>
    <pre>${body}</pre>
    <hr>
    <p style='font-size: 12px; color: #666;'>This is an automated alert from ${SYSTEM_NAME}</p>
</body>
</html>"

    # Send email using Python (available in Docker environment)
    docker exec inventory-app python3 -c "
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

msg = MIMEMultipart('alternative')
msg['Subject'] = '''${subject}'''
msg['From'] = '''${SMTP_FROM}'''
msg['To'] = '''${ALERT_EMAIL}'''

html = '''${email_body}'''
msg.attach(MIMEText(html, 'html'))

try:
    server = smtplib.SMTP('''${SMTP_HOST}''', ${SMTP_PORT})
    server.login('''${SMTP_USER}''', '''Galveston34-''')
    server.send_message(msg)
    server.quit()
    print('Email sent successfully')
except Exception as e:
    print(f'Failed to send email: {e}')
" 2>&1 | tee -a "$LOG_FILE"
}

# Function to log alerts
log_alert() {
    local alert_message="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: $alert_message" | tee -a "$ALERT_LOG"
    log_message "ALERT: $alert_message"

    # Email notifications disabled - alerts only logged to file
    # if [ -n "$ALERT_EMAIL" ]; then
    #     send_email_alert "⚠️ System Alert: ${SYSTEM_NAME}" "$alert_message"
    # fi
}

# Check if running as root/sudo
if [ "$EUID" -ne 0 ] && ! groups | grep -q docker; then
    log_alert "Script must be run as root or docker group member"
    exit 1
fi

log_message "=== Starting health check ==="

# Track overall health status
HEALTH_OK=true

# 1. Check Docker service status
log_message "Checking Docker service status..."
if ! systemctl is-active --quiet docker; then
    log_alert "Docker service is not running!"
    HEALTH_OK=false
else
    log_message "✓ Docker service is running"
fi

# 2. Check all required containers
log_message "Checking Docker containers..."
REQUIRED_CONTAINERS=("inventory-app" "inventory-db" "accounting-app" "accounting-db" "inventory-redis" "nginx")
CONTAINER_ISSUES=0

for container in "${REQUIRED_CONTAINERS[@]}"; do
    # Get container status using docker compose ps with filters
    STATUS=$(docker compose -f "$COMPOSE_FILE" ps "$container" --format "{{.State}}" 2>/dev/null)

    if [ "$STATUS" != "running" ]; then
        log_alert "Container $container is not running (Status: $STATUS)"
        CONTAINER_ISSUES=$((CONTAINER_ISSUES + 1))
        HEALTH_OK=false
    else
        log_message "✓ Container $container is running"
    fi
done

if [ $CONTAINER_ISSUES -eq 0 ]; then
    log_message "✓ All containers are running"
fi

# 3. Check disk space
log_message "Checking disk space..."
DISK_USAGE=$(df /opt/restaurant-system | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ]; then
    log_alert "Disk usage is at ${DISK_USAGE}% (threshold: ${DISK_THRESHOLD}%)"
    HEALTH_OK=false
else
    log_message "✓ Disk usage is at ${DISK_USAGE}% (healthy)"
fi

# Show backup directory size
BACKUP_SIZE=$(du -sh /opt/restaurant-system/backups 2>/dev/null | cut -f1)
if [ -n "$BACKUP_SIZE" ]; then
    log_message "  Backup directory size: $BACKUP_SIZE"
fi

# 4. Check memory usage
log_message "Checking memory usage..."
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')

if [ "$MEMORY_USAGE" -gt "$MEMORY_THRESHOLD" ]; then
    log_alert "Memory usage is at ${MEMORY_USAGE}% (threshold: ${MEMORY_THRESHOLD}%)"
    HEALTH_OK=false
else
    log_message "✓ Memory usage is at ${MEMORY_USAGE}% (healthy)"
fi

# 5. Check database connectivity
log_message "Checking database connectivity..."

# Check inventory database
if docker compose -f "$COMPOSE_FILE" exec -T inventory-db \
    psql -U inventory_user -d inventory_db -c "SELECT 1;" >/dev/null 2>&1; then
    log_message "✓ Inventory database connection OK"
else
    log_alert "Cannot connect to inventory database!"
    HEALTH_OK=false
fi

# Check accounting database
if docker compose -f "$COMPOSE_FILE" exec -T accounting-db \
    psql -U accounting_user -d accounting_db -c "SELECT 1;" >/dev/null 2>&1; then
    log_message "✓ Accounting database connection OK"
else
    log_alert "Cannot connect to accounting database!"
    HEALTH_OK=false
fi

# 6. Check Redis connectivity
log_message "Checking Redis connectivity..."
if docker compose -f "$COMPOSE_FILE" exec -T inventory-redis redis-cli ping >/dev/null 2>&1; then
    log_message "✓ Redis connection OK"
else
    log_alert "Cannot connect to Redis!"
    HEALTH_OK=false
fi

# 7. Check application endpoints
log_message "Checking application endpoints..."

# Check inventory app through Nginx (redirects to login if not authenticated)
INVENTORY_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/ 2>/dev/null || echo "000")
if [ "$INVENTORY_RESPONSE" = "200" ] || [ "$INVENTORY_RESPONSE" = "302" ] || [ "$INVENTORY_RESPONSE" = "301" ]; then
    log_message "✓ Inventory app is responding through Nginx (HTTP $INVENTORY_RESPONSE)"
else
    log_alert "Inventory app is not responding properly (HTTP $INVENTORY_RESPONSE)"
    HEALTH_OK=false
fi

# Check accounting app through Nginx
ACCOUNTING_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/accounting/health 2>/dev/null || echo "000")
if [ "$ACCOUNTING_RESPONSE" = "200" ] || [ "$ACCOUNTING_RESPONSE" = "404" ]; then
    log_message "✓ Accounting app is responding through Nginx (HTTP $ACCOUNTING_RESPONSE)"
else
    log_message "⚠ Accounting app endpoint check returned HTTP $ACCOUNTING_RESPONSE (may be expected)"
fi

# Check Nginx is serving static files
NGINX_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/css/style.css 2>/dev/null || echo "000")
if [ "$NGINX_RESPONSE" = "200" ] || [ "$NGINX_RESPONSE" = "304" ]; then
    log_message "✓ Nginx is serving static files (HTTP $NGINX_RESPONSE)"
else
    log_message "⚠ Nginx static file check returned HTTP $NGINX_RESPONSE"
fi

# 8. Check for recent application errors (last 5 minutes)
log_message "Checking for recent application errors..."
ERROR_COUNT=0

# Check inventory app logs
INVENTORY_ERRORS=$(docker compose -f "$COMPOSE_FILE" logs --since 5m inventory-app 2>/dev/null | grep -i "error\|exception\|critical" | wc -l)
if [ "$INVENTORY_ERRORS" -gt 0 ]; then
    log_message "⚠ Found $INVENTORY_ERRORS error(s) in inventory app logs (last 5 minutes)"
    ERROR_COUNT=$((ERROR_COUNT + INVENTORY_ERRORS))
fi

# Check accounting app logs
ACCOUNTING_ERRORS=$(docker compose -f "$COMPOSE_FILE" logs --since 5m accounting-app 2>/dev/null | grep -i "error\|exception\|critical" | wc -l)
if [ "$ACCOUNTING_ERRORS" -gt 0 ]; then
    log_message "⚠ Found $ACCOUNTING_ERRORS error(s) in accounting app logs (last 5 minutes)"
    ERROR_COUNT=$((ERROR_COUNT + ACCOUNTING_ERRORS))
fi

if [ $ERROR_COUNT -eq 0 ]; then
    log_message "✓ No recent errors found in application logs"
elif [ $ERROR_COUNT -gt 10 ]; then
    log_alert "High error rate detected: $ERROR_COUNT errors in the last 5 minutes"
    HEALTH_OK=false
fi

# 9. Check database sizes
log_message "Checking database sizes..."

INVENTORY_DB_SIZE=$(docker compose -f "$COMPOSE_FILE" exec -T inventory-db \
    psql -U inventory_user -d inventory_db -t -c "SELECT pg_size_pretty(pg_database_size('inventory_db'));" 2>/dev/null | xargs)
if [ -n "$INVENTORY_DB_SIZE" ]; then
    log_message "  Inventory database size: $INVENTORY_DB_SIZE"
fi

ACCOUNTING_DB_SIZE=$(docker compose -f "$COMPOSE_FILE" exec -T accounting-db \
    psql -U accounting_user -d accounting_db -t -c "SELECT pg_size_pretty(pg_database_size('accounting_db'));" 2>/dev/null | xargs)
if [ -n "$ACCOUNTING_DB_SIZE" ]; then
    log_message "  Accounting database size: $ACCOUNTING_DB_SIZE"
fi

# 10. Summary
log_message "=== Health check completed ==="

if [ "$HEALTH_OK" = true ]; then
    log_message "✓ System is healthy - all checks passed"
    exit 0
else
    log_alert "System health check failed - see logs for details"
    exit 1
fi
