#!/usr/bin/env python3
"""
Sync user-location assignments from HR database to Events database

This script copies the user_locations mappings from the HR system to the Events system.
It maps HR location names to Events venue names and HR user emails to Events user emails.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# HR Database connection
HR_DATABASE_URL = os.getenv(
    "HR_DATABASE_URL",
    "postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db"
)

# Events Database connection
EVENTS_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://events_user:events_pass@events-db:5432/events_db"
)

def sync_admin_venues(events_session):
    """
    Ensure all Administrators have access to all venues.
    Admins should see all events regardless of HR location assignments.
    """
    synced_count = 0

    # Get all admin user IDs
    admin_users = events_session.execute(text("""
        SELECT u.id, u.email
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        JOIN roles r ON ur.role_id = r.id
        WHERE r.name = 'Administrator' AND u.is_active = true
    """)).fetchall()

    # Get all venue IDs
    venues = events_session.execute(text("SELECT id, name FROM venues")).fetchall()

    for admin in admin_users:
        admin_id = admin[0]
        admin_email = admin[1]

        for venue in venues:
            venue_id = venue[0]
            venue_name = venue[1]

            # Insert if not exists
            result = events_session.execute(
                text("""
                    INSERT INTO user_locations (user_id, venue_id, created_at)
                    VALUES (:user_id, :venue_id, NOW())
                    ON CONFLICT (user_id, venue_id) DO NOTHING
                    RETURNING user_id
                """),
                {"user_id": admin_id, "venue_id": venue_id}
            ).fetchone()

            if result:
                print(f"✓ Admin access: {admin_email} → {venue_name}")
                synced_count += 1

    events_session.commit()
    return synced_count


def sync_locations():
    """Sync user-location assignments from HR to Events"""

    # Connect to both databases
    hr_engine = create_engine(HR_DATABASE_URL)
    events_engine = create_engine(EVENTS_DATABASE_URL)

    HRSession = sessionmaker(bind=hr_engine)
    EventsSession = sessionmaker(bind=events_engine)

    hr_session = HRSession()
    events_session = EventsSession()

    try:
        print("=" * 60)
        print("Syncing User-Location Assignments from HR to Events")
        print("=" * 60)

        # Get user-location mappings from HR
        hr_mappings = hr_session.execute(text("""
            SELECT
                u.email,
                l.name as location_name
            FROM user_locations ul
            JOIN users u ON ul.user_id = u.id
            JOIN locations l ON ul.location_id = l.id
            WHERE u.is_active = true AND l.is_active = true
            ORDER BY u.email, l.name
        """)).fetchall()

        print(f"\nFound {len(hr_mappings)} user-location assignments in HR\n")

        if not hr_mappings:
            print("No mappings to sync.")
            return

        # Clear existing mappings in Events
        events_session.execute(text("DELETE FROM user_locations"))
        print("Cleared existing user_locations in Events DB\n")

        synced_count = 0
        skipped_count = 0

        for hr_mapping in hr_mappings:
            email = hr_mapping[0]
            location_name = hr_mapping[1]

            # Find matching user in Events by email
            user_result = events_session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": email}
            ).fetchone()

            if not user_result:
                print(f"⚠️  Skipping {email} (user not found in Events)")
                skipped_count += 1
                continue

            user_id = user_result[0]

            # Find matching venue in Events by name (using LIKE for flexibility)
            # HR locations might be "Seaside Grill" and Events venues might be "Seaside Grill - Main"
            venue_result = events_session.execute(
                text("SELECT id FROM venues WHERE name ILIKE :name OR name ILIKE :name_pattern"),
                {"name": location_name, "name_pattern": f"%{location_name}%"}
            ).fetchone()

            if not venue_result:
                print(f"⚠️  Skipping {email} → {location_name} (venue not found in Events)")
                skipped_count += 1
                continue

            venue_id = venue_result[0]

            # Insert the mapping
            events_session.execute(
                text("""
                    INSERT INTO user_locations (user_id, venue_id, created_at)
                    VALUES (:user_id, :venue_id, NOW())
                    ON CONFLICT (user_id, venue_id) DO NOTHING
                """),
                {"user_id": user_id, "venue_id": venue_id}
            )

            print(f"✓ Synced: {email} → {location_name}")
            synced_count += 1

        events_session.commit()

        print("\n" + "=" * 60)
        print(f"Sync Complete!")
        print(f"  ✓ Synced: {synced_count}")
        print(f"  ⚠️  Skipped: {skipped_count}")
        print("=" * 60)

        # Now ensure all Administrators have access to all venues
        print("\n" + "=" * 60)
        print("Ensuring Administrators have access to all venues...")
        print("=" * 60 + "\n")

        admin_synced = sync_admin_venues(events_session)
        print(f"\n✓ Admin venue assignments added: {admin_synced}")

    except Exception as e:
        events_session.rollback()
        print(f"\n❌ Error during sync: {e}")
        sys.exit(1)
    finally:
        hr_session.close()
        events_session.close()


if __name__ == "__main__":
    sync_locations()
