"""Add permissions system

Revision ID: 20251019_0007
Revises: 20251019_0006
Create Date: 2025-10-19 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '20251019_0007'
down_revision = '20251019_0006'
branch_labels = None
depends_on = None


def upgrade():
    """Add permissions table and role_permissions association table"""

    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('module', sa.String(50), nullable=False, index=True),
        sa.Column('action', sa.String(20), nullable=False, index=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
    )

    # Create role_permissions association table
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', sa.Integer(), sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
    )

    # Insert standard permissions
    permissions_data = [
        # General Ledger permissions
        ('general_ledger', 'view', 'general_ledger:view', 'View GL accounts and balances'),
        ('general_ledger', 'create', 'general_ledger:create', 'Create GL accounts'),
        ('general_ledger', 'edit', 'general_ledger:edit', 'Edit GL accounts'),
        ('general_ledger', 'delete', 'general_ledger:delete', 'Delete GL accounts'),

        # Journal Entries permissions
        ('journal_entries', 'view', 'journal_entries:view', 'View journal entries'),
        ('journal_entries', 'create', 'journal_entries:create', 'Create journal entries'),
        ('journal_entries', 'edit', 'journal_entries:edit', 'Edit draft journal entries'),
        ('journal_entries', 'delete', 'journal_entries:delete', 'Delete draft journal entries'),
        ('journal_entries', 'approve', 'journal_entries:approve', 'Post journal entries'),
        ('journal_entries', 'reverse', 'journal_entries:reverse', 'Reverse posted journal entries'),

        # Daily Sales Summary permissions
        ('daily_sales', 'view', 'daily_sales:view', 'View daily sales summaries'),
        ('daily_sales', 'create', 'daily_sales:create', 'Create daily sales summaries'),
        ('daily_sales', 'edit', 'daily_sales:edit', 'Edit daily sales summaries'),
        ('daily_sales', 'delete', 'daily_sales:delete', 'Delete daily sales summaries'),
        ('daily_sales', 'verify', 'daily_sales:verify', 'Verify daily sales summaries'),
        ('daily_sales', 'post', 'daily_sales:post', 'Post daily sales summaries'),
        ('daily_sales', 'reopen', 'daily_sales:reopen', 'Reopen posted daily sales summaries'),

        # Accounts Payable permissions
        ('accounts_payable', 'view', 'accounts_payable:view', 'View vendor bills'),
        ('accounts_payable', 'create', 'accounts_payable:create', 'Create vendor bills'),
        ('accounts_payable', 'edit', 'accounts_payable:edit', 'Edit vendor bills'),
        ('accounts_payable', 'delete', 'accounts_payable:delete', 'Delete vendor bills'),
        ('accounts_payable', 'approve', 'accounts_payable:approve', 'Approve vendor bills for payment'),
        ('accounts_payable', 'pay', 'accounts_payable:pay', 'Process payments'),

        # Reports permissions
        ('reports', 'view', 'reports:view', 'View financial reports'),
        ('reports', 'export', 'reports:export', 'Export reports to Excel/PDF'),

        # Administration permissions
        ('users', 'view', 'users:view', 'View users'),
        ('users', 'create', 'users:create', 'Create users'),
        ('users', 'edit', 'users:edit', 'Edit users'),
        ('users', 'delete', 'users:delete', 'Delete users'),

        ('roles', 'view', 'roles:view', 'View roles'),
        ('roles', 'create', 'roles:create', 'Create roles'),
        ('roles', 'edit', 'roles:edit', 'Edit roles'),
        ('roles', 'delete', 'roles:delete', 'Delete roles'),

        ('locations', 'view', 'locations:view', 'View locations/areas'),
        ('locations', 'create', 'locations:create', 'Create locations/areas'),
        ('locations', 'edit', 'locations:edit', 'Edit locations/areas'),
        ('locations', 'delete', 'locations:delete', 'Delete locations/areas'),

        ('fiscal_periods', 'view', 'fiscal_periods:view', 'View fiscal periods'),
        ('fiscal_periods', 'create', 'fiscal_periods:create', 'Create fiscal periods'),
        ('fiscal_periods', 'edit', 'fiscal_periods:edit', 'Edit fiscal periods'),
        ('fiscal_periods', 'close', 'fiscal_periods:close', 'Close fiscal periods'),

        ('settings', 'view', 'settings:view', 'View system settings'),
        ('settings', 'edit', 'settings:edit', 'Modify system settings'),
    ]

    # Use direct SQL to insert permissions
    permissions_table = sa.table('permissions',
        sa.column('module', sa.String),
        sa.column('action', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.Text)
    )

    for module, action, name, description in permissions_data:
        op.execute(
            permissions_table.insert().values(
                module=module,
                action=action,
                name=name,
                description=description
            )
        )

    # Assign all permissions to Administrator role (role_id = 1)
    # Get all permission IDs
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM permissions"))
    permission_ids = [row[0] for row in result]

    role_permissions_table = sa.table('role_permissions',
        sa.column('role_id', sa.Integer),
        sa.column('permission_id', sa.Integer)
    )

    for perm_id in permission_ids:
        op.execute(
            role_permissions_table.insert().values(
                role_id=1,  # Administrator role
                permission_id=perm_id
            )
        )


def downgrade():
    """Remove permissions system"""
    op.drop_table('role_permissions')
    op.drop_table('permissions')
