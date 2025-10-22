"""Add amount ranges and recurring pattern tracking

Revision ID: 20251022_0200
Revises: 20251022_0100
Create Date: 2025-10-22 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_0200'
down_revision = '20251022_0100'
branch_labels = None
depends_on = None


def upgrade():
    # Add amount range tracking to vendor GL mappings
    op.add_column('vendor_gl_mappings', sa.Column('min_amount', sa.Numeric(15, 2), nullable=True))
    op.add_column('vendor_gl_mappings', sa.Column('max_amount', sa.Numeric(15, 2), nullable=True))
    op.add_column('vendor_gl_mappings', sa.Column('avg_amount', sa.Numeric(15, 2), nullable=True))

    # Add amount range tracking to pattern mappings
    op.add_column('description_pattern_mappings', sa.Column('min_amount', sa.Numeric(15, 2), nullable=True))
    op.add_column('description_pattern_mappings', sa.Column('max_amount', sa.Numeric(15, 2), nullable=True))
    op.add_column('description_pattern_mappings', sa.Column('avg_amount', sa.Numeric(15, 2), nullable=True))

    # Create recurring transaction patterns table
    op.create_table(
        'recurring_transaction_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('description_pattern', sa.String(255), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('expected_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('amount_variance', sa.Numeric(15, 2), nullable=True, server_default='0.00'),  # Acceptable variance
        sa.Column('frequency_days', sa.Integer(), nullable=True),  # Expected days between occurrences
        sa.Column('last_occurrence_date', sa.Date(), nullable=True),
        sa.Column('next_expected_date', sa.Date(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_recurring_patterns_description', 'recurring_transaction_patterns', ['description_pattern'])
    op.create_index('ix_recurring_patterns_vendor', 'recurring_transaction_patterns', ['vendor_id'])
    op.create_index('ix_recurring_patterns_next_date', 'recurring_transaction_patterns', ['next_expected_date'])

    # Foreign keys
    op.create_foreign_key('fk_recurring_patterns_vendor', 'recurring_transaction_patterns', 'vendors', ['vendor_id'], ['id'])
    op.create_foreign_key('fk_recurring_patterns_account', 'recurring_transaction_patterns', 'accounts', ['account_id'], ['id'])


def downgrade():
    op.drop_table('recurring_transaction_patterns')
    op.drop_column('description_pattern_mappings', 'avg_amount')
    op.drop_column('description_pattern_mappings', 'max_amount')
    op.drop_column('description_pattern_mappings', 'min_amount')
    op.drop_column('vendor_gl_mappings', 'avg_amount')
    op.drop_column('vendor_gl_mappings', 'max_amount')
    op.drop_column('vendor_gl_mappings', 'min_amount')
