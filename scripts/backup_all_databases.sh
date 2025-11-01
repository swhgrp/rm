#!/bin/bash
#
# Comprehensive Database Backup Script
# Backs up ALL restaurant system databases
# Designed for automated cron execution
#

set -e  # Exit on error

BACKUP_DIR="/opt/restaurant-system/backups"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/opt/restaurant-system/logs/backup.log"
COMPOSE_FILE="/opt/restaurant-system/docker-compose.yml"

# Create directories if they don't exist
mkdir -p "$BACKUP_DIR"
mkdir -p "/opt/restaurant-system/logs"

# Colors for output (only when running interactively)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    NC='\033[0m'
else
    GREEN=''
    RED=''
    NC=''
fi

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}✗ $1${NC}" | tee -a "$LOG_FILE"
}

log_message "========================================="
log_message "Database Backup - Starting"
log_message "========================================="

# Database configurations: "container:user:database"
DATABASES=(
    "inventory-db:inventory_user:inventory_db"
    "accounting-db:accounting_user:accounting_db"
    "hr-db:hr_user:hr_db"
    "events-db:events_user:events_db"
    "hub-db:hub_user:integration_hub_db"
)

BACKUP_COUNT=0
FAILED_COUNT=0

# Backup each database
for db_config in "${DATABASES[@]}"; do
    IFS=':' read -r container user database <<< "$db_config"

    log_message "Backing up $database..."

    BACKUP_FILE="$BACKUP_DIR/${database}_${DATE}.sql.gz"

    if docker compose -f "$COMPOSE_FILE" exec -T "$container" \
        pg_dump -U "$user" "$database" | \
        gzip > "$BACKUP_FILE" 2>>"$LOG_FILE"; then

        FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        log_success "$database backed up successfully ($FILE_SIZE)"
        BACKUP_COUNT=$((BACKUP_COUNT + 1))
    else
        log_error "$database backup FAILED"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        # Don't exit - try to backup remaining databases
    fi
done

log_message "-----------------------------------"
log_message "Backup Summary:"
log_message "  Successful: $BACKUP_COUNT"
log_message "  Failed: $FAILED_COUNT"

# Count total backups
TOTAL_BACKUPS=$(ls -1 "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l)
log_message "  Total backups in directory: $TOTAL_BACKUPS"

# Show disk usage
BACKUP_DIR_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log_message "  Backup directory size: $BACKUP_DIR_SIZE"

log_message "========================================="

if [ $FAILED_COUNT -eq 0 ]; then
    log_success "All backups completed successfully"
    exit 0
else
    log_error "Some backups failed - check log for details"
    exit 1
fi
