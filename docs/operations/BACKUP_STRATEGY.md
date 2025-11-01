# Complete Backup Strategy - Restaurant Management System

**Last Updated:** October 31, 2025
**Status:** ✅ Production Ready
**Coverage:** Multi-layer backup protection

---

## Executive Summary

The restaurant management system employs a **multi-layer backup strategy** combining:
1. **Linode infrastructure backups** (server-level)
2. **Local database backups** (application-level)
3. **Automated rotation** (retention management)

This provides comprehensive protection against data loss, hardware failure, and disaster scenarios.

---

## Backup Layers

### Layer 1: Linode Backups ✅ ACTIVE

**Type:** Full server snapshots (infrastructure-level)
**Provider:** Linode Backup Service
**Coverage:** Entire server including OS, applications, data, configurations

#### Features:
- **Automatic daily backups** (managed by Linode)
- **Off-site storage** (separate from production server)
- **Point-in-time recovery** (restore entire server to specific backup)
- **Snapshot retention** (Linode's retention policy)
- **One-click restore** (via Linode Cloud Manager)

#### What's Protected:
- ✅ Operating system and configurations
- ✅ Docker containers and images
- ✅ Application code and files
- ✅ Database volumes (Docker volumes)
- ✅ All system files and logs
- ✅ SSL certificates
- ✅ Configuration files

#### Recovery Scenarios:
- **Complete server failure** → Restore from Linode backup
- **Hardware failure** → Deploy backup to new Linode instance
- **Accidental system changes** → Rollback to previous snapshot

#### Access:
- Linode Cloud Manager → Backups tab
- Recovery Time: ~30-60 minutes for full server restore

---

### Layer 2: Local Database Backups ✅ ACTIVE

**Type:** PostgreSQL dumps (application-level)
**Coverage:** Database content only
**Frequency:** Daily at 2:00 AM
**Retention:** 7 days local, older backups archived

#### Features:
- **Granular database recovery** (restore individual databases)
- **SQL dump format** (portable, human-readable)
- **Compressed storage** (gzip compression)
- **Automated rotation** (7-day retention)
- **Fast restoration** (database-specific recovery)

#### What's Protected:
- ✅ inventory_db (Inventory Management)
- ✅ accounting_db (Accounting/GL)
- ✅ hr_db (HR/Payroll)
- ✅ events_db (Event Management)
- ✅ integration_hub_db (Integration Hub)

#### Backup Process:
```bash
# Automated via cron at 2:00 AM
/opt/restaurant-system/scripts/backup_databases.sh

# Rotation at 3:00 AM (keeps last 7 days)
/opt/restaurant-system/scripts/rotate-backups.sh
```

#### File Locations:
- **Active backups:** `/opt/restaurant-system/backups/` (last 7 days)
- **Archived backups:** `/opt/archives/old-backups/` (older than 7 days)

#### File Format:
```
inventory_db_20251031_020001.sql.gz
accounting_db_20251031_020001.sql.gz
hr_db_20251031_020001.sql.gz
events_db_20251031_020001.sql.gz
```

#### Recovery Scenarios:
- **Single database corruption** → Restore from SQL dump
- **Accidental data deletion** → Restore from recent backup
- **Need specific database state** → Restore from specific date

---

### Layer 3: Log Rotation ✅ ACTIVE

**Type:** System and application logs
**Coverage:** Health checks, alerts, backup logs
**Frequency:** Daily rotation
**Retention:** 7 days

#### Configuration:
- **File:** `/etc/logrotate.d/restaurant-system`
- **Logs managed:**
  - health_check.log (was 6.5MB, now rotated)
  - alerts.log
  - backup.log
  - s3-upload.log (if S3 implemented)

#### Features:
- Daily rotation
- Compression after rotation
- 7-day retention
- Automatic cleanup

---

## Backup Schedule

### Daily Operations

| Time | Task | Script | Description |
|------|------|--------|-------------|
| 2:00 AM | Database Backup | backup_databases.sh | Dump all 5 databases to SQL files |
| 3:00 AM | Backup Rotation | rotate-backups.sh | Keep last 7 days, archive older |
| Daily (Linode) | Server Snapshot | Linode automatic | Full server backup by Linode |
| Daily (System) | Log Rotation | logrotate | Rotate and compress logs |

### Weekly Operations

| Day | Task | Description |
|-----|------|-------------|
| Sunday 3:00 AM | Old Log Cleanup | Delete logs older than 30 days |

---

## Recovery Procedures

### Scenario 1: Complete Server Failure (Catastrophic)

**Use:** Linode Backups (Layer 1)

**Steps:**
1. Log into Linode Cloud Manager
2. Navigate to your Linode → Backups tab
3. Select most recent backup
4. Click "Restore to this Linode" or "Deploy to New Linode"
5. Wait for restore to complete (~30-60 minutes)
6. Verify all services are running
7. Check data integrity

**RTO (Recovery Time Objective):** 1-2 hours
**RPO (Recovery Point Objective):** Up to 24 hours (last Linode backup)

**When to Use:**
- Complete server failure
- Hardware failure
- Need to restore entire system
- Major system corruption

---

### Scenario 2: Single Database Corruption/Loss

**Use:** Local Database Backups (Layer 2)

**Steps:**

#### 2a. List Available Backups
```bash
ls -lt /opt/restaurant-system/backups/inventory_db_*.sql.gz
```

#### 2b. Choose Backup Date
```bash
# Example: Restore inventory_db from October 30, 2025
BACKUP_FILE="/opt/restaurant-system/backups/inventory_db_20251030_020001.sql.gz"
```

#### 2c. Stop Affected Service (optional but recommended)
```bash
docker stop inventory-app
```

#### 2d. Restore Database
```bash
# Decompress and restore
gunzip < $BACKUP_FILE | docker exec -i inventory-db psql -U inventory_user -d inventory_db
```

#### 2e. Restart Service
```bash
docker start inventory-app
```

#### 2f. Verify Data
```bash
# Check tables and data
docker exec inventory-db psql -U inventory_user -d inventory_db -c "\dt"
docker exec inventory-db psql -U inventory_user -d inventory_db -c "SELECT COUNT(*) FROM master_items;"
```

**RTO:** 15-30 minutes
**RPO:** Up to 24 hours (last database backup)

**When to Use:**
- Single database corruption
- Accidental data deletion
- Need to restore specific database
- Testing/development purposes

---

### Scenario 3: Need Older Backup (7+ days old)

**Use:** Archived Backups

**Steps:**

#### 3a. Check Archived Backups
```bash
ls -lt /opt/archives/old-backups/inventory_db_*.sql.gz
```

#### 3b. Follow Same Restore Process
Use Scenario 2 steps, but use archived backup file path instead.

**When to Use:**
- Need data from more than 7 days ago
- Compliance/audit requirements
- Historical data recovery

---

### Scenario 4: Restore After Linode Recovery

If you've restored from Linode backup but need database at a different point in time:

1. **Restore server from Linode backup** (gets infrastructure)
2. **Then restore specific database** from local backup (gets precise data state)

This gives you maximum flexibility in recovery.

---

## Data Protection Matrix

| Data Type | Linode Backup | Local DB Backup | Combined Protection |
|-----------|---------------|-----------------|---------------------|
| Database data | ✅ Yes | ✅ Yes | ✅✅ Dual protection |
| Application code | ✅ Yes | ❌ No | ✅ Protected |
| Docker volumes | ✅ Yes | ❌ No | ✅ Protected |
| System config | ✅ Yes | ❌ No | ✅ Protected |
| SSL certificates | ✅ Yes | ❌ No | ✅ Protected |
| Logs | ✅ Yes | ❌ No | ✅ Protected |

**Analysis:** Database data has dual protection. Everything else protected by Linode backups.

---

## Retention Policies

### Linode Backups
- Retention controlled by Linode backup service
- Check Linode Cloud Manager for specific retention period
- Typically: Daily backups retained for X days (check your plan)

### Local Database Backups
- **Active:** Last 7 days in `/opt/restaurant-system/backups/`
- **Archived:** Older backups in `/opt/archives/old-backups/`
- **Cleanup:** Manual review of archives (not automatically deleted)

### Recommendation:
- Keep archived backups for **30-90 days**
- After 90 days, can be deleted if Linode backups cover the period
- For compliance: Check if you need longer retention (some industries require 7 years)

---

## Testing and Verification

### Monthly Testing Checklist

#### Test 1: Verify Linode Backups
```bash
# Via Linode Cloud Manager:
1. Log into Linode Cloud Manager
2. Navigate to Backups tab
3. Verify recent backups exist
4. Check backup dates and sizes
```

#### Test 2: Verify Local Database Backups
```bash
# Check backup files exist
ls -lh /opt/restaurant-system/backups/

# Verify backups are current (today or yesterday)
ls -lt /opt/restaurant-system/backups/ | head -10

# Check backup file sizes (should be ~50KB-4MB per file)
du -h /opt/restaurant-system/backups/*.sql.gz
```

#### Test 3: Test Database Restore (Non-Production)
```bash
# Create test database
docker exec inventory-db psql -U inventory_user -c "CREATE DATABASE inventory_test;"

# Restore to test database
LATEST_BACKUP=$(ls -t /opt/restaurant-system/backups/inventory_db_*.sql.gz | head -1)
gunzip < $LATEST_BACKUP | docker exec -i inventory-db psql -U inventory_user -d inventory_test

# Verify data
docker exec inventory-db psql -U inventory_user -d inventory_test -c "SELECT COUNT(*) FROM master_items;"

# Cleanup
docker exec inventory-db psql -U inventory_user -c "DROP DATABASE inventory_test;"
```

#### Test 4: Verify Backup Rotation
```bash
# Should have exactly 7 days of backups (14 files = 2 DBs × 7 days)
# Note: May vary slightly around rotation time
ls /opt/restaurant-system/backups/*.sql.gz | wc -l

# Check archived backups exist
ls /opt/archives/old-backups/ | wc -l
```

---

## Monitoring and Alerts

### Current Monitoring

#### Health Check (every 15 minutes)
```bash
tail -f /opt/restaurant-system/logs/health_check.log
```

#### Backup Log
```bash
tail -f /opt/restaurant-system/logs/backup.log
```

#### Check for Backup Failures
```bash
grep -i "error\|fail" /opt/restaurant-system/logs/backup.log | tail -10
```

### Recommended Alerts (Future Enhancement)

1. **Backup failure alert** - Email if backup_databases.sh fails
2. **Disk space alert** - Warning if < 10GB free space
3. **Rotation failure** - Alert if rotation script fails
4. **Linode backup check** - Weekly verification Linode backups are current

---

## Cost Analysis

### Current Costs

| Item | Cost | Notes |
|------|------|-------|
| Linode Backups | Included or $X/month | Check your Linode plan |
| Local Storage | $0 (uses server disk) | ~20MB for 7 days of backups |
| Scripts/Automation | $0 (implemented) | No additional cost |
| **Total** | **$X/month** | Linode backup service cost only |

### Optional S3 Enhancement
- **Cost:** ~$2/month
- **Benefit:** Additional off-site copy of database dumps
- **Priority:** LOW (already have Linode backups)
- **When to consider:** If need database-level backups stored separately from Linode

---

## Disaster Recovery Capabilities

### Current RTO/RPO

| Scenario | RTO (Recovery Time) | RPO (Data Loss) |
|----------|-------------------|-----------------|
| Complete server failure | 1-2 hours | Up to 24 hours |
| Single database failure | 15-30 minutes | Up to 24 hours |
| Accidental data deletion | 15-30 minutes | Up to 24 hours |
| Infrastructure failure | 1-2 hours | Up to 24 hours |

### Improving RTO/RPO

**To reduce RPO (data loss window):**
- Increase backup frequency (e.g., every 6 hours instead of daily)
- Implement database replication (real-time standby)
- Add transaction log shipping

**Current RPO is acceptable for most restaurant operations** - losing up to 24 hours of data would require manual re-entry but is survivable.

---

## Compliance Considerations

### Data Retention Requirements

**Check if your industry requires:**
- PCI-DSS (payment card data): Typically 1 year
- SOX (if applicable): 7 years
- GDPR (if handling EU data): Right to deletion (don't over-retain)
- State laws: Varies by state

**Recommendation:** Consult with legal/compliance team for specific retention requirements.

---

## Security

### Backup Security Measures

✅ **Encryption at rest:**
- Linode backups are encrypted by Linode
- Local backups stored on encrypted filesystem (if enabled)

✅ **Access control:**
- Backup files: root-only access (600 permissions on scripts, 644 on files)
- Linode backups: Linode Cloud Manager login (MFA recommended)

✅ **Secure deletion:**
- Rotation script moves files (doesn't delete immediately)
- Archived files retained for review period

⚠️ **Future enhancement:**
- Encrypt backup files before storage (gpg encryption)
- Separate backup user with limited permissions

---

## Quick Reference Commands

### View Active Backups
```bash
ls -lh /opt/restaurant-system/backups/
```

### View Archived Backups
```bash
ls -lh /opt/archives/old-backups/
```

### Manual Backup (Emergency)
```bash
/opt/restaurant-system/scripts/backup_databases.sh
```

### Manual Rotation
```bash
/opt/restaurant-system/scripts/rotate-backups.sh
```

### Check Cron Schedule
```bash
crontab -l | grep backup
```

### View Backup Logs
```bash
tail -50 /opt/restaurant-system/logs/backup.log
```

### Calculate Backup Sizes
```bash
# Active backups
du -sh /opt/restaurant-system/backups/

# Archived backups
du -sh /opt/archives/old-backups/

# Total
du -sh /opt/restaurant-system/backups/ /opt/archives/old-backups/
```

---

## Summary

### ✅ Current Backup Status: EXCELLENT

**Strengths:**
1. ✅ **Multi-layer protection** - Linode + Local database backups
2. ✅ **Automated daily backups** - No manual intervention required
3. ✅ **Automated rotation** - Prevents disk space issues
4. ✅ **Off-site protection** - Linode backups stored separately
5. ✅ **Fast recovery** - Multiple recovery options
6. ✅ **Cost-effective** - Using existing Linode service

**What's Protected:**
- ✅ Complete server (Linode backups)
- ✅ All databases (local backups)
- ✅ Application code and configurations
- ✅ Docker volumes and containers
- ✅ System files and certificates

**Recovery Capabilities:**
- ✅ Full server restoration
- ✅ Individual database restoration
- ✅ Point-in-time recovery
- ✅ Multiple restore points (7 days local + Linode retention)

### Next Actions: OPTIONAL ENHANCEMENTS ONLY

All critical backup infrastructure is in place. The following are optional enhancements:

**Priority: LOW**
- [ ] Add S3 backups for extra redundancy (~$2/month)
- [ ] Implement backup monitoring/alerts
- [ ] Test Linode restore procedure (practice drill)
- [ ] Document database-specific recovery procedures
- [ ] Review retention policy for compliance requirements

**Priority: MEDIUM**
- [ ] Monthly backup restore test (verify backups work)
- [ ] Quarterly Linode backup verification
- [ ] Review and clean archived backups older than 90 days

---

## Related Documentation

- [Cleanup Summary](CLEANUP_SUMMARY_OCT31.md) - October 31, 2025 cleanup actions
- [S3 Implementation Plan](S3_BACKUP_IMPLEMENTATION_PLAN.md) - Optional S3 enhancement
- [README.md](../README.md) - Main system documentation
- [SYSTEM_DOCUMENTATION.md](../SYSTEM_DOCUMENTATION.md) - System architecture

---

**Document Version:** 1.0
**Last Review:** October 31, 2025
**Next Review:** December 1, 2025
