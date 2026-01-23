"""Add categories and user permissions tables

Revision ID: 002
Revises: 001
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_categories_permissions'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create categories table
    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('color', sa.String(20), server_default='#455A64', nullable=True),
        sa.Column('icon', sa.String(50), server_default='bi-folder', nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )

    # Create user_permissions table
    op.create_table(
        'user_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('can_create_templates', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_edit_templates', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_delete_templates', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_all_submissions', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_delete_submissions', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_export_submissions', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('can_manage_categories', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_manage_users', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('can_view_audit_logs', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('allowed_locations', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id')
    )
    op.create_index('ix_user_permissions_employee_id', 'user_permissions', ['employee_id'])

    # Insert default categories (matching existing enum values)
    op.execute("""
        INSERT INTO categories (id, name, slug, description, color, icon, sort_order, is_active)
        VALUES
            (gen_random_uuid(), 'Human Resources', 'hr_employment', 'HR & Employment forms', '#1976D2', 'bi-people', 1, true),
            (gen_random_uuid(), 'Safety & Compliance', 'safety_compliance', 'Safety and compliance forms', '#F57C00', 'bi-shield-check', 2, true),
            (gen_random_uuid(), 'Operations', 'operations', 'Operational forms', '#388E3C', 'bi-gear', 3, true)
    """)


def downgrade() -> None:
    op.drop_index('ix_user_permissions_employee_id', table_name='user_permissions')
    op.drop_table('user_permissions')
    op.drop_table('categories')
