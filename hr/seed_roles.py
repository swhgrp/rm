#!/usr/bin/env python3
"""
Seed default roles and permissions for HR system
Creates Admin and Manager roles with appropriate permissions
"""
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hr.db.database import SessionLocal
from hr.models.role import Role
from hr.models.permission import Permission
from hr.models.role_permission import RolePermission


def seed_permissions(db):
    """Create default permissions"""
    permissions_data = [
        # Employee Management
        {
            "name": "view_employees",
            "description": "View employee information",
            "resource": "employee",
            "action": "view"
        },
        {
            "name": "create_employee",
            "description": "Create new employees",
            "resource": "employee",
            "action": "create"
        },
        {
            "name": "edit_employee",
            "description": "Edit employee information",
            "resource": "employee",
            "action": "update"
        },
        {
            "name": "delete_employee",
            "description": "Delete employees",
            "resource": "employee",
            "action": "delete"
        },
        {
            "name": "export_employees",
            "description": "Export employee data",
            "resource": "employee",
            "action": "export"
        },

        # Position Management
        {
            "name": "view_positions",
            "description": "View positions",
            "resource": "position",
            "action": "view"
        },
        {
            "name": "create_position",
            "description": "Create new positions",
            "resource": "position",
            "action": "create"
        },
        {
            "name": "edit_position",
            "description": "Edit positions",
            "resource": "position",
            "action": "update"
        },
        {
            "name": "delete_position",
            "description": "Delete positions",
            "resource": "position",
            "action": "delete"
        },

        # Document Management
        {
            "name": "view_documents",
            "description": "View employee documents",
            "resource": "document",
            "action": "view"
        },
        {
            "name": "upload_document",
            "description": "Upload employee documents",
            "resource": "document",
            "action": "create"
        },
        {
            "name": "delete_document",
            "description": "Delete employee documents",
            "resource": "document",
            "action": "delete"
        },

        # User Management
        {
            "name": "view_users",
            "description": "View system users",
            "resource": "user",
            "action": "view"
        },
        {
            "name": "create_user",
            "description": "Create new users",
            "resource": "user",
            "action": "create"
        },
        {
            "name": "edit_user",
            "description": "Edit user information",
            "resource": "user",
            "action": "update"
        },
        {
            "name": "delete_user",
            "description": "Delete users",
            "resource": "user",
            "action": "delete"
        },
        {
            "name": "manage_roles",
            "description": "Assign and manage user roles",
            "resource": "user",
            "action": "manage_roles"
        },

        # Reports
        {
            "name": "view_reports",
            "description": "View HR reports",
            "resource": "report",
            "action": "view"
        },
        {
            "name": "export_reports",
            "description": "Export report data",
            "resource": "report",
            "action": "export"
        }
    ]

    created_permissions = {}

    for perm_data in permissions_data:
        # Check if permission already exists
        existing = db.query(Permission).filter(Permission.name == perm_data["name"]).first()

        if existing:
            print(f"  Permission '{perm_data['name']}' already exists")
            created_permissions[perm_data["name"]] = existing
        else:
            permission = Permission(**perm_data)
            db.add(permission)
            db.flush()
            print(f"  Created permission: {perm_data['name']}")
            created_permissions[perm_data["name"]] = permission

    db.commit()
    return created_permissions


def seed_roles(db, permissions):
    """Create Admin and Manager roles"""
    # Define roles and their permissions
    roles_data = {
        "Admin": {
            "description": "Full system access - all permissions",
            "permissions": [
                # All permissions
                "view_employees", "create_employee", "edit_employee", "delete_employee", "export_employees",
                "view_positions", "create_position", "edit_position", "delete_position",
                "view_documents", "upload_document", "delete_document",
                "view_users", "create_user", "edit_user", "delete_user", "manage_roles",
                "view_reports", "export_reports"
            ]
        },
        "Manager": {
            "description": "Create/view employees and upload documents",
            "permissions": [
                # Employee permissions
                "view_employees", "create_employee",
                # Position viewing
                "view_positions",
                # Document management
                "view_documents", "upload_document"
            ]
        }
    }

    for role_name, role_info in roles_data.items():
        # Check if role already exists
        existing_role = db.query(Role).filter(Role.name == role_name).first()

        if existing_role:
            print(f"\nRole '{role_name}' already exists, updating permissions...")
            role = existing_role

            # Clear existing permissions
            db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        else:
            # Create new role
            role = Role(
                name=role_name,
                description=role_info["description"],
                is_active=True
            )
            db.add(role)
            db.flush()
            print(f"\nCreated role: {role_name}")

        # Add permissions to role
        for perm_name in role_info["permissions"]:
            if perm_name in permissions:
                role_perm = RolePermission(
                    role_id=role.id,
                    permission_id=permissions[perm_name].id
                )
                db.add(role_perm)
                print(f"  Added permission: {perm_name}")

    db.commit()
    print("\n✓ Roles and permissions seeded successfully!")


def main():
    """Main seeding function"""
    print("Seeding HR roles and permissions...")
    print("=" * 60)

    db = SessionLocal()

    try:
        print("\n1. Creating permissions...")
        permissions = seed_permissions(db)

        print(f"\n✓ Created/verified {len(permissions)} permissions")

        print("\n2. Creating roles...")
        seed_roles(db, permissions)

        print("\n" + "=" * 60)
        print("Seeding complete!")
        print("\nCreated roles:")
        print("  - Admin: Full system access")
        print("  - Manager: Create/view employees, upload documents")
        print("\nYou can now assign these roles to users via the API or admin interface.")

    except Exception as e:
        print(f"\n✗ Error during seeding: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
