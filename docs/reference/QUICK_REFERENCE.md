# SW Restaurant Management System - Quick Reference Card

**Print this page and keep it handy!**

---

## 🌐 System Access

**Portal:** https://rm.swhgrp.com
**Inventory:** https://rm.swhgrp.com/inventory/
**Accounting:** https://rm.swhgrp.com/accounting/

---

## 👥 Support Contact

**Email:** admin@swhgrp.com
**Subject Line:** "Restaurant System Issue"

---

## 🚨 Emergency Commands

**Server Access:**
```bash
ssh root@172.233.172.92
cd /opt/restaurant-system
```

**Check Status:**
```bash
docker compose ps
```

**Restart Everything:**
```bash
docker compose restart
```

**View Logs:**
```bash
docker compose logs -f inventory-app
```

---

## 🔍 Health Checks

**Quick Health Check:**
```bash
/opt/restaurant-system/scripts/health_check.sh
```

**POS Sync Status:**
```bash
/opt/restaurant-system/scripts/check_pos_sync.sh
```

**Test Email Alerts:**
```bash
/opt/restaurant-system/scripts/test_email_alert.sh
```

---

## 💾 Backups

**Location:** `/opt/restaurant-system/backups/`
**Schedule:** Daily at 2:00 AM
**Retention:** 7 days

**List Backups:**
```bash
ls -lh /opt/restaurant-system/backups/
```

**Manual Backup:**
```bash
/opt/restaurant-system/scripts/backup_databases.sh
```

---

## ⚙️ Common Tasks

**Restart Inventory:**
```bash
docker compose restart inventory-app
```

**Restart Accounting:**
```bash
docker compose restart accounting-app
```

**Check Disk Space:**
```bash
df -h /opt/restaurant-system
```

**View Recent Errors:**
```bash
docker compose logs --tail=50 | grep -i error
```

---

## 📊 Monitoring

**What's Being Monitored:**
- Container health (every 5 min)
- Database connectivity (every 5 min)
- Disk space (every 5 min)
- POS sync (every 10 min)

**Alerts Sent To:** admin@swhgrp.com

---

## 🔐 SSL Certificate

**Domain:** rm.swhgrp.com
**Provider:** Let's Encrypt
**Expires:** January 13, 2026
**Auto-Renewal:** ✅ Enabled

**Test Renewal:**
```bash
sudo certbot renew --dry-run
```

---

## 📍 Restaurant Locations

1. Seaside Grill - Vero Beach
2. The Nest Eatery - Boca Raton
3. SW Grill - Boca Raton
4. Okee Grill - West Palm Beach
5. Park Bistro - Wellington
6. Links Grill - Boynton Beach

---

## 🔑 User Roles

- **Admin:** Full access, all locations
- **Manager:** Assigned locations, most features
- **Staff:** Limited access, assigned locations

---

## 📝 Important Files

```
/opt/restaurant-system/
├── backups/              # Database backups (7 days)
├── logs/                 # System logs
├── scripts/              # Maintenance scripts
├── OPERATIONS_GUIDE.md   # Full documentation
└── docker-compose.yml    # Service configuration
```

---

## 🆘 Troubleshooting Quick Steps

**Website Down:**
1. `docker compose ps` - Check containers
2. `docker compose restart nginx-proxy` - Restart nginx
3. Check https://rm.swhgrp.com

**Login Issues:**
1. Verify user is active (Settings → Users)
2. `docker compose logs inventory-app --tail=50`
3. `docker compose restart inventory-app`

**POS Not Syncing:**
1. `/opt/restaurant-system/scripts/check_pos_sync.sh`
2. Check Settings → POS Integration
3. Manually trigger sync in web interface

**Database Issues:**
1. `docker compose ps inventory-db`
2. `docker compose restart inventory-db`
3. Check backups if needed

---

## 📧 Email Alerts Mean...

🚨 **Critical** - Container stopped, database down
⚠️ **Warning** - Disk/memory high, sync issues
✅ **Info** - Test email, successful operation

**Action:** Check email, run health check, investigate logs

---

## 💡 Pro Tips

- Keep this card near your desk
- Bookmark https://rm.swhgrp.com
- Check email alerts daily
- Run health check weekly
- Test backups monthly
- Read OPERATIONS_GUIDE.md for details

---

**System Version:** 2.1
**Last Updated:** October 15, 2025
**Full Guide:** `/opt/restaurant-system/OPERATIONS_GUIDE.md`
