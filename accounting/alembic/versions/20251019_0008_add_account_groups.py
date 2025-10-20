"""Add account groups for P&L report organization

Revision ID: 20251019_0008
Revises: 20251019_0007
Create Date: 2025-10-19 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251019_0008'
down_revision = '20251019_0007'
branch_labels = None
depends_on = None


def upgrade():
    """Add account_groups table and link to accounts"""

    # Create ReportSection enum
    report_section_enum = sa.Enum(
        'REVENUE', 'COGS', 'OPERATING_EXPENSES', 'OTHER_INCOME', 'OTHER_EXPENSES',
        name='reportsection'
    )
    report_section_enum.create(op.get_bind(), checkfirst=True)

    # Create account_groups table
    op.create_table(
        'account_groups',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('display_name', sa.String(250), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('report_section', report_section_enum, nullable=False, index=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0', index=True),
        sa.Column('parent_group_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now())
    )

    # Add account_group_id to accounts table
    op.add_column('accounts', sa.Column('account_group_id', sa.Integer(), nullable=True))
    op.create_index('ix_accounts_account_group_id', 'accounts', ['account_group_id'])
    op.create_foreign_key(
        'fk_accounts_account_group_id',
        'accounts', 'account_groups',
        ['account_group_id'], ['id'],
        ondelete='SET NULL'
    )

    # Insert common account groups based on the P&L example
    groups_data = [
        # REVENUE groups
        ('Food Sale', '4100-4103', '4100-4103 Food Sale', 'REVENUE', 10),
        ('NAB Sales', '4130-4131', '4130-4131 NAB Sales', 'REVENUE', 20),
        ('Alcohol Sales', '4140-4146', '4140-4146 Alcohol Sales', 'REVENUE', 30),
        ('Beer Sales', '4150-4153', '4150-4153 Beer Sales', 'REVENUE', 40),
        ('Wine Sales', '4155-4156', '4155-4156 Wine Sales', 'REVENUE', 50),
        ('Merchandise Sales', '4200', '4200 Merchandise Sales', 'REVENUE', 60),
        ('Voids/Refunds', '4819', '4819 Voids/Refunds', 'REVENUE', 70),

        # COGS groups
        ('Food Cost', '5100-5120', '5100-5120 Food Cost', 'COGS', 10),
        ('NAB Cost', '5130', '5130 NAB Cost', 'COGS', 20),
        ('Beer Cost', '5150-5152', '5150-5152 Beer Cost', 'COGS', 30),
        ('Wine Cost', '5155', '5155 Wine Cost', 'COGS', 40),

        # OPERATING_EXPENSES groups
        ('Payroll', '6105-6133', '6105-6133 Payroll', 'OPERATING_EXPENSES', 10),
        ('Payroll Taxes', '6300-6318', '6300-6318 Payroll Taxes', 'OPERATING_EXPENSES', 20),
        ('Employee Benefits', '6330-6370', '6330-6370 Employee Benefits', 'OPERATING_EXPENSES', 30),
        ('Direct Operating Expense', '7100-7199', '7100-7199 Direct Operating Expense', 'OPERATING_EXPENSES', 40),
        ('Utilities', '7200-7220', '7200-7220 Utilities', 'OPERATING_EXPENSES', 50),
        ('General and Administrative Expense', '7400-7550', '7400-7550 General and Administrative Expense', 'OPERATING_EXPENSES', 60),
        ('Repairs and Maintenance', '7600-7630', '7600-7630 Repairs and Maintenance', 'OPERATING_EXPENSES', 70),
        ('Occupancy Cost', '8100-8190', '8100-8190 Occupancy Cost', 'OPERATING_EXPENSES', 80),
        ('Interest Expense', '9200-9230', '9200-9230 Interest Expense', 'OPERATING_EXPENSES', 90),
    ]

    account_groups_table = sa.table('account_groups',
        sa.column('name', sa.String),
        sa.column('code', sa.String),
        sa.column('display_name', sa.String),
        sa.column('report_section', sa.String),
        sa.column('sort_order', sa.Integer)
    )

    for name, code, display_name, report_section, sort_order in groups_data:
        op.execute(
            account_groups_table.insert().values(
                name=name,
                code=code,
                display_name=display_name,
                report_section=report_section,
                sort_order=sort_order
            )
        )


def downgrade():
    """Remove account groups"""
    op.drop_constraint('fk_accounts_account_group_id', 'accounts', type_='foreignkey')
    op.drop_index('ix_accounts_account_group_id', 'accounts')
    op.drop_column('accounts', 'account_group_id')
    op.drop_table('account_groups')

    # Drop enum
    sa.Enum(name='reportsection').drop(op.get_bind(), checkfirst=True)
