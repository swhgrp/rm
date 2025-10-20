#!/bin/bash

echo "=== Dashboard Diagnostic Script ==="
echo ""

echo "1. Testing Dashboard HTML Endpoint..."
DASH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/dashboard)
if [ "$DASH_STATUS" = "200" ]; then
    echo "   ✓ Dashboard HTML loads ($DASH_STATUS)"
else
    echo "   ✗ Dashboard HTML issue ($DASH_STATUS)"
fi
echo ""

echo "2. Testing Login Endpoint..."
LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/login)
if [ "$LOGIN_STATUS" = "200" ]; then
    echo "   ✓ Login page loads ($LOGIN_STATUS)"
else
    echo "   ✗ Login page issue ($LOGIN_STATUS)"
fi
echo ""

echo "3. Testing Static Files..."
AUTH_JS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/js/auth.js)
MAIN_JS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/static/js/main.js)
if [ "$AUTH_JS" = "200" ] && [ "$MAIN_JS" = "200" ]; then
    echo "   ✓ JavaScript files load (auth: $AUTH_JS, main: $MAIN_JS)"
else
    echo "   ✗ JavaScript file issue (auth: $AUTH_JS, main: $MAIN_JS)"
fi
echo ""

echo "4. Testing API Endpoint (without auth - should fail)..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/dashboard/analytics)
if [ "$API_STATUS" = "403" ] || [ "$API_STATUS" = "401" ]; then
    echo "   ✓ API correctly requires authentication ($API_STATUS)"
else
    echo "   ? API returned unexpected status: $API_STATUS"
fi
echo ""

echo "5. Checking inventory-app service logs for errors..."
docker compose logs inventory-app --tail=20 | grep -i "error\|exception\|traceback" | head -10
if [ $? -ne 0 ]; then
    echo "   ✓ No recent errors in logs"
fi
echo ""

echo "6. Checking database connectivity..."
DB_CHECK=$(docker compose exec -T inventory-db psql -U inventory_user -d inventory_db -c "SELECT COUNT(*) FROM users;" 2>&1 | grep -E "^\s+[0-9]+")
if [ $? -eq 0 ]; then
    echo "   ✓ Database connected -$DB_CHECK users"
else
    echo "   ✗ Database connection issue"
fi
echo ""

echo "=== Next Steps ==="
echo "1. Open your browser to: http://172.233.172.92/dashboard"
echo "2. Open Developer Tools (F12)"
echo "3. Check the Console tab for JavaScript errors"
echo "4. Check the Network tab to see if API calls are failing"
echo "5. Verify you're logged in (check for access_token in localStorage)"
