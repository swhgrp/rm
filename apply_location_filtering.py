#!/usr/bin/env python3
"""
Script to apply location-based filtering to all endpoints that need it.

Endpoints that NEED location filtering:
- Inventory (counts, movements)
- Storage areas
- Invoices
- Transfers
- Waste logs
- Reports
- Dashboard (already done)
- Locations (already done)

Endpoints that DON'T need location filtering (global resources):
- Vendor items
- Master items
- Recipes
- Units of measure
- Categories
- Vendors (but invoices filtered)
"""

import sys
import os

# List of files that need location filtering
FILES_TO_UPDATE = [
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/inventory.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/storage_areas.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/invoices.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/transfers.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/waste.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/reports.py",
    "inventory/src/restaurant_inventory/api/api_v1/endpoints/count_sessions.py",
]

print("Files that need location filtering:")
for f in FILES_TO_UPDATE:
    full_path = f"/opt/restaurant-system/{f}"
    exists = "✓" if os.path.exists(full_path) else "✗"
    print(f"  {exists} {f}")

print("\nThese files need to be updated to use filter_by_user_locations()")
print("Manual review recommended for each endpoint")
