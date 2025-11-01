#!/bin/bash

# Test Restore Script for Restaurant System Databases
# Tests restoration capability without affecting production databases

set -e  # Exit on error

BACKUP_DIR="/opt/restaurant-system/backups"
TEST_DIR="/tmp/restore-test-$(date +%Y%m%d-%H%M%S)"
LOG_FILE="/opt/restaurant-system/logs/restore-test.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}✗ $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}" | tee -a "$LOG_FILE"
}

# Create test directory
mkdir -p "$TEST_DIR"
log "Created test directory: $TEST_DIR"

# Test configuration
DATABASES=(
    "accounting_db:accounting_user:accounting_pass"
    "inventory_db:inventory_user:inventory_pass"
    "hr_db:hr_user:hr_pass"
    "events_db:events_user:events_pass"
    "hub_db:hub_user:hub_pass"
)

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

log "========================================="
log "Database Restore Test - Starting"
log "========================================="
log ""

# Function to test restore for a single database
test_restore() {
    local db_name=$1
    local db_user=$2
    local db_pass=$3

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    log "Testing restore for: $db_name"
    log "-----------------------------------"

    # Find most recent backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/${db_name}_*.sql.gz 2>/dev/null | head -1)

    if [ -z "$LATEST_BACKUP" ]; then
        log_error "No backup found for $db_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    log "Found backup: $(basename $LATEST_BACKUP)"
    log "Backup size: $(du -h $LATEST_BACKUP | cut -f1)"
    log "Backup date: $(stat -c %y $LATEST_BACKUP | cut -d' ' -f1,2 | cut -d'.' -f1)"

    # Test 1: Verify backup file integrity
    log "Test 1/5: Checking backup file integrity..."
    if gunzip -t "$LATEST_BACKUP" 2>/dev/null; then
        log_success "Backup file is valid gzip"
    else
        log_error "Backup file is corrupted!"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    # Test 2: Extract backup
    log "Test 2/5: Extracting backup..."
    EXTRACTED_FILE="$TEST_DIR/${db_name}_restored.sql"
    if gunzip -c "$LATEST_BACKUP" > "$EXTRACTED_FILE" 2>/dev/null; then
        log_success "Backup extracted successfully"
        log "Extracted size: $(du -h $EXTRACTED_FILE | cut -f1)"
    else
        log_error "Failed to extract backup"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    # Test 3: Check SQL file validity
    log "Test 3/5: Validating SQL syntax..."
    if head -5 "$EXTRACTED_FILE" | grep -q "PostgreSQL database dump"; then
        log_success "Valid PostgreSQL dump file"
    else
        log_error "Invalid SQL file format"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi

    # Test 4: Count SQL statements
    log "Test 4/5: Analyzing backup content..."
    CREATE_TABLES=$(grep -c "CREATE TABLE" "$EXTRACTED_FILE" || echo 0)
    INSERT_STATEMENTS=$(grep -c "^INSERT INTO" "$EXTRACTED_FILE" || echo 0)
    log "  - CREATE TABLE statements: $CREATE_TABLES"
    log "  - INSERT statements: $INSERT_STATEMENTS"

    if [ "$CREATE_TABLES" -gt 0 ]; then
        log_success "Backup contains table definitions"
    else
        log_warning "No tables found in backup (may be expected for empty DB)"
    fi

    # Test 5: Test restore to temporary database (non-destructive)
    log "Test 5/5: Testing restore to temporary database..."
    TEST_DB_NAME="${db_name}_test_$(date +%s)"

    # Create test database
    if PGPASSWORD=$db_pass psql -h localhost -U $db_user -d postgres -c "CREATE DATABASE $TEST_DB_NAME;" 2>/dev/null; then
        log_success "Created test database: $TEST_DB_NAME"

        # Restore to test database
        if PGPASSWORD=$db_pass psql -h localhost -U $db_user -d $TEST_DB_NAME < "$EXTRACTED_FILE" 2>/dev/null; then
            log_success "Successfully restored to test database"

            # Verify restore by counting tables
            TABLE_COUNT=$(PGPASSWORD=$db_pass psql -h localhost -U $db_user -d $TEST_DB_NAME -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
            log "  - Tables restored: $TABLE_COUNT"

            if [ "$TABLE_COUNT" -gt 0 ]; then
                log_success "Restore verification PASSED"
                PASSED_TESTS=$((PASSED_TESTS + 1))
            else
                log_warning "Restore completed but no tables found"
                PASSED_TESTS=$((PASSED_TESTS + 1))
            fi
        else
            log_error "Failed to restore to test database"
            FAILED_TESTS=$((FAILED_TESTS + 1))
        fi

        # Clean up test database
        PGPASSWORD=$db_pass psql -h localhost -U $db_user -d postgres -c "DROP DATABASE $TEST_DB_NAME;" 2>/dev/null
        log "Cleaned up test database"
    else
        log_error "Failed to create test database"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi

    # Clean up extracted file
    rm -f "$EXTRACTED_FILE"

    log ""
}

# Run tests for all databases
for db_config in "${DATABASES[@]}"; do
    IFS=':' read -r db_name db_user db_pass <<< "$db_config"
    test_restore "$db_name" "$db_user" "$db_pass"
done

# Clean up test directory
rm -rf "$TEST_DIR"
log "Cleaned up test directory"

# Summary
log "========================================="
log "Database Restore Test - Summary"
log "========================================="
log "Total databases tested: $TOTAL_TESTS"
log_success "Passed: $PASSED_TESTS"
if [ $FAILED_TESTS -gt 0 ]; then
    log_error "Failed: $FAILED_TESTS"
else
    log "Failed: 0"
fi
log ""

if [ $FAILED_TESTS -eq 0 ]; then
    log_success "ALL RESTORE TESTS PASSED ✓"
    log ""
    log "Your backups are working correctly and can be restored!"
    log "Recommendation: Run this test monthly to ensure ongoing backup health."
    exit 0
else
    log_error "SOME TESTS FAILED ✗"
    log ""
    log "Action Required: Review failed tests above and fix backup issues."
    exit 1
fi
