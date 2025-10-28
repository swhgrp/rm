"""Seed initial data for events system"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from events.core.database import SessionLocal
from events.models import Role, Venue, EventTemplate
import json

def seed_roles(db):
    """Create default roles"""
    roles = [
        {"code": "admin", "name": "Administrator"},
        {"code": "event_manager", "name": "Event Manager"},
        {"code": "dept_lead", "name": "Department Lead"},
        {"code": "staff", "name": "Staff"},
        {"code": "read_only", "name": "Read Only"},
    ]

    for role_data in roles:
        existing = db.query(Role).filter(Role.code == role_data["code"]).first()
        if not existing:
            role = Role(**role_data)
            db.add(role)
            print(f"✓ Created role: {role_data['name']}")

    db.commit()


def seed_venues(db):
    """Create sample venues"""
    venues = [
        {
            "name": "Grand Ballroom",
            "address": "123 Main St, Downtown",
            "rooms_json": {
                "rooms": [
                    {"name": "Main Ballroom", "capacity": 300},
                    {"name": "Foyer", "capacity": 50},
                    {"name": "VIP Room", "capacity": 20}
                ]
            }
        },
        {
            "name": "Garden Pavilion",
            "address": "456 Garden Ln, Westside",
            "rooms_json": {
                "rooms": [
                    {"name": "Covered Patio", "capacity": 150},
                    {"name": "Open Lawn", "capacity": 200}
                ]
            }
        },
        {
            "name": "Corporate Center",
            "address": "789 Business Blvd, Business District",
            "rooms_json": {
                "rooms": [
                    {"name": "Conference Room A", "capacity": 50},
                    {"name": "Conference Room B", "capacity": 30},
                    {"name": "Board Room", "capacity": 20}
                ]
            }
        }
    ]

    for venue_data in venues:
        existing = db.query(Venue).filter(Venue.name == venue_data["name"]).first()
        if not existing:
            venue = Venue(**venue_data)
            db.add(venue)
            print(f"✓ Created venue: {venue_data['name']}")

    db.commit()


def seed_event_templates(db):
    """Create event templates"""
    templates = [
        {
            "name": "wedding_standard",
            "event_type": "Wedding",
            "form_schema_json": {
                "fields": [
                    {"name": "ceremony_time", "type": "time", "required": True},
                    {"name": "reception_start", "type": "time", "required": True},
                    {"name": "bridal_party_count", "type": "number", "required": False}
                ]
            },
            "default_tasks_json": {
                "tasks": [
                    {
                        "title": "Menu finalization meeting",
                        "department": "kitchen",
                        "due_offset_days": -30,
                        "priority": "high",
                        "checklist": [
                            "Confirm guest count",
                            "Finalize menu selections",
                            "Identify dietary restrictions",
                            "Confirm cake details"
                        ]
                    },
                    {
                        "title": "Bar setup and inventory",
                        "department": "bar",
                        "due_offset_days": -7,
                        "priority": "high",
                        "checklist": [
                            "Order wine and champagne",
                            "Prepare signature cocktails",
                            "Stock standard bar items",
                            "Prep garnishes"
                        ]
                    },
                    {
                        "title": "AV and music setup",
                        "department": "av",
                        "due_offset_days": -3,
                        "priority": "high",
                        "checklist": [
                            "Test microphones (ceremony + reception)",
                            "Set up projector for slideshow",
                            "Configure music playlist",
                            "Test dance floor lighting"
                        ]
                    },
                    {
                        "title": "Final venue walkthrough",
                        "department": "floor",
                        "due_offset_days": -1,
                        "priority": "high",
                        "checklist": [
                            "Set up ceremony chairs",
                            "Arrange reception tables",
                            "Place centerpieces",
                            "Set up gift table"
                        ]
                    },
                    {
                        "title": "Day-of coordination",
                        "department": "floor",
                        "due_offset_days": 0,
                        "priority": "high",
                        "checklist": [
                            "Coordinate with vendors",
                            "Direct ceremony",
                            "Manage timeline",
                            "Oversee reception"
                        ]
                    }
                ]
            },
            "default_menu_json": {
                "categories": ["Appetizers", "Entrees", "Desserts", "Bar"],
                "items": []
            },
            "default_financials_json": {
                "base_price": 10000,
                "per_guest": 85,
                "deposit_percent": 50,
                "tax_rate": 0.08
            },
            "email_rules_json": {
                "on_created": [
                    {
                        "to": "{client.email}",
                        "subject": "Wedding Request Received - {event.title}",
                        "template_key": "client_confirmation"
                    }
                ],
                "on_confirmed": [
                    {
                        "to": "{client.email}",
                        "subject": "Your Wedding is Confirmed! - {event.title}",
                        "template_key": "client_confirmation"
                    },
                    {
                        "to": "kitchen@swhgrp.com",
                        "cc": "bar@swhgrp.com",
                        "subject": "New Wedding Event - {event.title} on {event.start_at}",
                        "template_key": "internal_update"
                    }
                ]
            },
            "doc_templates_json": {
                "beo": {"template_key": "beo_v1"},
                "summary": {"template_key": "event_summary_v1"}
            }
        },
        {
            "name": "corporate_lunch",
            "event_type": "Corporate Event",
            "form_schema_json": {
                "fields": [
                    {"name": "presentation_time", "type": "time", "required": False},
                    {"name": "av_requirements", "type": "text", "required": False}
                ]
            },
            "default_tasks_json": {
                "tasks": [
                    {
                        "title": "Menu selection and dietary accommodations",
                        "department": "kitchen",
                        "due_offset_days": -7,
                        "priority": "med",
                        "checklist": [
                            "Confirm attendee count",
                            "Collect dietary restrictions",
                            "Finalize menu"
                        ]
                    },
                    {
                        "title": "AV setup for presentation",
                        "department": "av",
                        "due_offset_days": -1,
                        "priority": "high",
                        "checklist": [
                            "Test projector/screen",
                            "Set up microphones",
                            "Test laptop connection"
                        ]
                    },
                    {
                        "title": "Room setup",
                        "department": "floor",
                        "due_offset_days": 0,
                        "priority": "high",
                        "checklist": [
                            "Arrange tables for lunch",
                            "Set up presentation area",
                            "Place name cards if needed"
                        ]
                    }
                ]
            },
            "default_menu_json": {
                "categories": ["Appetizers", "Entrees", "Desserts", "Beverages"],
                "items": []
            },
            "default_financials_json": {
                "base_price": 500,
                "per_guest": 35,
                "deposit_percent": 25,
                "tax_rate": 0.08
            },
            "email_rules_json": {
                "on_created": [
                    {
                        "to": "{client.email}",
                        "subject": "Corporate Event Request Received",
                        "template_key": "client_confirmation"
                    }
                ],
                "on_confirmed": [
                    {
                        "to": "kitchen@swhgrp.com",
                        "subject": "Corporate Lunch - {event.title}",
                        "template_key": "internal_update"
                    }
                ]
            },
            "doc_templates_json": {
                "beo": {"template_key": "beo_v1"}
            }
        }
    ]

    for template_data in templates:
        existing = db.query(EventTemplate).filter(
            EventTemplate.name == template_data["name"]
        ).first()

        if not existing:
            template = EventTemplate(**template_data)
            db.add(template)
            print(f"✓ Created template: {template_data['name']}")

    db.commit()


def main():
    """Run all seed functions"""
    print("🌱 Seeding database...")
    db = SessionLocal()

    try:
        seed_roles(db)
        seed_venues(db)
        seed_event_templates(db)

        print("\n✅ Database seeded successfully!")
        print("\n📝 Summary:")
        print(f"   - Roles: {db.query(Role).count()}")
        print(f"   - Venues: {db.query(Venue).count()}")
        print(f"   - Event Templates: {db.query(EventTemplate).count()}")

    except Exception as e:
        print(f"\n❌ Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
