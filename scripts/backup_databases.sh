#!/bin/bash
#
# Automated Database Backup Script
# Backs up both inventory and accounting databases
# Retains backups for 30 days
#

BACKUP_DIR="/opt/restaurant-system/backups"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/opt/restaurant-system/logs/backup.log"

# Create directories if they don't exist
mkdir -p "$BACKUP_DIR"
mkdir -p "/opt/restaurant-system/logs"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message "=== Starting database backup ==="

# Backup inventory database
log_message "Backing up inventory database..."
if docker compose -f /opt/restaurant-system/docker-compose.yml exec -T inventory-db \
    pg_dump -U inventory_user inventory_db | \
    gzip > "$BACKUP_DIR/inventory_db_$DATE.sql.gz"; then

    INVENTORY_SIZE=$(du -h "$BACKUP_DIR/inventory_db_$DATE.sql.gz" | cut -f1)
    log_message "✓ Inventory database backed up successfully ($INVENTORY_SIZE)"
else
    log_message "✗ ERROR: Inventory database backup failed!"
    exit 1
fi

# Backup accounting database
log_message "Backing up accounting database..."
if docker compose -f /opt/restaurant-system/docker-compose.yml exec -T accounting-db \
    pg_dump -U accounting_user accounting_db | \
    gzip > "$BACKUP_DIR/accounting_db_$DATE.sql.gz"; then

    ACCOUNTING_SIZE=$(du -h "$BACKUP_DIR/accounting_db_$DATE.sql.gz" | cut -f1)
    log_message "✓ Accounting database backed up successfully ($ACCOUNTING_SIZE)"
else
    log_message "✗ ERROR: Accounting database backup failed!"
    exit 1
fi

# Count total backups
TOTAL_BACKUPS=$(ls -1 "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l)
log_message "Total backups in directory: $TOTAL_BACKUPS"

# Remove backups older than 30 days
log_message "Cleaning up old backups (older than 30 days)..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -type f -delete -print | wc -l)
if [ "$DELETED_COUNT" -gt 0 ]; then
    log_message "Deleted $DELETED_COUNT old backup(s)"
else
    log_message "No old backups to delete"
fi

# Show disk usage
BACKUP_DIR_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log_message "Backup directory size: $BACKUP_DIR_SIZE"

log_message "=== Backup completed successfully ==="

# Optional: Send email notification (uncomment if email is configured)
# echo "Database backup completed successfully at $DATE" | \
#   mail -s "Restaurant System - Backup Success" admin@swhgrp.com

exit 0
