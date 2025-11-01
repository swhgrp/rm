#!/bin/bash
# Backup Rotation Script
# Keeps the last 7 days of backups, archives older ones

BACKUP_DIR="/opt/restaurant-system/backups"
ARCHIVE_DIR="/opt/archives/old-backups"
RETENTION_DAYS=7

# Create archive directory if it doesn't exist
mkdir -p "$ARCHIVE_DIR"

# Calculate retention (7 days * 2 files per day = 14 files to keep)
RETENTION_COUNT=$((RETENTION_DAYS * 2))

# Move old backups to archive
cd "$BACKUP_DIR" || exit 1

# Get list of files older than retention, sorted by modification time
ls -t *.sql.gz 2>/dev/null | tail -n +$((RETENTION_COUNT + 1)) | while read -r file; do
    if [ -f "$file" ]; then
        mv "$file" "$ARCHIVE_DIR/"
        echo "Archived: $file"
    fi
done

echo "Backup rotation complete. Keeping last $RETENTION_DAYS days."
echo "Active backups: $(ls -1 *.sql.gz 2>/dev/null | wc -l)"
echo "Archived backups: $(ls -1 "$ARCHIVE_DIR" 2>/dev/null | wc -l)"
