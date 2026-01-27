"""Add refund_breakdown to DSS and POS cache

Revision ID: 20260126_0001
Revises: 20260106_0001
Create Date: 2026-01-26 00:00:00

This migration adds refund_breakdown JSONB columns to both
daily_sales_summaries and pos_daily_sales_cache tables.
This allows tracking refunds by original sale category for
proper GL posting (e.g., Merchandise refund debits Merchandise Sales).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260126_0001'
down_revision = '20260106_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Add refund_breakdown column to daily_sales_summaries
    # Example: {"Merchandise": 25.00, "Food": 10.00}
    op.add_column(
        'daily_sales_summaries',
        sa.Column('refund_breakdown', postgresql.JSONB, nullable=True)
    )

    # Add refunds column to pos_daily_sales_cache (breakdown by category)
    # Example: {"Merchandise": 25.00, "Food": 10.00}
    op.add_column(
        'pos_daily_sales_cache',
        sa.Column('refunds', postgresql.JSONB, nullable=True)
    )


def downgrade():
    # Remove refund_breakdown column from daily_sales_summaries
    op.drop_column('daily_sales_summaries', 'refund_breakdown')

    # Remove refunds column from pos_daily_sales_cache
    op.drop_column('pos_daily_sales_cache', 'refunds')
