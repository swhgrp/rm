"""Add deposit and payout fields to daily_sales_summaries and pos_daily_sales_cache

Revision ID: 20260106_0001
Revises:
Create Date: 2026-01-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260106_0001'
down_revision: Union[str, None] = '20251228_0001_perf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new deposit and payout fields to daily_sales_summaries
    op.add_column('daily_sales_summaries',
        sa.Column('card_deposit', sa.Numeric(15, 2), nullable=True,
                  comment='Card payments (amount + tips - card refunds)'))

    op.add_column('daily_sales_summaries',
        sa.Column('cash_tips_paid', sa.Numeric(15, 2), nullable=True, server_default='0.00',
                  comment='Cash tips paid out to employees'))

    op.add_column('daily_sales_summaries',
        sa.Column('cash_payouts', sa.Numeric(15, 2), nullable=True, server_default='0.00',
                  comment='Cash payouts/adjustments (money taken from drawer)'))

    op.add_column('daily_sales_summaries',
        sa.Column('payout_breakdown', postgresql.JSONB, nullable=True,
                  comment='Details of each payout: [{"amount": 50.00, "note": "Bank run", "employee": "John"}]'))

    # Add new deposit and payout fields to pos_daily_sales_cache (POS cache table)
    op.add_column('pos_daily_sales_cache',
        sa.Column('card_deposit', sa.Numeric(12, 2), nullable=True,
                  comment='Card payments (amount + tips - card refunds)'))

    op.add_column('pos_daily_sales_cache',
        sa.Column('cash_tips_paid', sa.Numeric(12, 2), nullable=True, server_default='0.00',
                  comment='Cash tips paid out to employees'))

    op.add_column('pos_daily_sales_cache',
        sa.Column('cash_payouts', sa.Numeric(12, 2), nullable=True, server_default='0.00',
                  comment='Cash payouts/adjustments (money taken from drawer)'))

    op.add_column('pos_daily_sales_cache',
        sa.Column('expected_cash_deposit', sa.Numeric(12, 2), nullable=True,
                  comment='Cash Sales - Cash Tips - Payouts'))

    op.add_column('pos_daily_sales_cache',
        sa.Column('payout_breakdown', postgresql.JSONB, nullable=True,
                  comment='Details of each payout: [{"amount": 50.00, "note": "Bank run", "employee": "John"}]'))


def downgrade() -> None:
    # Remove from daily_sales_summaries
    op.drop_column('daily_sales_summaries', 'payout_breakdown')
    op.drop_column('daily_sales_summaries', 'cash_payouts')
    op.drop_column('daily_sales_summaries', 'cash_tips_paid')
    op.drop_column('daily_sales_summaries', 'card_deposit')

    # Remove from pos_daily_sales_cache
    op.drop_column('pos_daily_sales_cache', 'payout_breakdown')
    op.drop_column('pos_daily_sales_cache', 'expected_cash_deposit')
    op.drop_column('pos_daily_sales_cache', 'cash_payouts')
    op.drop_column('pos_daily_sales_cache', 'cash_tips_paid')
    op.drop_column('pos_daily_sales_cache', 'card_deposit')
