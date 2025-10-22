"""Add general accounting dashboard tables

Revision ID: 20251022_1600
Revises: 20251022_1500
Create Date: 2025-10-22 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_1600'
down_revision = '20251022_1500'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum for alert types (check if exists first)
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'dashboardalerttype')")).scalar()

    if not result:
        # Create enum directly with SQL to avoid conflicts
        conn.execute(sa.text("""
            CREATE TYPE dashboardalerttype AS ENUM (
                'UNPOSTED_JOURNAL',
                'PENDING_RECONCILIATION',
                'MISSING_DSS_MAPPING',
                'GL_BALANCE_OUTLIER',
                'SALES_DROP',
                'COGS_HIGH',
                'AP_AGING_HIGH',
                'MISSING_INVENTORY',
                'NEGATIVE_CASH',
                'PERIOD_NOT_CLOSED'
            )
        """))

    # Daily Financial Snapshot - aggregated daily metrics
    op.create_table(
        'daily_financial_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False, index=True),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id'), nullable=True, index=True),

        # Revenue metrics
        sa.Column('total_sales', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('food_sales', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('beverage_sales', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('alcohol_sales', sa.Numeric(15, 2), nullable=False, default=0),

        # COGS metrics
        sa.Column('total_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('food_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('beverage_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('cogs_percentage', sa.Numeric(5, 2), nullable=True),

        # Gross profit
        sa.Column('gross_profit', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('gross_profit_margin', sa.Numeric(5, 2), nullable=True),

        # Operating metrics
        sa.Column('total_expenses', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('labor_expense', sa.Numeric(15, 2), nullable=True),
        sa.Column('labor_percentage', sa.Numeric(5, 2), nullable=True),

        # Net income
        sa.Column('net_income', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('net_income_margin', sa.Numeric(5, 2), nullable=True),

        # Transaction counts
        sa.Column('transaction_count', sa.Integer(), nullable=False, default=0),
        sa.Column('average_check', sa.Numeric(10, 2), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),

        # Unique constraint
        sa.UniqueConstraint('snapshot_date', 'area_id', name='uq_snapshot_date_area')
    )

    # Monthly Performance Summary - closed month metrics
    op.create_table(
        'monthly_performance_summaries',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('period_month', sa.Date(), nullable=False, index=True, comment='First day of month'),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id'), nullable=True, index=True),
        sa.Column('is_closed', sa.Boolean(), nullable=False, default=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),

        # Revenue
        sa.Column('total_revenue', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('food_revenue', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('beverage_revenue', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('other_revenue', sa.Numeric(15, 2), nullable=False, default=0),

        # COGS
        sa.Column('total_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('food_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('beverage_cogs', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('cogs_percentage', sa.Numeric(5, 2), nullable=True),

        # Operating Expenses by category
        sa.Column('labor_expense', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('labor_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('rent_expense', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('utilities_expense', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('marketing_expense', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('repairs_expense', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('other_expenses', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('total_operating_expenses', sa.Numeric(15, 2), nullable=False, default=0),

        # Profitability
        sa.Column('gross_profit', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('gross_profit_margin', sa.Numeric(5, 2), nullable=True),
        sa.Column('operating_income', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('operating_margin', sa.Numeric(5, 2), nullable=True),
        sa.Column('net_income', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('net_income_margin', sa.Numeric(5, 2), nullable=True),

        # Prime Cost (COGS + Labor)
        sa.Column('prime_cost', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('prime_cost_percentage', sa.Numeric(5, 2), nullable=True),

        # Comparison to previous period
        sa.Column('revenue_vs_prior', sa.Numeric(5, 2), nullable=True, comment='Percentage change'),
        sa.Column('cogs_vs_prior', sa.Numeric(5, 2), nullable=True),
        sa.Column('labor_vs_prior', sa.Numeric(5, 2), nullable=True),
        sa.Column('net_income_vs_prior', sa.Numeric(5, 2), nullable=True),

        # Budget variance
        sa.Column('budgeted_revenue', sa.Numeric(15, 2), nullable=True),
        sa.Column('revenue_variance', sa.Numeric(15, 2), nullable=True),
        sa.Column('revenue_variance_pct', sa.Numeric(5, 2), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),

        # Unique constraint
        sa.UniqueConstraint('period_month', 'area_id', name='uq_period_area')
    )

    # Dashboard Alerts - system-generated alerts for accounting control
    op.create_table(
        'dashboard_alerts',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('alert_type', postgresql.ENUM('UNPOSTED_JOURNAL', 'PENDING_RECONCILIATION', 'MISSING_DSS_MAPPING',
                                       'GL_BALANCE_OUTLIER', 'SALES_DROP', 'COGS_HIGH', 'AP_AGING_HIGH',
                                       'MISSING_INVENTORY', 'NEGATIVE_CASH', 'PERIOD_NOT_CLOSED',
                                       name='dashboardalerttype', create_type=False), nullable=False, index=True),
        sa.Column('severity', sa.String(20), nullable=False, index=True, comment='critical, warning, info'),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id'), nullable=True, index=True),

        # Alert details
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metric_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('threshold_value', sa.Numeric(15, 2), nullable=True),

        # Related entity
        sa.Column('related_entity_type', sa.String(50), nullable=True, comment='journal_entry, reconciliation, etc'),
        sa.Column('related_entity_id', sa.Integer(), nullable=True),
        sa.Column('action_url', sa.String(500), nullable=True, comment='Link to fix the issue'),

        # Alert state
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True, index=True),
        sa.Column('is_acknowledged', sa.Boolean(), nullable=False, default=False),
        sa.Column('acknowledged_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),

        # Resolution
        sa.Column('is_resolved', sa.Boolean(), nullable=False, default=False),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), index=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp())
    )

    # Expense Category Summary - top expense tracking
    op.create_table(
        'expense_category_summaries',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('period_month', sa.Date(), nullable=False, index=True, comment='First day of month'),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id'), nullable=True, index=True),
        sa.Column('category_name', sa.String(100), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),

        # Amounts
        sa.Column('current_month', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('prior_month', sa.Numeric(15, 2), nullable=True),
        sa.Column('ytd_total', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('budget_amount', sa.Numeric(15, 2), nullable=True),

        # Percentages
        sa.Column('pct_of_revenue', sa.Numeric(5, 2), nullable=True),
        sa.Column('pct_change_mom', sa.Numeric(5, 2), nullable=True, comment='Month over month'),
        sa.Column('pct_of_total_expenses', sa.Numeric(5, 2), nullable=True),

        # Rankings
        sa.Column('rank_by_amount', sa.Integer(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),

        sa.UniqueConstraint('period_month', 'area_id', 'category_name', name='uq_period_area_category')
    )

    # Create indexes for performance
    op.create_index('idx_daily_snapshots_date_area', 'daily_financial_snapshots', ['snapshot_date', 'area_id'])
    op.create_index('idx_monthly_perf_month_area', 'monthly_performance_summaries', ['period_month', 'area_id'])
    op.create_index('idx_dashboard_alerts_active', 'dashboard_alerts', ['is_active', 'severity'])
    op.create_index('idx_expense_summary_month_area', 'expense_category_summaries', ['period_month', 'area_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_expense_summary_month_area', 'expense_category_summaries')
    op.drop_index('idx_dashboard_alerts_active', 'dashboard_alerts')
    op.drop_index('idx_monthly_perf_month_area', 'monthly_performance_summaries')
    op.drop_index('idx_daily_snapshots_date_area', 'daily_financial_snapshots')

    # Drop tables
    op.drop_table('expense_category_summaries')
    op.drop_table('dashboard_alerts')
    op.drop_table('monthly_performance_summaries')
    op.drop_table('daily_financial_snapshots')

    # Drop enum
    alert_type_enum = postgresql.ENUM(
        'UNPOSTED_JOURNAL', 'PENDING_RECONCILIATION', 'MISSING_DSS_MAPPING',
        'GL_BALANCE_OUTLIER', 'SALES_DROP', 'COGS_HIGH', 'AP_AGING_HIGH',
        'MISSING_INVENTORY', 'NEGATIVE_CASH', 'PERIOD_NOT_CLOSED',
        name='dashboardalerttype'
    )
    alert_type_enum.drop(op.get_bind(), checkfirst=True)
