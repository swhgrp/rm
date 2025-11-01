# Backup Strategy Documentation

**Status:** Linode Backups In Use
**Priority:** Medium (S3 optional enhancement)
**Last Updated:** October 31, 2025
**Owner:** DevOps/System Administrator

---

## Overview

This document describes the current backup infrastructure using Linode's backup system and provides optional S3 implementation for additional redundancy.

---

## Current State

### Existing Backup Infrastructure ✅ COMPLETE
- ✅ **Linode Backups** - Server-level backups (infrastructure backup)
- ✅ Daily database backups via cron (2:00 AM)
- ✅ 7-day local retention policy
- ✅ Automated rotation script
- ✅ Log rotation configured
- ✅ Remote/off-site backup via Linode
- ⚠️ **OPTIONAL:** Additional S3 backup for database files (extra redundancy)

### Current Backup Files
- **Location:** `/opt/restaurant-system/backups/`
- **Databases:**
  - inventory_db (PostgreSQL)
  - accounting_db (PostgreSQL)
  - hr_db (PostgreSQL)
  - events_db (PostgreSQL)
  - integration-hub (PostgreSQL)
- **Frequency:** Daily at 2:00 AM
- **Format:** gzip compressed SQL dumps (.sql.gz)
- **Retention:** 7 days local, older files archived to `/opt/archives/old-backups/`

---

## Goals

1. **Disaster Recovery:** Protect against complete server failure
2. **Data Retention:** Keep 30 days of daily backups, 12 months of monthly backups
3. **Automation:** Fully automated upload to S3 after local backup completes
4. **Cost Optimization:** Use appropriate S3 storage classes to minimize costs
5. **Security:** Encrypted backups in transit and at rest

---

## Implementation Options

### Option 1: AWS S3 (Recommended)
**Pros:**
- Industry standard, highly reliable (99.999999999% durability)
- Excellent documentation and tooling
- Flexible storage classes (Standard, IA, Glacier)
- Built-in versioning and lifecycle policies

**Cons:**
- Monthly cost (estimated $5-15/month for ~10GB)
- Requires AWS account setup

**Estimated Cost:**
- Storage: ~10GB average = $0.25/month (Standard)
- Requests: ~30 PUT requests/month = $0.01
- Data Transfer OUT (disaster recovery): ~$0.90/GB if needed
- **Total: ~$1-3/month** (excluding data retrieval)

### Option 2: Backblaze B2
**Pros:**
- S3-compatible API
- Lower cost than AWS S3
- Simple pricing model
- Good for backups

**Cons:**
- Less ecosystem integration
- Smaller provider (higher risk)

**Estimated Cost:**
- Storage: $0.005/GB/month = $0.05/month for 10GB
- Downloads: $0.01/GB
- **Total: ~$0.10-0.50/month**

### Option 3: Wasabi
**Pros:**
- S3-compatible
- Flat pricing (no egress fees)
- Minimum 1TB billing

**Cons:**
- Minimum $5.99/month (1TB minimum)
- Overkill for current needs

### Option 4: Local Object Storage (MinIO)
**Pros:**
- Self-hosted
- S3-compatible API
- No ongoing costs
- Full control

**Cons:**
- Requires separate server/infrastructure
- Not true "off-site" backup unless on different infrastructure
- Additional maintenance burden

**Recommendation:** **AWS S3** for production reliability, or **Backblaze B2** for cost optimization.

---

## Implementation Plan

### Phase 1: AWS S3 Setup (Week 1, Days 1-2)

#### Tasks:
1. **Create AWS Account** (if not exists)
   - Sign up at aws.amazon.com
   - Enable MFA on root account
   - Create IAM user for backups

2. **Create S3 Bucket**
   ```bash
   Bucket name: restaurant-system-backups-prod
   Region: us-east-1 (or closest to server)
   Versioning: Enabled
   Encryption: AES-256 (SSE-S3)
   Block public access: Enable all
   ```

