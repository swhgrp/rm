"""add discount breakdown to dss

Revision ID: 20251023_0800
Revises: 20251023_0700
Create Date: 2025-10-23 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251023_0800'
down_revision = '20251023_0700'
branch_labels = None
depends_on = None


def upgrade():
    # Add discount_breakdown JSONB column to daily_sales_summaries
    op.add_column('daily_sales_summaries', sa.Column('discount_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove discount_breakdown column
    op.drop_column('daily_sales_summaries', 'discount_breakdown')
