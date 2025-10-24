"""add discounts to pos cache

Revision ID: 20251023_0600
Revises: 20251023_0100
Create Date: 2025-10-23 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251023_0600'
down_revision = '20251023_0100'
branch_labels = None
depends_on = None


def upgrade():
    # Add discounts JSONB column to pos_daily_sales_cache
    op.add_column('pos_daily_sales_cache', sa.Column('discounts', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove discounts column
    op.drop_column('pos_daily_sales_cache', 'discounts')