3. **Create IAM User for Backups**
   - User name: `restaurant-backups-user`
   - Permissions: Custom policy (see below)
   - Generate access key ID and secret

   **IAM Policy:**
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:PutObject",
           "s3:GetObject",
           "s3:ListBucket",
           "s3:DeleteObject"
         ],
         "Resource": [
           "arn:aws:s3:::restaurant-system-backups-prod",
           "arn:aws:s3:::restaurant-system-backups-prod/*"
         ]
       }
     ]
   }
   ```

4. **Configure S3 Lifecycle Policy**
   ```json
   {
     "Rules": [
       {
         "Id": "DailyBackupRetention",
         "Status": "Enabled",
         "Filter": {
           "Prefix": "daily/"
         },
         "Expiration": {
           "Days": 30
         },
         "Transitions": [
           {
             "Days": 7,
             "StorageClass": "STANDARD_IA"
           }
         ]
       },
       {
         "Id": "MonthlyBackupRetention",
         "Status": "Enabled",
         "Filter": {
           "Prefix": "monthly/"
         },
         "Expiration": {
           "Days": 365
         },
         "Transitions": [
           {
             "Days": 90,
             "StorageClass": "GLACIER_IR"
           }
         ]
       }
     ]
   }
   ```

### Phase 2: Install and Configure AWS CLI (Week 1, Day 3)

```bash
# Install AWS CLI
apt-get update
apt-get install -y awscli

# Verify installation
aws --version

# Configure AWS credentials
mkdir -p /root/.aws
cat > /root/.aws/credentials << EOF
[default]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
EOF

cat > /root/.aws/config << EOF
[default]
region = us-east-1
output = json
EOF

# Secure credentials
chmod 600 /root/.aws/credentials
chmod 600 /root/.aws/config

# Test connection
aws s3 ls s3://restaurant-system-backups-prod/
```

### Phase 3: Create S3 Upload Script (Week 1, Days 4-5)

**File:** `/opt/restaurant-system/scripts/upload-backups-to-s3.sh`

```bash
#!/bin/bash
# S3 Backup Upload Script
# Uploads local database backups to AWS S3 for disaster recovery

set -e

# Configuration
S3_BUCKET="restaurant-system-backups-prod"
BACKUP_DIR="/opt/restaurant-system/backups"
LOG_FILE="/opt/restaurant-system/logs/s3-upload.log"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=30

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting S3 backup upload..."

