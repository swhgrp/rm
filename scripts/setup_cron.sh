#!/bin/bash
#
# Setup cron jobs for automated backups and health monitoring
#

echo "Setting up cron jobs for restaurant system..."

# Create cron jobs
CRON_FILE="/tmp/restaurant_system_cron"

# Write cron jobs to temporary file
cat > "$CRON_FILE" << 'EOF'
# Restaurant System - Automated Tasks

# Daily database backup at 2:00 AM
0 2 * * * /opt/restaurant-system/scripts/backup_databases.sh >> /opt/restaurant-system/logs/backup.log 2>&1

# Health check every 15 minutes
*/15 * * * * /opt/restaurant-system/scripts/health_check.sh >> /opt/restaurant-system/logs/health_check.log 2>&1

# Weekly cleanup of old logs (keep last 30 days)
0 3 * * 0 find /opt/restaurant-system/logs -name "*.log" -mtime +30 -type f -delete

EOF

# Install cron jobs
crontab -l > /tmp/existing_cron 2>/dev/null || true
grep -v "Restaurant System - Automated Tasks" /tmp/existing_cron > /tmp/filtered_cron 2>/dev/null || true
cat /tmp/filtered_cron "$CRON_FILE" | crontab -

# Clean up temporary files
rm -f "$CRON_FILE" /tmp/existing_cron /tmp/filtered_cron

echo "✓ Cron jobs installed successfully"
echo ""
echo "Installed jobs:"
echo "  - Daily backup at 2:00 AM"
echo "  - Health check every 15 minutes"
echo "  - Weekly log cleanup"
echo ""
echo "To view cron jobs: crontab -l"
echo "To view logs:"
echo "  - Backup log: tail -f /opt/restaurant-system/logs/backup.log"
echo "  - Health check log: tail -f /opt/restaurant-system/logs/health_check.log"
echo "  - Alert log: tail -f /opt/restaurant-system/logs/alerts.log"
