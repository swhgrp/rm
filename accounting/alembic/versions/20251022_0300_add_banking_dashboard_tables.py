"""Add banking dashboard tables

Revision ID: 20251022_0300
Revises: 20251022_0200
Create Date: 2025-10-22 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_0300'
down_revision = '20251022_0200'
branch_labels = None
depends_on = None


def upgrade():
    # Create enum types
    op.execute("""
        CREATE TYPE cashflowcategory AS ENUM (
            'operating_inflow', 'operating_outflow',
            'investing_inflow', 'investing_outflow',
            'financing_inflow', 'financing_outflow',
            'transfer'
        )
    """)

    op.execute("""
        CREATE TYPE alertseverity AS ENUM ('critical', 'warning', 'info')
    """)

    op.execute("""
        CREATE TYPE alerttype AS ENUM (
            'gl_variance', 'low_balance', 'unreconciled_old',
            'missing_transaction', 'duplicate_transaction', 'unusual_amount',
            'reconciliation_stuck', 'negative_balance', 'large_transaction'
        )
    """)

    # Create daily_cash_positions table
    op.create_table(
        'daily_cash_positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_date', sa.Date(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('closing_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('total_inflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('total_outflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_change', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('transaction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reconciled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unreconciled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gl_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('variance', sa.Numeric(15, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_daily_cash_positions_position_date', 'daily_cash_positions', ['position_date'])
    op.create_index('ix_daily_cash_positions_area_id', 'daily_cash_positions', ['area_id'])
    op.create_index('ix_daily_cash_positions_bank_account_id', 'daily_cash_positions', ['bank_account_id'])
    op.create_foreign_key('fk_daily_cash_positions_area', 'daily_cash_positions', 'areas', ['area_id'], ['id'])
    op.create_foreign_key('fk_daily_cash_positions_bank_account', 'daily_cash_positions', 'bank_accounts', ['bank_account_id'], ['id'])

    # Create cash_flow_transactions table
    op.create_table(
        'cash_flow_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('category', postgresql.ENUM(name='cashflowcategory', create_type=False), nullable=False),
        sa.Column('subcategory', sa.String(100), nullable=True),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_auto_classified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('classification_confidence', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cash_flow_transactions_bank_transaction_id', 'cash_flow_transactions', ['bank_transaction_id'])
    op.create_index('ix_cash_flow_transactions_area_id', 'cash_flow_transactions', ['area_id'])
    op.create_index('ix_cash_flow_transactions_category', 'cash_flow_transactions', ['category'])
    op.create_index('ix_cash_flow_transactions_transaction_date', 'cash_flow_transactions', ['transaction_date'])
    op.create_foreign_key('fk_cash_flow_transactions_bank_transaction', 'cash_flow_transactions', 'bank_transactions', ['bank_transaction_id'], ['id'])
    op.create_foreign_key('fk_cash_flow_transactions_area', 'cash_flow_transactions', 'areas', ['area_id'], ['id'])

    # Create banking_alerts table
    op.create_table(
        'banking_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_type', postgresql.ENUM(name='alerttype', create_type=False), nullable=False),
        sa.Column('severity', postgresql.ENUM(name='alertseverity', create_type=False), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_acknowledged', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_banking_alerts_alert_type', 'banking_alerts', ['alert_type'])
    op.create_index('ix_banking_alerts_severity', 'banking_alerts', ['severity'])
    op.create_index('ix_banking_alerts_area_id', 'banking_alerts', ['area_id'])
    op.create_index('ix_banking_alerts_bank_account_id', 'banking_alerts', ['bank_account_id'])
    op.create_index('ix_banking_alerts_bank_transaction_id', 'banking_alerts', ['bank_transaction_id'])
    op.create_index('ix_banking_alerts_is_active', 'banking_alerts', ['is_active'])
    op.create_index('ix_banking_alerts_created_at', 'banking_alerts', ['created_at'])
    op.create_foreign_key('fk_banking_alerts_area', 'banking_alerts', 'areas', ['area_id'], ['id'])
    op.create_foreign_key('fk_banking_alerts_bank_account', 'banking_alerts', 'bank_accounts', ['bank_account_id'], ['id'])
    op.create_foreign_key('fk_banking_alerts_bank_transaction', 'banking_alerts', 'bank_transactions', ['bank_transaction_id'], ['id'])
    op.create_foreign_key('fk_banking_alerts_acknowledged_by', 'banking_alerts', 'users', ['acknowledged_by'], ['id'])
    op.create_foreign_key('fk_banking_alerts_resolved_by', 'banking_alerts', 'users', ['resolved_by'], ['id'])

    # Create reconciliation_health_metrics table
    op.create_table(
        'reconciliation_health_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('total_transactions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reconciled_transactions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unreconciled_transactions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reconciliation_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('avg_days_to_reconcile', sa.Numeric(10, 2), nullable=True),
        sa.Column('transactions_over_30_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transactions_over_60_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transactions_over_90_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('auto_matched_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_matched_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('auto_match_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('gl_variance_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_gl_variance', sa.Numeric(15, 2), nullable=True),
        sa.Column('avg_gl_variance', sa.Numeric(15, 2), nullable=True),
        sa.Column('critical_alerts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_alerts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reconciliation_health_metrics_metric_date', 'reconciliation_health_metrics', ['metric_date'])
    op.create_index('ix_reconciliation_health_metrics_area_id', 'reconciliation_health_metrics', ['area_id'])
    op.create_foreign_key('fk_reconciliation_health_metrics_area', 'reconciliation_health_metrics', 'areas', ['area_id'], ['id'])

    # Create location_cash_flow_summaries table
    op.create_table(
        'location_cash_flow_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('summary_month', sa.Date(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('closing_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('operating_inflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('operating_outflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_operating_cash_flow', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('investing_inflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('investing_outflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_investing_cash_flow', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('financing_inflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('financing_outflows', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_financing_cash_flow', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('net_cash_change', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('daily_burn_rate', sa.Numeric(15, 2), nullable=True),
        sa.Column('runway_days', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_location_cash_flow_summaries_area_id', 'location_cash_flow_summaries', ['area_id'])
    op.create_index('ix_location_cash_flow_summaries_summary_month', 'location_cash_flow_summaries', ['summary_month'])
    op.create_foreign_key('fk_location_cash_flow_summaries_area', 'location_cash_flow_summaries', 'areas', ['area_id'], ['id'])


def downgrade():
    op.drop_table('location_cash_flow_summaries')
    op.drop_table('reconciliation_health_metrics')
    op.drop_table('banking_alerts')
    op.drop_table('cash_flow_transactions')
    op.drop_table('daily_cash_positions')

    # Drop enum types
    op.execute('DROP TYPE IF EXISTS alerttype')
    op.execute('DROP TYPE IF EXISTS alertseverity')
    op.execute('DROP TYPE IF EXISTS cashflowcategory')
