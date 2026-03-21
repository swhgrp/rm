"""Add AI review fields to daily_sales_summaries

Adds review_status, review_notes, and reviewed_at fields for the
Claude Code automated DSS review and posting system.

Revision ID: 20260320_0002
Revises: 20260320_0001
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260320_0002'
down_revision = '20260320_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('daily_sales_summaries',
        sa.Column('review_status', sa.String(20), nullable=True, index=True))
    op.add_column('daily_sales_summaries',
        sa.Column('review_notes', postgresql.JSONB(), nullable=True))
    op.add_column('daily_sales_summaries',
        sa.Column('reviewed_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('daily_sales_summaries', 'reviewed_at')
    op.drop_column('daily_sales_summaries', 'review_notes')
    op.drop_column('daily_sales_summaries', 'review_status')
