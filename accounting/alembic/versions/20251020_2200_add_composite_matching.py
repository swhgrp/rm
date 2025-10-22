"""Add composite matching for bank reconciliation Phase 1B

Revision ID: 20251020_2200
Revises: 20251020_0200
Create Date: 2025-10-20 22:00:00

This migration adds support for composite matching (many-to-one) where
one bank transaction can be matched to multiple journal entry lines.
This is essential for matching batch deposits to multiple DSS entries.

Example use case:
- Bank deposit: $1,550 (credit card batch)
- DSS Entry 1: $500 to GL 1090 (Day 1)
- DSS Entry 2: $600 to GL 1090 (Day 2)
- DSS Entry 3: $450 to GL 1090 (Day 3)
- Composite match: Link all 3 JE lines to the single bank transaction
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20251020_2200'
down_revision = '20251020_0200'
branch_labels = None
depends_on = None


def upgrade():
    # Create composite matching table
    op.create_table(
        'bank_transaction_composite_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=False),
        sa.Column('journal_entry_line_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('match_type', sa.String(length=50), nullable=True, comment='composite, partial, full'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance
    op.create_index(
        'ix_composite_matches_bank_transaction',
        'bank_transaction_composite_matches',
        ['bank_transaction_id']
    )
    op.create_index(
        'ix_composite_matches_je_line',
        'bank_transaction_composite_matches',
        ['journal_entry_line_id']
    )

    # Add foreign keys
    op.create_foreign_key(
        'fk_composite_matches_bank_transaction',
        'bank_transaction_composite_matches',
        'bank_transactions',
        ['bank_transaction_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_composite_matches_je_line',
        'bank_transaction_composite_matches',
        'journal_entry_lines',
        ['journal_entry_line_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_composite_matches_created_by',
        'bank_transaction_composite_matches',
        'users',
        ['created_by'],
        ['id'],
        ondelete='SET NULL'
    )

    # Add composite_match_id to bank_transactions to track if transaction is part of composite
    op.add_column(
        'bank_transactions',
        sa.Column('is_composite_match', sa.Boolean(), nullable=False, server_default='false',
                 comment='True if this transaction is matched to multiple JE lines')
    )

    # Add reconciliation_date to bank_statements if not exists
    # (checking if column exists first via execute)
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='bank_statements'
        AND column_name='reconciliation_date'
    """))

    if not result.fetchone():
        op.add_column(
            'bank_statements',
            sa.Column('reconciliation_date', sa.Date(), nullable=True,
                     comment='Date when reconciliation was completed')
        )

    # Add cleared_balance to bank_statements for tracking cleared transactions
    result = conn.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='bank_statements'
        AND column_name='cleared_balance'
    """))

    if not result.fetchone():
        op.add_column(
            'bank_statements',
            sa.Column('cleared_balance', sa.Numeric(precision=15, scale=2), nullable=True,
                     comment='Sum of all cleared transactions for this statement')
        )

    # Create a view for easy composite match querying
    op.execute("""
        CREATE OR REPLACE VIEW v_composite_match_summary AS
        SELECT
            bt.id as bank_transaction_id,
            bt.description,
            bt.amount as bank_amount,
            bt.transaction_date,
            COUNT(cm.id) as matched_lines_count,
            SUM(cm.amount) as total_matched_amount,
            bt.amount - COALESCE(SUM(cm.amount), 0) as difference
        FROM bank_transactions bt
        LEFT JOIN bank_transaction_composite_matches cm ON bt.id = cm.bank_transaction_id
        WHERE bt.is_composite_match = true
        GROUP BY bt.id, bt.description, bt.amount, bt.transaction_date
    """)


def downgrade():
    # Drop view
    op.execute("DROP VIEW IF EXISTS v_composite_match_summary")

    # Drop columns from bank_transactions
    op.drop_column('bank_transactions', 'is_composite_match')

    # Drop columns from bank_statements (check if they exist first)
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='bank_statements'
        AND column_name='cleared_balance'
    """))
    if result.fetchone():
        op.drop_column('bank_statements', 'cleared_balance')

    result = conn.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='bank_statements'
        AND column_name='reconciliation_date'
    """))
    if result.fetchone():
        op.drop_column('bank_statements', 'reconciliation_date')

    # Drop foreign keys
    op.drop_constraint('fk_composite_matches_created_by', 'bank_transaction_composite_matches', type_='foreignkey')
    op.drop_constraint('fk_composite_matches_je_line', 'bank_transaction_composite_matches', type_='foreignkey')
    op.drop_constraint('fk_composite_matches_bank_transaction', 'bank_transaction_composite_matches', type_='foreignkey')

    # Drop indexes
    op.drop_index('ix_composite_matches_je_line', table_name='bank_transaction_composite_matches')
    op.drop_index('ix_composite_matches_bank_transaction', table_name='bank_transaction_composite_matches')

    # Drop table
    op.drop_table('bank_transaction_composite_matches')
