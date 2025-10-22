"""Add GL learning tables for intelligent suggestions

Revision ID: 20251022_0100
Revises: 20251020_2200
Create Date: 2025-10-22 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_0100'
down_revision = '20251020_2200'
branch_labels = None
depends_on = None


def upgrade():
    # Create vendor_gl_mappings table
    op.create_table(
        'vendor_gl_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('times_accepted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_rejected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_date', sa.Date(), nullable=True),
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vendor_gl_mappings_vendor_id', 'vendor_gl_mappings', ['vendor_id'])
    op.create_index('ix_vendor_gl_mappings_account_id', 'vendor_gl_mappings', ['account_id'])
    op.create_index('ix_vendor_gl_mappings_confidence', 'vendor_gl_mappings', ['confidence_score'])

    # Foreign keys
    op.create_foreign_key('fk_vendor_gl_mappings_vendor', 'vendor_gl_mappings', 'vendors', ['vendor_id'], ['id'])
    op.create_foreign_key('fk_vendor_gl_mappings_account', 'vendor_gl_mappings', 'accounts', ['account_id'], ['id'])

    # Unique constraint: one mapping per vendor-account pair
    op.create_unique_constraint('uq_vendor_account', 'vendor_gl_mappings', ['vendor_id', 'account_id'])

    # Create description_pattern_mappings table
    op.create_table(
        'description_pattern_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.String(255), nullable=False),
        sa.Column('pattern_type', sa.String(50), nullable=False, server_default='keyword'),  # keyword, prefix, suffix, regex
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('times_accepted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_rejected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_description_pattern_mappings_pattern', 'description_pattern_mappings', ['pattern'])
    op.create_index('ix_description_pattern_mappings_account_id', 'description_pattern_mappings', ['account_id'])
    op.create_index('ix_description_pattern_mappings_confidence', 'description_pattern_mappings', ['confidence_score'])

    # Foreign key
    op.create_foreign_key('fk_description_pattern_mappings_account', 'description_pattern_mappings', 'accounts', ['account_id'], ['id'])

    # Unique constraint: one mapping per pattern-account pair
    op.create_unique_constraint('uq_pattern_account', 'description_pattern_mappings', ['pattern', 'account_id'])


def downgrade():
    op.drop_table('description_pattern_mappings')
    op.drop_table('vendor_gl_mappings')
