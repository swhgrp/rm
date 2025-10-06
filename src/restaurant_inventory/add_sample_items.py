#!/usr/bin/env python3

import sys
sys.path.append('/app/src')

from sqlalchemy.orm import Session
from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.models.item import MasterItem
from decimal import Decimal
from datetime import datetime

def add_sample_items():
    """Add sample master items to the database"""
    db = SessionLocal()
    
    try:
        # Check if items already exist
        existing_count = db.query(MasterItem).count()
        if existing_count > 0:
            print(f"Database already has {existing_count} items. Skipping.")
            return
        
        # Create sample master items
        items = [
            MasterItem(
                name="Ground Beef 80/20",
                description="Fresh ground beef, 80% lean, 20% fat",
                category="Meat",
                unit_of_measure="lb",
                current_cost=Decimal("5.99"),
                average_cost=Decimal("5.85"),
                sku="BEEF-80-20",
                is_active=True
            ),
            MasterItem(
                name="Tomatoes - Roma",
                description="Fresh Roma tomatoes, perfect for sauce",
                category="Produce",
                unit_of_measure="lb",
                current_cost=Decimal("2.49"),
                average_cost=Decimal("2.35"),
                sku="TOM-ROMA",
                is_active=True
            ),
            MasterItem(
                name="Flour - All Purpose",
                description="All-purpose flour, 50lb bag",
                category="Dry Goods",
                unit_of_measure="50lb bag",
                current_cost=Decimal("18.99"),
                average_cost=Decimal("18.75"),
                sku="FLOUR-AP-50",
                is_active=True
            ),
            MasterItem(
                name="Olive Oil - Extra Virgin",
                description="Extra virgin olive oil, premium quality",
                category="Oils & Condiments",
                unit_of_measure="gallon",
                current_cost=Decimal("24.99"),
                average_cost=Decimal("24.50"),
                sku="OIL-OLIVE-EV",
                is_active=True
            ),
            MasterItem(
                name="Chicken Breast - Boneless",
                description="Fresh boneless, skinless chicken breast",
                category="Meat",
                unit_of_measure="lb",
                current_cost=Decimal("7.99"),
                average_cost=Decimal("7.85"),
                sku="CHICK-BREAST",
                is_active=True
            ),
            MasterItem(
                name="Mozzarella Cheese",
                description="Fresh mozzarella cheese, 5lb block",
                category="Dairy",
                unit_of_measure="5lb block",
                current_cost=Decimal("15.99"),
                average_cost=Decimal("15.75"),
                sku="CHEESE-MOZZ-5",
                is_active=True
            ),
            MasterItem(
                name="Pizza Dough Balls",
                description="Fresh pizza dough balls, 12oz each",
                category="Prepared Foods",
                unit_of_measure="each",
                current_cost=Decimal("1.25"),
                average_cost=Decimal("1.20"),
                sku="DOUGH-PIZZA-12",
                is_active=True
            )
        ]
        
        # Add to database
        for item in items:
            item.last_cost_update = datetime.now()
            db.add(item)
        
        db.commit()
        print(f"Successfully added {len(items)} sample master items!")
        
        # Print the items for verification
        for item in items:
            print(f"- {item.name} ({item.category}): ${item.current_cost}/{item.unit_of_measure}")
        
    except Exception as e:
        print(f"Error adding sample data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_sample_items()
