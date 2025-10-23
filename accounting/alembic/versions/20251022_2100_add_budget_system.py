"""Add budget management system

Revision ID: 20251022_2100
Revises: 20251022_2000
Create Date: 2025-10-22 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_2100'
down_revision = '20251022_2000'
branch_labels = None
depends_on = None


def upgrade():
    # Budget status enum
    op.execute("""
        CREATE TYPE budget_status AS ENUM (
            'DRAFT',
            'PENDING_APPROVAL',
            'APPROVED',
            'ACTIVE',
            'CLOSED',
            'REJECTED'
        )
    """)

    # Budget period type enum
    op.execute("""
        CREATE TYPE budget_period_type AS ENUM (
            'ANNUAL',
            'QUARTERLY',
            'MONTHLY'
        )
    """)

    # Budgets - main budget header
    op.create_table(
        'budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_name', sa.String(200), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', postgresql.ENUM('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'ACTIVE', 'CLOSED', 'REJECTED', name='budget_status', create_type=False), nullable=False, server_default='DRAFT'),
        sa.Column('budget_type', sa.String(50), nullable=False, server_default='OPERATING'),  # OPERATING, CAPITAL, CASH_FLOW
        sa.Column('area_id', sa.Integer(), nullable=True),  # NULL = consolidated/all areas
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('total_revenue', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('total_expenses', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_income', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_budgets_fiscal_year', 'budgets', ['fiscal_year'])
    op.create_index('idx_budgets_status', 'budgets', ['status'])
    op.create_index('idx_budgets_area', 'budgets', ['area_id'])
    op.create_index('idx_budgets_dates', 'budgets', ['start_date', 'end_date'])

    # Budget periods - monthly/quarterly breakdowns
    op.create_table(
        'budget_periods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('period_type', postgresql.ENUM('ANNUAL', 'QUARTERLY', 'MONTHLY', name='budget_period_type', create_type=False), nullable=False),
        sa.Column('period_number', sa.Integer(), nullable=False),  # 1-12 for months, 1-4 for quarters
        sa.Column('period_name', sa.String(50), nullable=False),  # "January 2025", "Q1 2025"
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('budget_id', 'period_type', 'period_number', name='uq_budget_period')
    )
    op.create_index('idx_budget_periods_budget', 'budget_periods', ['budget_id'])
    op.create_index('idx_budget_periods_dates', 'budget_periods', ['start_date', 'end_date'])

    # Budget lines - account-level budget amounts
    op.create_table(
        'budget_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('budget_period_id', sa.Integer(), nullable=True),  # NULL = annual total
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['budget_period_id'], ['budget_periods.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('budget_id', 'budget_period_id', 'account_id', name='uq_budget_line')
    )
    op.create_index('idx_budget_lines_budget', 'budget_lines', ['budget_id'])
    op.create_index('idx_budget_lines_period', 'budget_lines', ['budget_period_id'])
    op.create_index('idx_budget_lines_account', 'budget_lines', ['account_id'])

    # Budget templates - save budget configurations for reuse
    op.create_table(
        'budget_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('budget_type', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )

    # Budget template lines
    op.create_table(
        'budget_template_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('allocation_method', sa.String(20), nullable=False, server_default='EQUAL'),  # EQUAL, WEIGHTED, MANUAL
        sa.Column('growth_rate', sa.Numeric(5, 2), nullable=True),  # % growth from prior year
        sa.Column('monthly_allocation', postgresql.JSONB(), nullable=True),  # {1: 0.08, 2: 0.08, ...}
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['template_id'], ['budget_templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'account_id', name='uq_template_line')
    )

    # Budget revisions - track changes to approved budgets
    op.create_table(
        'budget_revisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('revision_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('revised_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('total_revenue_change', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('total_expense_change', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revised_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('budget_id', 'revision_number', name='uq_budget_revision')
    )

    # Budget alerts - configure alerts for variance thresholds
    op.create_table(
        'budget_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),  # NULL = alert for entire budget
        sa.Column('alert_type', sa.String(20), nullable=False),  # OVER_BUDGET, UNDER_BUDGET, VARIANCE
        sa.Column('threshold_percent', sa.Numeric(5, 2), nullable=False),  # Alert when variance exceeds %
        sa.Column('threshold_amount', sa.Numeric(15, 2), nullable=True),  # Alert when variance exceeds $
        sa.Column('notify_users', postgresql.ARRAY(sa.Integer()), nullable=True),  # Array of user IDs
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('budget_alerts')
    op.drop_table('budget_revisions')
    op.drop_table('budget_template_lines')
    op.drop_table('budget_templates')
    op.drop_table('budget_lines')
    op.drop_table('budget_periods')
    op.drop_table('budgets')

    op.execute('DROP TYPE budget_period_type')
    op.execute('DROP TYPE budget_status')
