"""add roles table

Revision ID: 006_add_roles
Revises: 005_add_invoices
Create Date: 2025-10-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006_add_roles'
down_revision = '005_add_invoices'
branch_labels = None
depends_on = None


def upgrade():
    # Create roles table
    op.create_table('roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('permissions', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # Insert default system roles
    op.execute("""
        INSERT INTO roles (name, description, permissions, is_system) VALUES
        ('Admin', 'Full system access with all permissions', '{"inventory_view": true, "inventory_edit": true, "inventory_count": true, "invoices_view": true, "invoices_create": true, "vendors_manage": true, "reports_view": true, "dashboard_view": true, "users_manage": true, "roles_manage": true, "settings_manage": true, "audit_view": true}', true),
        ('Manager', 'Manage inventory and view reports', '{"inventory_view": true, "inventory_edit": true, "inventory_count": true, "invoices_view": true, "invoices_create": true, "vendors_manage": true, "reports_view": true, "dashboard_view": true, "users_manage": false, "roles_manage": false, "settings_manage": false, "audit_view": true}', true),
        ('Staff', 'Basic inventory access', '{"inventory_view": true, "inventory_edit": false, "inventory_count": true, "invoices_view": false, "invoices_create": false, "vendors_manage": false, "reports_view": false, "dashboard_view": true, "users_manage": false, "roles_manage": false, "settings_manage": false, "audit_view": false}', true);
    """)


def downgrade():
    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_index(op.f('ix_roles_id'), table_name='roles')
    op.drop_table('roles')
