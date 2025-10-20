#!/usr/bin/env python3
"""
Create initial admin user for HR system
Run this script after database migrations
"""
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from hr.db.database import SessionLocal
from hr.models.user import User
from hr.core.security import hash_password


def create_admin_user():
    """Create the initial admin user"""
    db = SessionLocal()

    try:
        # Check if any users exist
        user_count = db.query(User).count()

        if user_count > 0:
            print(f"Users already exist in database ({user_count} users found)")
            print("Admin user may already be created.")
            response = input("Do you want to create another admin user? (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return

        # Get admin details
        print("\n=== Create HR Admin User ===\n")

        username = input("Username: ").strip()
        if not username:
            print("Error: Username cannot be empty")
            return

        # Check if username exists
        if db.query(User).filter(User.username == username).first():
            print(f"Error: Username '{username}' already exists")
            return

        email = input("Email: ").strip()
        if not email:
            print("Error: Email cannot be empty")
            return

        # Check if email exists
        if db.query(User).filter(User.email == email).first():
            print(f"Error: Email '{email}' already exists")
            return

        full_name = input("Full Name: ").strip()
        if not full_name:
            print("Error: Full name cannot be empty")
            return

        password = input("Password (min 6 characters): ").strip()
        if len(password) < 6:
            print("Error: Password must be at least 6 characters")
            return

        password_confirm = input("Confirm Password: ").strip()
        if password != password_confirm:
            print("Error: Passwords do not match")
            return

        # Create admin user
        admin_user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_admin=True,
            is_active=True
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print(f"\n✓ Admin user created successfully!")
        print(f"  Username: {admin_user.username}")
        print(f"  Email: {admin_user.email}")
        print(f"  Full Name: {admin_user.full_name}")
        print(f"\nYou can now login at /hr/login\n")

    except Exception as e:
        db.rollback()
        print(f"\nError creating admin user: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
