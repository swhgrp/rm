#!/bin/bash
# Update all containers with new timezone configuration
# Restarts one at a time to minimize downtime

echo "Updating timezone configuration for all containers..."
echo "This will restart containers one at a time."
echo ""

cd /opt/restaurant-system

# Restart services in order (dependencies first)
SERVICES=(
    "inventory-redis"
    "inventory-db"
    "accounting-db"
    "hr-db"
    "events-redis"
    "events-db"
    "hub-db"
    "inventory-app"
    "accounting-app"
    "hr-app"
    "events-app"
    "integration-hub"
    "files-app"
    "portal-app"
    "nginx"
)

for service in "${SERVICES[@]}"; do
    echo "Restarting $service..."
    docker compose restart "$service"
    sleep 3
done

echo ""
echo "All services restarted with America/New_York timezone"
echo "Verifying timezone..."
docker exec portal-app date
