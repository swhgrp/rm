# SW Restaurant Management System - Operations Guide

**Last Updated:** October 15, 2025
**Version:** 2.1
**Support Contact:** admin@swhgrp.com

---

## 📋 Table of Contents

1. [Quick Reference](#quick-reference)
2. [System Access](#system-access)
3. [User Management](#user-management)
4. [Monitoring & Alerts](#monitoring--alerts)
5. [Backups & Recovery](#backups--recovery)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance Tasks](#maintenance-tasks)
8. [Emergency Procedures](#emergency-procedures)

---

## Quick Reference

### System URLs

| Service | URL | Purpose |
|---------|-----|---------|
| **Portal Home** | https://rm.swhgrp.com | Main entry point |
| **Inventory** | https://rm.swhgrp.com/inventory/ | Inventory management |
| **Accounting** | https://rm.swhgrp.com/accounting/ | Accounting system |

### Important Files & Locations

```
/opt/restaurant-system/          # Main system directory
├── backups/                      # Automated backups (7 days retention)
├── logs/                         # System logs
├── scripts/                      # Maintenance scripts
│   ├── backup_databases.sh       # Daily backup script
│   ├── health_check.sh           # Health monitoring
│   ├── check_pos_sync.sh         # POS sync monitoring
│   └── test_email_alert.sh       # Email system test
└── docker-compose.yml            # Service configuration
```

### Key Commands

```bash
# Check system status
cd /opt/restaurant-system
docker compose ps

# View logs
docker compose logs -f inventory-app
docker compose logs -f accounting-app

# Restart a service
docker compose restart inventory-app

# Run health check manually
/opt/restaurant-system/scripts/health_check.sh

# Check POS sync status
/opt/restaurant-system/scripts/check_pos_sync.sh

# Test email alerts
/opt/restaurant-system/scripts/test_email_alert.sh
```

---

## System Access

### For End Users

**Access the System:**
1. Go to https://rm.swhgrp.com
2. Click on the module you need (Inventory or Accounting)
3. Log in with your username and password

**First-Time Login:**
- You'll receive an email invitation with a setup link
- Click the link to set your password
- Link expires in 24 hours
- Contact admin if link expires

**Supported Browsers:**
- Chrome (recommended)
- Firefox
- Safari
- Edge

**Mobile Access:**
- Fully responsive design
- Works on phones and tablets
- Best experience on tablets for inventory counts

### User Roles

| Role | Permissions | Typical Use |
|------|-------------|-------------|
| **Admin** | Full access to all locations, all features | System administrators, owners |
| **Manager** | Access to assigned locations, most features | Restaurant managers, supervisors |
| **Staff** | Limited access, assigned locations only | Staff members, inventory counters |

### Locations

1. **Seaside Grill** - Vero Beach, FL 32963
2. **The Nest Eatery** - Boca Raton, FL 33498
3. **SW Grill** - Boca Raton, FL 33487
4. **Okee Grill** - West Palm Beach, FL 33413
5. **Park Bistro** - Wellington, FL 33467
6. **Links Grill** - Boynton Beach, FL 33472

---

## User Management

### Adding New Users (Admin Only)

**Via Web Interface:**
1. Log in as Admin
2. Go to **Settings** → **Users** tab
3. Click **"Add User"**
4. Fill in user details:
   - Full Name
   - Email (where invitation will be sent)
   - Username
   - Role (Admin/Manager/Staff)
5. Assign locations (if not Admin)
6. Click **"Create User"**
7. User receives email invitation with setup link

**What the User Receives:**
- Email from admin@swhgrp.com
- Subject: "Welcome to SW Hospitality Group Inventory System"
- Contains secure setup link (expires in 24 hours)
- Instructions to set their password

### Modifying Users

**Change Role:**
1. Settings → Users tab
2. Click edit icon next to user
3. Change role
4. Save changes

**Assign/Remove Locations:**
1. Settings → Users tab
2. Click "Manage Locations" icon
3. Check/uncheck locations
4. Save changes

**Deactivate User:**
1. Settings → Users tab
2. Click edit icon
3. Uncheck "Active" status
4. User can no longer log in (data preserved)

### Password Reset

**User Forgot Password:**
1. User contacts admin
2. Admin goes to Settings → Users
3. Click "Reset Password" for that user
4. User receives email with reset link
5. Link expires in 24 hours

---

## Monitoring & Alerts

### Automated Monitoring

**What's Being Monitored:**
- ✅ Docker container health (every 5 minutes)
- ✅ Database connectivity (every 5 minutes)
- ✅ Disk space usage (every 5 minutes)
- ✅ Memory usage (every 5 minutes)
- ✅ Application errors (every 5 minutes)
- ✅ POS sync status (every 10 minutes)

**Who Gets Alerts:**
- Email: admin@swhgrp.com
- Format: HTML email with details

### Email Alerts

**You'll Receive Alerts When:**
- 🚨 Docker service stops
- 🚨 Any container stops or crashes
- 🚨 Database connection fails
- 🚨 Redis connection fails
- ⚠️ Disk space exceeds 85%
- ⚠️ Memory usage exceeds 90%
- ⚠️ High error rate (>10 errors in 5 minutes)
- ⚠️ POS sync failures
- ⚠️ Background scheduler issues

**Alert Email Example:**
```
Subject: ⚠️ System Alert: SW Restaurant Management System

Alert: Container inventory-db is not running
Time: 2025-10-15 14:30:00
Server: restaurant-platform
```

### Checking System Health Manually

**Quick Health Check:**
```bash
cd /opt/restaurant-system
docker compose ps
```

Expected output: All services "Up" and "healthy"

**Detailed Health Check:**
```bash
/opt/restaurant-system/scripts/health_check.sh
```

**View Recent Logs:**
```bash
# All services
docker compose logs --tail=50

# Specific service
docker compose logs --tail=50 inventory-app
docker compose logs --tail=50 accounting-app

# Follow logs in real-time
docker compose logs -f inventory-app
```

**Check Disk Space:**
```bash
df -h /opt/restaurant-system
```

**Check Database Sizes:**
```bash
docker compose exec inventory-db psql -U inventory_user -d inventory_db -c "SELECT pg_size_pretty(pg_database_size('inventory_db'));"
docker compose exec accounting-db psql -U accounting_user -d accounting_db -c "SELECT pg_size_pretty(pg_database_size('accounting_db'));"
```

---

## Backups & Recovery

### Automated Backups

**Schedule:**
- Runs daily at 2:00 AM
- Backs up both inventory and accounting databases
- Retention: 7 days (older backups automatically deleted)

**Backup Location:**
```
/opt/restaurant-system/backups/
├── inventory_backup_YYYYMMDD.sql
└── accounting_backup_YYYYMMDD.sql
```

**Verify Backups:**
```bash
ls -lh /opt/restaurant-system/backups/
```

You should see recent backups with today's date.

**Check Backup Logs:**
```bash
tail -50 /opt/restaurant-system/logs/backup.log
```

### Manual Backup

**Create Backup Now:**
```bash
/opt/restaurant-system/scripts/backup_databases.sh
```

**Backup Entire System:**
```bash
cd /opt
sudo tar -czf restaurant-system-backup-$(date +%Y%m%d).tar.gz restaurant-system/
```

### Restore from Backup

**⚠️ IMPORTANT: Only perform restores if absolutely necessary!**

**Restore Inventory Database:**
```bash
cd /opt/restaurant-system

# Stop the application
docker compose stop inventory-app

# Restore database
cat backups/inventory_backup_YYYYMMDD.sql | \
    docker compose exec -T inventory-db \
    psql -U inventory_user -d inventory_db

# Start the application
docker compose start inventory-app
```

**Restore Accounting Database:**
```bash
cd /opt/restaurant-system

# Stop the application
docker compose stop accounting-app

# Restore database
cat backups/accounting_backup_YYYYMMDD.sql | \
    docker compose exec -T accounting-db \
    psql -U accounting_user -d accounting_db

# Start the application
docker compose start accounting-app
```

**Verify Restore:**
1. Log in to the system
2. Check that your data is present
3. Test key functionality

---

## Troubleshooting

### Common Issues

#### "Cannot connect to the system"

**Symptoms:** Website not loading, timeout errors

**Steps:**
1. Check if Docker is running:
   ```bash
   systemctl status docker
   ```
2. Check if containers are running:
   ```bash
   cd /opt/restaurant-system
   docker compose ps
   ```
3. Check nginx logs:
   ```bash
   docker compose logs nginx-proxy --tail=50
   ```
4. Restart nginx if needed:
   ```bash
   docker compose restart nginx-proxy
   ```

#### "Login not working"

**Symptoms:** "Invalid credentials" or "Network error"

**Steps:**
1. Verify user account exists and is active (Admin checks Settings → Users)
2. Check inventory app logs:
   ```bash
   docker compose logs inventory-app --tail=50 | grep -i error
   ```
3. Check database connectivity:
   ```bash
   docker compose exec inventory-db psql -U inventory_user -d inventory_db -c "SELECT 1;"
   ```
4. Restart inventory app:
   ```bash
   docker compose restart inventory-app
   ```

#### "POS sync not working"

**Symptoms:** Sales not appearing, old data

**Steps:**
1. Run POS sync check:
   ```bash
   /opt/restaurant-system/scripts/check_pos_sync.sh
   ```
2. Check POS configuration in web interface:
   - Settings → POS Integration tab
   - Verify API keys are correct
   - Check last sync time
3. Manually trigger sync from web interface
4. Check logs for errors:
   ```bash
   docker compose logs inventory-app | grep -i "sync\|clover"
   ```

#### "Data not saving" or "500 errors"

**Symptoms:** Forms not submitting, error messages

**Steps:**
1. Check application logs:
   ```bash
   docker compose logs inventory-app --tail=100
   ```
2. Check database space:
   ```bash
   df -h
   ```
3. Check database connectivity:
   ```bash
   docker compose ps inventory-db
   ```
4. Restart the application:
   ```bash
   docker compose restart inventory-app
   ```

#### "Email notifications not arriving"

**Steps:**
1. Test email system:
   ```bash
   /opt/restaurant-system/scripts/test_email_alert.sh
   ```
2. Check spam folder
3. Verify email in Settings → Users
4. Check SMTP logs:
   ```bash
   docker compose logs inventory-app | grep -i smtp
   ```

#### "Slow performance"

**Steps:**
1. Check system resources:
   ```bash
   docker stats
   free -h
   df -h
   ```
2. Check for high CPU containers
3. Restart Redis cache:
   ```bash
   docker compose restart inventory-redis
   ```
4. Clear browser cache
5. Check database sizes (may need optimization)

### Getting Help

**When contacting support, provide:**
1. What you were trying to do
2. Error message (exact text or screenshot)
3. Your username and role
4. Time when issue occurred
5. Browser you're using
6. Output of health check:
   ```bash
   /opt/restaurant-system/scripts/health_check.sh
   ```

**Support Contact:**
- Email: admin@swhgrp.com
- Include "Restaurant System Issue" in subject line

---

## Maintenance Tasks

### Daily

- ✅ **Automated:** Backups run at 2 AM
- ✅ **Automated:** Health checks every 5 minutes
- ✅ **Automated:** POS sync every 10 minutes

**No daily manual tasks required!**

### Weekly

**Check Email Alerts:**
- Review any alert emails received
- Investigate and resolve any issues

**Verify Backups:**
```bash
ls -lh /opt/restaurant-system/backups/
```
Should see backups from last 7 days.

**Review Audit Log:**
- Log in as Admin
- Settings → Audit Log tab
- Review recent critical changes

### Monthly

**Review System Performance:**
```bash
# Check disk space
df -h /opt/restaurant-system

# Check database sizes
/opt/restaurant-system/scripts/health_check.sh

# Review resource usage
docker stats --no-stream
```

**Clean Up Old Logs (if needed):**
```bash
# Logs older than 30 days
find /opt/restaurant-system/logs -name "*.log" -mtime +30 -delete
```

**Review User Accounts:**
- Deactivate users who left
- Update locations for managers
- Verify role assignments

### Quarterly

**SSL Certificate Check:**
```bash
sudo certbot certificates
```

Certificate should auto-renew, but verify expiration date is > 30 days away.

**Test Disaster Recovery:**
1. Create manual backup
2. Document restore procedure
3. Test restore in development if available

**Security Review:**
- Review audit logs for suspicious activity
- Update passwords if needed
- Review user access levels

**Performance Optimization:**
- Review database sizes
- Check for unused data
- Consider archiving old records

---

## Emergency Procedures

### Complete System Down

**If entire system is unresponsive:**

1. **Check Server Status:**
   ```bash
   ping 172.233.172.92
   ssh root@172.233.172.92
   ```

2. **Restart All Services:**
   ```bash
   cd /opt/restaurant-system
   docker compose down
   docker compose up -d
   ```

3. **Wait 2 minutes, then check:**
   ```bash
   docker compose ps
   ```

4. **Test access:** https://rm.swhgrp.com

5. **If still down, check logs:**
   ```bash
   docker compose logs --tail=100
   ```

6. **Contact hosting provider (Linode)** if server is unreachable

### Database Corruption

**Symptoms:** Cannot start database, data errors

1. **Stop application:**
   ```bash
   docker compose stop inventory-app accounting-app
   ```

2. **Restore from latest backup** (see Restore section above)

3. **Start applications:**
   ```bash
   docker compose start inventory-app accounting-app
   ```

4. **Verify data integrity**

### Security Breach Suspected

**Immediate Actions:**

1. **Change all passwords immediately**
2. **Review audit logs:**
   - Settings → Audit Log
   - Look for unauthorized changes
3. **Deactivate suspicious user accounts**
4. **Check server access logs:**
   ```bash
   docker compose logs nginx-proxy | grep -v "200\|304"
   ```
5. **Review recent user activity**
6. **Contact security team**

### Data Loss / Accidental Deletion

**For recent deletions:**
1. Check audit log for what was deleted and when
2. Identify the most recent backup before deletion
3. Restore from backup (see Restore section)

**For critical data:**
- Backups go back 7 days
- Older backups may be on Linode backup service (if enabled)

---

## System Information

### Technical Specifications

**Server:**
- Provider: Linode
- IP Address: 172.233.172.92
- Domain: rm.swhgrp.com
- OS: Ubuntu 22.04 LTS
- Docker: Latest version

**Services Running:**
- Inventory Management (FastAPI/Python)
- Accounting System (FastAPI/Python)
- PostgreSQL 15 (2 databases)
- Redis 7 (caching)
- Nginx (reverse proxy)
- Certbot (SSL certificates)

**SSL Certificate:**
- Provider: Let's Encrypt
- Expires: January 13, 2026
- Auto-renewal: Enabled

**Integrations:**
- POS System: Clover
- Email: SMTP (smtp.swhgrp.com)

### Scheduled Tasks (Cron)

```bash
# View all scheduled tasks
crontab -l
```

**Current Schedule:**
- `0 2 * * *` - Daily backups at 2:00 AM
- `*/5 * * * *` - Health checks every 5 minutes
- `*/10 * * * *` - POS sync check every 10 minutes

### File Permissions

**Important directories should be owned by root:**
```bash
ls -la /opt/restaurant-system
```

**Backup directory should have write permissions:**
```bash
ls -la /opt/restaurant-system/backups
```

---

## Appendix

### Useful Commands Reference

**Docker Management:**
```bash
# View all containers
docker compose ps

# View resource usage
docker stats

# Restart all services
docker compose restart

# Stop all services
docker compose stop

# Start all services
docker compose start

# View logs (all services)
docker compose logs -f

# View logs (specific service)
docker compose logs -f inventory-app
```

**Database Access:**
```bash
# Inventory database
docker compose exec inventory-db psql -U inventory_user -d inventory_db

# Accounting database
docker compose exec accounting-db psql -U accounting_user -d accounting_db

# Query from command line
docker compose exec -T inventory-db psql -U inventory_user -d inventory_db -c "SELECT COUNT(*) FROM users;"
```

**System Monitoring:**
```bash
# Disk space
df -h

# Memory usage
free -h

# System load
uptime

# Network connections
netstat -tulpn | grep :80
netstat -tulpn | grep :443
```

### Contact Information

**System Administrator:**
- Email: admin@swhgrp.com
- Emergency: [Add phone number]

**Hosting Provider:**
- Linode Support: https://www.linode.com/support/
- Support Phone: [Add if available]

**Domain Registrar:**
- Domain: swhgrp.com
- Registrar: [Add registrar name]

**Email Provider:**
- SMTP Host: smtp.swhgrp.com
- Support: [Add email support contact]

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-15 | 2.1 | Added HTTPS, email alerts, operations guide |
| 2025-10-14 | 2.0 | Portal implementation, automation |
| 2025-10-13 | 1.5 | Microservices restructure |
| 2025-10-01 | 1.0 | Initial production deployment |

---

**Document Version:** 2.1
**Last Updated:** October 15, 2025
**Next Review:** January 15, 2026

---

*This document is maintained by the system administrator. Please report any errors or suggested improvements to admin@swhgrp.com.*
