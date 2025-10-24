"""Add total_refunds to pos_daily_sales_cache

Revision ID: 20251023_1500
Revises: 20251023_1400
Create Date: 2025-10-23 15:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251023_1500'
down_revision = '20251023_1400'
branch_labels = None
depends_on = None


def upgrade():
    # Add total_refunds column to pos_daily_sales_cache
    op.add_column(
        'pos_daily_sales_cache',
        sa.Column('total_refunds', sa.Numeric(12, 2), nullable=False, server_default='0')
    )


def downgrade():
    # Remove total_refunds column
    op.drop_column('pos_daily_sales_cache', 'total_refunds')
