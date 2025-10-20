#!/bin/bash
#
# Check POS Auto-Sync Status
# Displays current status of POS sync for all locations
# Sends email alert if sync issues are detected
#

COMPOSE_FILE="/opt/restaurant-system/docker-compose.yml"
LOG_FILE="/opt/restaurant-system/logs/pos_sync_check.log"

# Email configuration
ALERT_EMAIL="admin@swhgrp.com"
SMTP_HOST="smtp.swhgrp.com"
SMTP_PORT="2555"
SMTP_USER="admin"
SMTP_FROM="admin@swhgrp.com"
SYSTEM_NAME="SW Restaurant Management System"

# Create log directory if it doesn't exist
mkdir -p "/opt/restaurant-system/logs"

# Function to send email alert
send_email_alert() {
    local subject="$1"
    local body="$2"

    docker exec inventory-app python3 -c "
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

msg = MIMEMultipart('alternative')
msg['Subject'] = '''${subject}'''
msg['From'] = '''${SMTP_FROM}'''
msg['To'] = '''${ALERT_EMAIL}'''

html = '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .alert { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
    </style>
</head>
<body>
    <h2>⚠️ POS Sync Alert</h2>
    <div class='alert'>
        <strong>Alert Time:</strong> $(date '+%Y-%m-%d %H:%M:%S')<br>
        <strong>Server:</strong> $(hostname)<br>
    </div>
    <pre>${body}</pre>
    <hr>
    <p style='font-size: 12px; color: #666;'>This is an automated alert from ${SYSTEM_NAME}</p>
</body>
</html>
'''
msg.attach(MIMEText(html, 'html'))

try:
    server = smtplib.SMTP('''${SMTP_HOST}''', ${SMTP_PORT})
    server.login('''${SMTP_USER}''', '''Galveston34-''')
    server.send_message(msg)
    server.quit()
except Exception as e:
    print(f'Failed to send email: {e}')
" 2>&1 >> "$LOG_FILE"
}

echo "=== POS Auto-Sync Status Report ==="
echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check if scheduler is running
echo "1. Checking Background Scheduler..."
SCHEDULER_STATUS=$(docker compose -f "$COMPOSE_FILE" logs inventory-app --since 10m 2>/dev/null | grep -c "Background scheduler initialized successfully")

if [ "$SCHEDULER_STATUS" -gt 0 ]; then
    echo "   ✓ Background scheduler is running"
else
    echo "   ✗ Background scheduler may not be running"
fi

# Check recent auto-sync activity
echo ""
echo "2. Recent Auto-Sync Activity (last hour)..."
SYNC_COUNT=$(docker compose -f "$COMPOSE_FILE" logs inventory-app --since 1h 2>/dev/null | grep -c "Auto-sync complete for location")

if [ "$SYNC_COUNT" -gt 0 ]; then
    echo "   ✓ Found $SYNC_COUNT auto-sync operations in the last hour"
    echo ""
    echo "   Recent sync details:"
    docker compose -f "$COMPOSE_FILE" logs inventory-app --since 1h 2>/dev/null | \
        grep "Auto-sync complete for location" | \
        tail -5 | \
        sed 's/^/     /'
else
    echo "   • No auto-sync operations in the last hour (may be scheduled for later)"
fi

# Get POS configuration details
echo ""
echo "3. POS Configuration Status..."
docker compose -f "$COMPOSE_FILE" exec -T inventory-db psql -U inventory_user -d inventory_db << 'EOF'
SELECT
    pc.id,
    l.name AS location_name,
    pc.provider,
    pc.auto_sync_enabled,
    pc.auto_deduct_inventory,
    pc.sync_frequency_minutes,
    ROUND(pc.sync_frequency_minutes::numeric / 60, 1) AS "sync_hours",
    pc.is_active,
    pc.last_sync_date,
    CASE
        WHEN pc.last_sync_date IS NULL THEN 'Never synced'
        WHEN NOW() - pc.last_sync_date < INTERVAL '1 hour' THEN 'Less than 1 hour ago'
        WHEN NOW() - pc.last_sync_date < INTERVAL '24 hours' THEN
            ROUND(EXTRACT(EPOCH FROM (NOW() - pc.last_sync_date)) / 3600) || ' hours ago'
        ELSE
            ROUND(EXTRACT(EPOCH FROM (NOW() - pc.last_sync_date)) / 86400) || ' days ago'
    END AS last_sync_ago,
    CASE
        WHEN pc.last_sync_date IS NULL THEN 'Due now'
        WHEN NOW() >= pc.last_sync_date + (pc.sync_frequency_minutes || ' minutes')::INTERVAL THEN 'Due now'
        ELSE 'Next in ' || ROUND(EXTRACT(EPOCH FROM (
            pc.last_sync_date + (pc.sync_frequency_minutes || ' minutes')::INTERVAL - NOW()
        )) / 60) || ' minutes'
    END AS next_sync
FROM pos_configurations pc
LEFT JOIN locations l ON l.id = pc.location_id
ORDER BY pc.location_id;
EOF

# Get total sales count
echo ""
echo "4. Total Sales Records..."
TOTAL_SALES=$(docker compose -f "$COMPOSE_FILE" exec -T inventory-db \
    psql -U inventory_user -d inventory_db -t -c \
    "SELECT COUNT(*) FROM pos_sales;" 2>/dev/null | xargs)

echo "   Total POS sales in database: $TOTAL_SALES"

# Get recent sales
RECENT_SALES=$(docker compose -f "$COMPOSE_FILE" exec -T inventory-db \
    psql -U inventory_user -d inventory_db -t -c \
    "SELECT COUNT(*) FROM pos_sales WHERE created_at > NOW() - INTERVAL '24 hours';" 2>/dev/null | xargs)

echo "   Sales added in last 24 hours: $RECENT_SALES"

# Check for sync errors
echo ""
echo "5. Recent Sync Errors (last 24 hours)..."
ERROR_COUNT=$(docker compose -f "$COMPOSE_FILE" logs inventory-app --since 24h 2>/dev/null | \
    grep -E "Error.*sync|sync.*error" -i | wc -l)

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "   ✓ No sync errors found"
else
    echo "   ⚠ Found $ERROR_COUNT potential sync errors"
    echo ""
    echo "   Recent errors:"
    docker compose -f "$COMPOSE_FILE" logs inventory-app --since 24h 2>/dev/null | \
        grep -E "Error.*sync|sync.*error" -i | \
        tail -5 | \
        sed 's/^/     /'
fi

echo ""
echo "=== End of Report ==="
echo ""
echo "Notes:"
echo "  - Auto-sync runs every 10 minutes to check which locations need syncing"
echo "  - Each location syncs based on its configured frequency"
echo "  - Location 2 syncs every 2 hours, others every 8 hours"
echo "  - To manually trigger sync, use the POS Config page in the web interface"

# Check if email alerts should be sent
SEND_ALERT=false
ALERT_MESSAGE=""

# Check if scheduler is not running
if [ "$SCHEDULER_STATUS" -eq 0 ]; then
    SEND_ALERT=true
    ALERT_MESSAGE="${ALERT_MESSAGE}⚠️ Background scheduler may not be running\n"
fi

# Check if there are many sync errors
if [ "$ERROR_COUNT" -gt 5 ]; then
    SEND_ALERT=true
    ALERT_MESSAGE="${ALERT_MESSAGE}⚠️ High number of sync errors detected: $ERROR_COUNT errors in last 24 hours\n"
fi

# Check if no syncs in the last hour (may indicate a problem)
if [ "$SYNC_COUNT" -eq 0 ]; then
    # Only alert if scheduler should be running (check if it's been more than 15 minutes)
    LAST_SYNC_AGE=$(docker compose -f "$COMPOSE_FILE" exec -T inventory-db \
        psql -U inventory_user -d inventory_db -t -c \
        "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(last_sync_date)))/60 FROM pos_configurations WHERE last_sync_date IS NOT NULL;" 2>/dev/null | xargs)

    if [ -n "$LAST_SYNC_AGE" ] && [ "${LAST_SYNC_AGE%.*}" -gt 15 ]; then
        SEND_ALERT=true
        ALERT_MESSAGE="${ALERT_MESSAGE}⚠️ No auto-sync operations detected in the last hour\n"
        ALERT_MESSAGE="${ALERT_MESSAGE}Last sync was ${LAST_SYNC_AGE%.*} minutes ago\n"
    fi
fi

# Send email alert if needed
if [ "$SEND_ALERT" = true ] && [ -n "$ALERT_EMAIL" ]; then
    echo ""
    echo "🚨 Sending email alert to $ALERT_EMAIL..."
    send_email_alert "🚨 POS Sync Issue Detected - ${SYSTEM_NAME}" "$ALERT_MESSAGE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Alert sent: $ALERT_MESSAGE" >> "$LOG_FILE"
fi
