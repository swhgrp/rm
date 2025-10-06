#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/restaurant-inventory/src')

from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.models.inventory import Inventory
from restaurant_inventory.models.storage_area import StorageAreaItem
from sqlalchemy import and_

def main():
    db = SessionLocal()

    try:
        # Get all inventory items that have a storage area assigned
        inventory_items = db.query(Inventory).filter(Inventory.storage_area_id.isnot(None)).all()

        added_count = 0
        for inv in inventory_items:
            # Check if this item is already in storage_area_items
            existing = db.query(StorageAreaItem).filter(
                and_(
                    StorageAreaItem.storage_area_id == inv.storage_area_id,
                    StorageAreaItem.master_item_id == inv.master_item_id
                )
            ).first()

            if not existing:
                # Get max display order for this storage area
                max_order = db.query(StorageAreaItem).filter(
                    StorageAreaItem.storage_area_id == inv.storage_area_id
                ).count()

                # Add to storage area items
                new_item = StorageAreaItem(
                    storage_area_id=inv.storage_area_id,
                    master_item_id=inv.master_item_id,
                    display_order=max_order + 1
                )
                db.add(new_item)
                added_count += 1
                print(f"Added item {inv.master_item_id} to storage area {inv.storage_area_id}")

        db.commit()
        print(f'\nTotal: Added {added_count} items to storage area expected items lists')

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    main()
