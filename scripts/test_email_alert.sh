#!/bin/bash
#
# Test Email Alert System
# Sends a test email to verify email configuration is working
#

echo "Testing email alert system..."
echo ""

# Email configuration
ALERT_EMAIL="admin@swhgrp.com"
SMTP_HOST="smtp.swhgrp.com"
SMTP_PORT="2555"
SMTP_USER="admin"
SMTP_FROM="admin@swhgrp.com"

# Send test email
docker exec inventory-app python3 -c "
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

msg = MIMEMultipart('alternative')
msg['Subject'] = '✅ Test Email - SW Restaurant Management System'
msg['From'] = '${SMTP_FROM}'
msg['To'] = '${ALERT_EMAIL}'

html = '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .success { background-color: #d1ecf1; border-left: 4px solid #0dcaf0; padding: 15px; margin: 20px 0; }
        pre { background-color: #f4f4f4; padding: 10px; border-radius: 4px; }
    </style>
</head>
<body>
    <h2>✅ Email Alert System Test</h2>
    <div class='success'>
        <strong>Test Time:</strong> $(date '+%Y-%m-%d %H:%M:%S')<br>
        <strong>Server:</strong> $(hostname)<br>
        <strong>Status:</strong> Email system is working correctly
    </div>
    <h3>What This Means:</h3>
    <ul>
        <li>✅ SMTP configuration is correct</li>
        <li>✅ Email alerts are enabled and functional</li>
        <li>✅ You will receive notifications when system issues occur</li>
    </ul>
    <h3>Alert Triggers:</h3>
    <pre>
- Docker containers stop or fail health checks
- Database connectivity issues
- Disk space exceeds 85%
- Memory usage exceeds 90%
- High error rate (>10 errors in 5 minutes)
- POS sync failures or scheduler issues
    </pre>
    <hr>
    <p style='font-size: 12px; color: #666;'>
        This is a test email from SW Restaurant Management System<br>
        Monitoring runs every 5 minutes automatically
    </p>
</body>
</html>
'''
msg.attach(MIMEText(html, 'html'))

try:
    print('Connecting to SMTP server...')
    server = smtplib.SMTP('${SMTP_HOST}', ${SMTP_PORT})
    print('Logging in...')
    server.login('${SMTP_USER}', 'Galveston34-')
    print('Sending message...')
    server.send_message(msg)
    server.quit()
    print('✅ Test email sent successfully to ${ALERT_EMAIL}')
    exit(0)
except Exception as e:
    print(f'❌ Failed to send email: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Email alert system is working!"
    echo "Check your inbox at $ALERT_EMAIL"
    exit 0
else
    echo ""
    echo "❌ Email alert system failed"
    echo "Please check SMTP configuration"
    exit 1
fi
