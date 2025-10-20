"""Add roles and areas tables

Revision ID: 20251018_0002
Revises: 20251018_0001
Create Date: 2025-10-18 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251018_0002'
down_revision = '20251018_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_roles_id', 'roles', ['id'])
    op.create_index('ix_roles_name', 'roles', ['name'])

    # Create areas table
    op.create_table(
        'areas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('code')
    )
    op.create_index('ix_areas_id', 'areas', ['id'])
    op.create_index('ix_areas_code', 'areas', ['code'])

    # Create role_areas association table (many-to-many)
    op.create_table(
        'role_areas',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'area_id')
    )

    # Add role_id column to users table
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.create_index('ix_users_role_id', 'users', ['role_id'])
    op.create_foreign_key('fk_users_role_id', 'users', 'roles', ['role_id'], ['id'], ondelete='SET NULL')

    # Insert default roles
    op.execute("""
        INSERT INTO roles (name, description) VALUES
        ('Administrator', 'Full system access with all permissions'),
        ('Accountant', 'Can create and manage journal entries, view reports'),
        ('Manager', 'Can view reports and approve transactions'),
        ('Viewer', 'Read-only access to reports and data')
    """)


def downgrade():
    # Drop foreign key and role_id column from users
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    op.drop_index('ix_users_role_id', table_name='users')
    op.drop_column('users', 'role_id')

    # Drop association table
    op.drop_table('role_areas')

    # Drop areas table
    op.drop_index('ix_areas_code', table_name='areas')
    op.drop_index('ix_areas_id', table_name='areas')
    op.drop_table('areas')

    # Drop roles table
    op.drop_index('ix_roles_name', table_name='roles')
    op.drop_index('ix_roles_id', table_name='roles')
    op.drop_table('roles')
