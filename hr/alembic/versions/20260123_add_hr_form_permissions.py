"""Add HR form permissions (corrective actions, injury reports, settings, sensitive docs)

Revision ID: hr_permissions_001
Revises: hr_forms_001
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'hr_permissions_001'
down_revision = 'hr_forms_001'
branch_labels = None
depends_on = None


def upgrade():
    # Get connection for raw SQL
    conn = op.get_bind()

    # Add new permissions
    new_permissions = [
        # Corrective Action permissions
        ('view_corrective_actions', 'View corrective action forms', 'corrective_action', 'view'),
        ('create_corrective_action', 'Create corrective action forms', 'corrective_action', 'create'),

        # Injury Report permissions
        ('view_injury_reports', 'View first report of injury forms', 'injury_report', 'view'),
        ('create_injury_report', 'Create first report of injury forms', 'injury_report', 'create'),

        # Settings permissions
        ('view_settings', 'View system settings', 'settings', 'view'),
        ('manage_settings', 'Manage system settings', 'settings', 'manage'),

        # Sensitive document permissions
        ('view_sensitive_documents', 'View sensitive documents (ID copies, SSN cards)', 'document', 'view_sensitive'),
    ]

    for name, description, resource, action in new_permissions:
        conn.execute(sa.text("""
            INSERT INTO permissions (name, description, resource, action, created_at)
            VALUES (:name, :description, :resource, :action, :created_at)
            ON CONFLICT (name) DO NOTHING
        """), {
            'name': name,
            'description': description,
            'resource': resource,
            'action': action,
            'created_at': datetime.utcnow()
        })

    # Get Admin role ID
    result = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'Admin'"))
    admin_role = result.fetchone()

    # Get Manager role ID
    result = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'Manager'"))
    manager_role = result.fetchone()

    if admin_role:
        admin_role_id = admin_role[0]
        # Admin gets all new permissions
        admin_permissions = [
            'view_corrective_actions', 'create_corrective_action',
            'view_injury_reports', 'create_injury_report',
            'view_settings', 'manage_settings',
            'view_sensitive_documents'
        ]
        for perm_name in admin_permissions:
            result = conn.execute(sa.text("SELECT id FROM permissions WHERE name = :name"), {'name': perm_name})
            perm = result.fetchone()
            if perm:
                conn.execute(sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (:role_id, :perm_id)
                    ON CONFLICT DO NOTHING
                """), {'role_id': admin_role_id, 'perm_id': perm[0]})

    if manager_role:
        manager_role_id = manager_role[0]
        # Manager gets form permissions but NOT settings or sensitive docs
        manager_permissions = [
            'view_corrective_actions', 'create_corrective_action',
            'view_injury_reports', 'create_injury_report',
            'edit_employee'  # Also allow managers to edit employees
        ]
        for perm_name in manager_permissions:
            result = conn.execute(sa.text("SELECT id FROM permissions WHERE name = :name"), {'name': perm_name})
            perm = result.fetchone()
            if perm:
                conn.execute(sa.text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (:role_id, :perm_id)
                    ON CONFLICT DO NOTHING
                """), {'role_id': manager_role_id, 'perm_id': perm[0]})


def downgrade():
    conn = op.get_bind()

    # Remove new permissions (this will also remove role_permissions due to FK cascade)
    permissions_to_remove = [
        'view_corrective_actions', 'create_corrective_action',
        'view_injury_reports', 'create_injury_report',
        'view_settings', 'manage_settings',
        'view_sensitive_documents'
    ]

    for perm_name in permissions_to_remove:
        conn.execute(sa.text("DELETE FROM permissions WHERE name = :name"), {'name': perm_name})