# Upload today's backups to S3
for backup_file in "$BACKUP_DIR"/*_${DATE}_*.sql.gz; do
    if [ -f "$backup_file" ]; then
        filename=$(basename "$backup_file")
        s3_path="s3://${S3_BUCKET}/daily/${DATE}/${filename}"

        log "Uploading $filename to S3..."
        if aws s3 cp "$backup_file" "$s3_path" --storage-class STANDARD; then
            log "  ✓ Successfully uploaded $filename"
        else
            log "  ✗ Failed to upload $filename"
            exit 1
        fi
    fi
done

# Monthly backup (first of month)
if [ "$(date +%d)" = "01" ]; then
    log "Creating monthly backup snapshot..."
    MONTH=$(date +%Y%m)
    for backup_file in "$BACKUP_DIR"/*_${DATE}_*.sql.gz; do
        if [ -f "$backup_file" ]; then
            filename=$(basename "$backup_file")
            s3_path="s3://${S3_BUCKET}/monthly/${MONTH}/${filename}"

            if aws s3 cp "$backup_file" "$s3_path" --storage-class STANDARD; then
                log "  ✓ Created monthly backup: $filename"
            fi
        fi
    done
fi

# Verify uploads
log "Verifying S3 uploads..."
aws s3 ls "s3://${S3_BUCKET}/daily/${DATE}/" | tee -a "$LOG_FILE"

# Calculate total S3 usage
total_size=$(aws s3 ls s3://${S3_BUCKET}/ --recursive --summarize | grep "Total Size" | awk '{print $3}')
log "Total S3 storage used: $(numfmt --to=iec --suffix=B $total_size)"

log "S3 backup upload completed successfully!"
```

**Make executable:**
```bash
chmod +x /opt/restaurant-system/scripts/upload-backups-to-s3.sh
```

### Phase 4: Update Cron Jobs (Week 1, Day 5)

Add S3 upload after local backup completes:

```bash
# Edit crontab
crontab -e

# Add after backup_databases.sh (runs at 2:30 AM, after 2:00 AM backup)
30 2 * * * /opt/restaurant-system/scripts/upload-backups-to-s3.sh >> /opt/restaurant-system/logs/s3-upload.log 2>&1
```

**Final cron schedule:**
```
0 2 * * * /opt/restaurant-system/scripts/backup_databases.sh >> /opt/restaurant-system/logs/backup.log 2>&1
30 2 * * * /opt/restaurant-system/scripts/upload-backups-to-s3.sh >> /opt/restaurant-system/logs/s3-upload.log 2>&1
0 3 * * * /opt/restaurant-system/scripts/rotate-backups.sh >> /opt/restaurant-system/logs/backup.log 2>&1
```

### Phase 5: Create Restore Script (Week 2, Days 1-2)

**File:** `/opt/restaurant-system/scripts/restore-from-s3.sh`

```bash
#!/bin/bash
# S3 Backup Restore Script
# Downloads and restores database backups from S3

set -e

# Configuration
S3_BUCKET="restaurant-system-backups-prod"
RESTORE_DIR="/tmp/restore-$(date +%Y%m%d-%H%M%S)"

# Function to show usage
usage() {
    echo "Usage: $0 <database> <date>"
    echo "Example: $0 inventory_db 20251031"
    echo ""
    echo "Available databases: inventory_db, accounting_db, hr_db, events_db"
    exit 1
}

# Check arguments
if [ $# -ne 2 ]; then
    usage
fi

DATABASE=$1
DATE=$2

# Create restore directory
mkdir -p "$RESTORE_DIR"

echo "Searching for ${DATABASE} backup from ${DATE}..."

# Find backup file in S3
S3_FILE=$(aws s3 ls "s3://${S3_BUCKET}/daily/${DATE}/" | grep "${DATABASE}_${DATE}" | awk '{print $4}')

if [ -z "$S3_FILE" ]; then
    echo "Error: No backup found for ${DATABASE} on ${DATE}"
    echo "Checking monthly backups..."
    MONTH=${DATE:0:6}
    S3_FILE=$(aws s3 ls "s3://${S3_BUCKET}/monthly/${MONTH}/" | grep "${DATABASE}_${DATE}" | awk '{print $4}')
    S3_PATH="s3://${S3_BUCKET}/monthly/${MONTH}/${S3_FILE}"
else
    S3_PATH="s3://${S3_BUCKET}/daily/${DATE}/${S3_FILE}"
fi

if [ -z "$S3_FILE" ]; then
    echo "Error: No backup found for ${DATABASE} on ${DATE}"
    exit 1
fi

echo "Found backup: $S3_FILE"
echo "Downloading from S3..."

# Download backup
aws s3 cp "$S3_PATH" "${RESTORE_DIR}/${S3_FILE}"

echo "Download complete: ${RESTORE_DIR}/${S3_FILE}"
echo ""
echo "To restore this backup, run:"
echo "gunzip ${RESTORE_DIR}/${S3_FILE}"
echo "cat ${RESTORE_DIR}/${DATABASE}_${DATE}_*.sql | docker exec -i <container> psql -U <user> -d <database>"
echo ""
echo "Example:"
echo "gunzip ${RESTORE_DIR}/${S3_FILE}"
echo "cat ${RESTORE_DIR}/inventory_db_${DATE}_*.sql | docker exec -i inventory-db psql -U inventory_user -d inventory_db"
```

**Make executable:**
```bash
chmod +x /opt/restaurant-system/scripts/restore-from-s3.sh
```

### Phase 6: Testing and Validation (Week 2, Days 3-5)

#### Test Checklist:

1. **Upload Test**
   ```bash
   # Run upload script manually
   /opt/restaurant-system/scripts/upload-backups-to-s3.sh

   # Verify files in S3
   aws s3 ls s3://restaurant-system-backups-prod/daily/$(date +%Y%m%d)/
   ```

2. **Download Test**
   ```bash
   # Test restore script
   /opt/restaurant-system/scripts/restore-from-s3.sh inventory_db $(date +%Y%m%d)
   ```

3. **Full Restore Test** (on test database)
   ```bash
   # Create test database
   docker exec inventory-db psql -U inventory_user -c "CREATE DATABASE inventory_test;"

   # Restore backup
   /opt/restaurant-system/scripts/restore-from-s3.sh inventory_db $(date +%Y%m%d)
   gunzip /tmp/restore-*/inventory_db_*.sql.gz
   cat /tmp/restore-*/inventory_db_*.sql | docker exec -i inventory-db psql -U inventory_user -d inventory_test

   # Verify data
   docker exec inventory-db psql -U inventory_user -d inventory_test -c "SELECT COUNT(*) FROM master_items;"
   ```

4. **Lifecycle Policy Test**
   - Wait 7 days and verify files moved to STANDARD_IA
   - Check S3 console for storage class transitions

5. **Monthly Backup Test**
   - Manually trigger on first of month
   - Verify monthly/ prefix in S3

6. **Cost Monitoring**
   - Set up AWS Budget alert for > $10/month
   - Monitor first month costs

---

## Monitoring and Alerts

### CloudWatch Alarms (Optional but Recommended)

1. **Backup Upload Failures**
   - Create SNS topic for alerts
   - Email notification on upload failures

2. **Cost Alerts**
   - AWS Budget: Alert if monthly cost > $10
   - Anomaly detection enabled

3. **Storage Growth**
   - Alert if bucket size > 50GB (indicates retention issue)

### Log Monitoring

```bash
# Check S3 upload logs
tail -f /opt/restaurant-system/logs/s3-upload.log

