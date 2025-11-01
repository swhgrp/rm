#!/usr/bin/env python3
"""Seed script to add initial event packages"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy.orm import Session
import sys
import os

# Fix imports
sys.path.insert(0, '/app/src')
os.chdir('/app')

from events.core.database import SessionLocal
from events.models.event import EventPackage

def seed_packages():
    """Add initial event packages"""
    db: Session = SessionLocal()

    try:
        # Check if packages already exist
        existing = db.query(EventPackage).count()
        if existing > 0:
            print(f"✓ {existing} packages already exist. Skipping seed.")
            return

        packages = [
            {
                "name": "Elegant Wedding Package",
                "event_type": "Wedding",
                "price_components_json": {
                    "base_price": 5000.00,
                    "per_guest_price": 75.00,
                    "setup_fee": 500.00,
                    "overtime_rate": 200.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "Includes ceremony and reception setup, linens, centerpieces, and 4-hour service"
                }
            },
            {
                "name": "Premium Wedding Package",
                "event_type": "Wedding",
                "price_components_json": {
                    "base_price": 8000.00,
                    "per_guest_price": 95.00,
                    "setup_fee": 750.00,
                    "overtime_rate": 250.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "All-inclusive package with upgraded decor, premium bar service, and 5-hour service"
                }
            },
            {
                "name": "Corporate Meeting Package",
                "event_type": "Corporate Event",
                "price_components_json": {
                    "base_price": 2500.00,
                    "per_guest_price": 45.00,
                    "setup_fee": 300.00,
                    "overtime_rate": 150.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.18,
                    "description": "Includes AV equipment, refreshments, and meeting room setup"
                }
            },
            {
                "name": "Corporate Gala Package",
                "event_type": "Corporate Event",
                "price_components_json": {
                    "base_price": 6000.00,
                    "per_guest_price": 80.00,
                    "setup_fee": 600.00,
                    "overtime_rate": 200.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "Full evening event with cocktail hour, dinner service, and entertainment setup"
                }
            },
            {
                "name": "Birthday Celebration Package",
                "event_type": "Birthday Party",
                "price_components_json": {
                    "base_price": 1500.00,
                    "per_guest_price": 35.00,
                    "setup_fee": 200.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.18,
                    "description": "Includes party room, decorations, and 3-hour service"
                }
            },
            {
                "name": "Milestone Birthday Package",
                "event_type": "Birthday Party",
                "price_components_json": {
                    "base_price": 3000.00,
                    "per_guest_price": 50.00,
                    "setup_fee": 350.00,
                    "overtime_rate": 125.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "Premium package for milestone celebrations with upgraded menu and bar service"
                }
            },
            {
                "name": "Fundraiser Gala Package",
                "event_type": "Fundraiser",
                "price_components_json": {
                    "base_price": 4500.00,
                    "per_guest_price": 65.00,
                    "setup_fee": 450.00,
                    "overtime_rate": 175.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.18,
                    "description": "Includes staging for presentations, silent auction areas, and full dinner service"
                }
            },
            {
                "name": "Holiday Party Package",
                "event_type": "Holiday Party",
                "price_components_json": {
                    "base_price": 3500.00,
                    "per_guest_price": 55.00,
                    "setup_fee": 400.00,
                    "overtime_rate": 150.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "Festive decorations, cocktail hour, buffet dinner, and 4-hour service"
                }
            },
            {
                "name": "Graduation Celebration Package",
                "event_type": "Graduation",
                "price_components_json": {
                    "base_price": 2000.00,
                    "per_guest_price": 40.00,
                    "setup_fee": 250.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.18,
                    "description": "Includes ceremony seating, reception space, and 3-hour service"
                }
            },
            {
                "name": "Anniversary Dinner Package",
                "event_type": "Anniversary",
                "price_components_json": {
                    "base_price": 2500.00,
                    "per_guest_price": 60.00,
                    "setup_fee": 300.00,
                    "tax_rate": 0.08,
                    "gratuity_rate": 0.20,
                    "description": "Elegant dinner service with premium menu options and romantic ambiance"
                }
            }
        ]

        for pkg_data in packages:
            package = EventPackage(**pkg_data)
            db.add(package)

        db.commit()
        print(f"✓ Successfully seeded {len(packages)} event packages")

        # Print summary
        print("\nPackages by Event Type:")
        from sqlalchemy import func
        summary = db.query(
            EventPackage.event_type,
            func.count(EventPackage.id).label('count')
        ).group_by(EventPackage.event_type).all()

        for event_type, count in summary:
            print(f"  - {event_type}: {count} package(s)")

    except Exception as e:
        print(f"✗ Error seeding packages: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding event packages...")
    seed_packages()
    print("\nDone!")
