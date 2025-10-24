"""add actual cash deposit fields

Revision ID: 20251023_1000
Revises:
Create Date: 2025-10-23 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251023_1000'
down_revision = '20251023_0900'  # Latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Add fields for cash reconciliation
    op.add_column('daily_sales_summaries', sa.Column('expected_cash_deposit', sa.Numeric(15, 2), nullable=True, comment='Expected cash deposit from POS'))
    op.add_column('daily_sales_summaries', sa.Column('actual_cash_deposit', sa.Numeric(15, 2), nullable=True, comment='Actual cash deposited (entered by manager)'))
    op.add_column('daily_sales_summaries', sa.Column('cash_variance', sa.Numeric(15, 2), nullable=True, comment='Actual - Expected cash'))
    op.add_column('daily_sales_summaries', sa.Column('cash_reconciled_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
    op.add_column('daily_sales_summaries', sa.Column('cash_reconciled_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('daily_sales_summaries', 'cash_reconciled_at')
    op.drop_column('daily_sales_summaries', 'cash_reconciled_by')
    op.drop_column('daily_sales_summaries', 'cash_variance')
    op.drop_column('daily_sales_summaries', 'actual_cash_deposit')
    op.drop_column('daily_sales_summaries', 'expected_cash_deposit')