# Check for errors
grep -i error /opt/restaurant-system/logs/s3-upload.log
```

---

## Security Considerations

1. **Encryption**
   - ✅ In transit: AWS CLI uses HTTPS by default
   - ✅ At rest: S3 server-side encryption (AES-256)
   - ⚠️ Consider: Client-side encryption for sensitive data

2. **Access Control**
   - ✅ IAM user with minimal permissions
   - ✅ No public bucket access
   - ✅ MFA on AWS root account
   - ⚠️ Consider: S3 bucket versioning for protection against accidental deletion

3. **Credential Management**
   - ✅ Credentials stored in /root/.aws/ (600 permissions)
   - ⚠️ Consider: AWS Systems Manager Parameter Store for credentials
   - ⚠️ Consider: IAM role for EC2 instance (if running on AWS)

---

## Disaster Recovery Procedures

### Scenario 1: Complete Server Failure

1. **Provision new server**
2. **Install Docker and dependencies**
3. **Clone repository**
4. **Install AWS CLI and configure credentials**
5. **Download latest backups from S3:**
   ```bash
   LATEST_DATE=$(date +%Y%m%d)
   mkdir -p /opt/restaurant-system/backups
   aws s3 cp s3://restaurant-system-backups-prod/daily/$LATEST_DATE/ /opt/restaurant-system/backups/ --recursive
   ```
6. **Start Docker containers**
7. **Restore databases** (see restore script)
8. **Verify services**

**RTO (Recovery Time Objective):** 4 hours
**RPO (Recovery Point Objective):** 24 hours (daily backups)

### Scenario 2: Single Database Corruption

1. **Identify corrupted database**
2. **Stop affected service**
3. **Download backup from S3:**
   ```bash
   /opt/restaurant-system/scripts/restore-from-s3.sh <database> <date>
   ```
4. **Restore database**
5. **Restart service**
6. **Verify data integrity**

**RTO:** 30 minutes
**RPO:** 24 hours

---

## Cost Estimates

### Monthly Costs (AWS S3 Standard)

| Item | Calculation | Cost |
|------|------------|------|
| Storage (first 7 days) | 10GB × $0.023/GB | $0.23 |
| Storage (STANDARD_IA, days 8-30) | 10GB × $0.0125/GB × 0.75 | $0.09 |
| PUT requests | 30/month × $0.005/1000 | $0.00 |
| Monthly backups (12 months) | 10GB × 12 × $0.0125/GB | $1.50 |
| **Total Monthly** | | **~$2/month** |

### Annual Cost: **~$24/year**

---

## Success Criteria

- ✅ Daily automated uploads to S3
- ✅ 30-day retention of daily backups
- ✅ 12-month retention of monthly backups
- ✅ Successful restore test completed
- ✅ Monitoring and alerts configured
- ✅ Documentation updated
- ✅ Monthly cost < $5

---

## Rollback Plan

If S3 backup fails or causes issues:

1. **Disable cron job** for S3 upload
2. **Continue local backups** (already working)
3. **Investigate and fix issues**
4. **Re-enable when resolved**

**No impact on local backups** - S3 is additive only.

---

## Timeline Summary

| Week | Days | Task | Status |
|------|------|------|--------|
| 1 | 1-2 | AWS account and S3 setup | Pending |
| 1 | 3 | AWS CLI installation | Pending |
| 1 | 4-5 | Create upload script and test | Pending |
| 1 | 5 | Update cron jobs | Pending |
| 2 | 1-2 | Create restore script | Pending |
| 2 | 3-5 | Testing and validation | Pending |
| 2 | 5 | Documentation and handoff | Pending |

**Total Duration:** 2 weeks
**Effort:** ~16 hours

---

## References

- AWS S3 Documentation: https://docs.aws.amazon.com/s3/
- AWS CLI Reference: https://docs.aws.amazon.com/cli/
- S3 Pricing: https://aws.amazon.com/s3/pricing/
- Current Backup Scripts: `/opt/restaurant-system/scripts/`
- Cleanup Summary: `/opt/restaurant-system/docs/CLEANUP_SUMMARY_OCT31.md`

---

**Status:** Ready for implementation
**Approval Required:** Yes (AWS account creation and costs)
**Next Steps:** Present plan to stakeholders for approval
