"""Add vendor alias learning fields

Add confidence, match_count, last_used_at, and created_by columns
to the vendor_aliases table to support persistent vendor alias learning.

Revision ID: 20260224_0001
Revises: 20260213_0002
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260224_0001'
down_revision = '20260213_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add learning fields to vendor_aliases
    op.add_column('vendor_aliases',
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('vendor_aliases',
        sa.Column('match_count', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('vendor_aliases',
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vendor_aliases',
        sa.Column('created_by', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('vendor_aliases', 'created_by')
    op.drop_column('vendor_aliases', 'last_used_at')
    op.drop_column('vendor_aliases', 'match_count')
    op.drop_column('vendor_aliases', 'confidence')
