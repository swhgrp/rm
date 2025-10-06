#!/usr/bin/env python3
"""
Create initial admin user
"""
import sys
sys.path.insert(0, '/app/src')

from restaurant_inventory.db.database import SessionLocal
from restaurant_inventory.models.user import User
from restaurant_inventory.core.security import get_password_hash

db = SessionLocal()

try:
    # Check if admin user already exists
    existing_admin = db.query(User).filter(User.username == 'admin').first()
    if existing_admin:
        print("Admin user already exists!")
        sys.exit(0)

    # Create admin user
    admin_user = User(
        username='admin',
        email='admin@swhgrp.com',
        hashed_password=get_password_hash('admin123'),
        full_name='System Administrator',
        role='Admin',
        is_active=True,
        is_verified=True
    )

    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    print(f"✅ Admin user created successfully!")
    print(f"   Username: admin")
    print(f"   Password: admin123")
    print(f"   Please change the password after first login.")

except Exception as e:
    print(f"❌ Error creating admin user: {e}")
    db.rollback()
finally:
    db.close()
