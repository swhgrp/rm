"""add banking module

Revision ID: 20251020_0001
Revises: 20251019_1600
Create Date: 2025-10-20 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251020_0001'
down_revision = '20251019_1600'
branch_labels = None
depends_on = None


def upgrade():
    # Bank accounts table
    op.create_table(
        'bank_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('account_name', sa.String(255), nullable=False),
        sa.Column('account_number', sa.String(50), nullable=True),
        sa.Column('account_type', sa.String(50), nullable=True, comment='checking, savings, credit_card, money_market, line_of_credit'),
        sa.Column('institution_name', sa.String(255), nullable=True),
        sa.Column('routing_number', sa.String(20), nullable=True),
        sa.Column('gl_account_id', sa.Integer(), nullable=True, comment='Link to cash/bank GL account'),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('current_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),

        # Sync configuration
        sa.Column('sync_method', sa.String(20), nullable=False, server_default='manual', comment='manual, plaid, api'),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_sync_date', sa.DateTime(), nullable=True),

        # Plaid integration fields (encrypted in application layer)
        sa.Column('plaid_access_token', sa.Text(), nullable=True),
        sa.Column('plaid_item_id', sa.String(255), nullable=True),
        sa.Column('plaid_account_id', sa.String(255), nullable=True),

        # Metadata
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['gl_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_accounts_area_id', 'bank_accounts', ['area_id'])
    op.create_index('ix_bank_accounts_status', 'bank_accounts', ['status'])

    # Bank statement imports table
    op.create_table(
        'bank_statement_imports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('import_date', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('file_format', sa.String(20), nullable=True, comment='csv, ofx, qfx, qbo'),
        sa.Column('import_method', sa.String(20), nullable=False, server_default='manual', comment='manual, plaid, scheduled'),
        sa.Column('statement_date', sa.Date(), nullable=True),
        sa.Column('beginning_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('ending_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('transaction_count', sa.Integer(), nullable=True),
        sa.Column('imported_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imported_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_statement_imports_account', 'bank_statement_imports', ['bank_account_id'])
    op.create_index('ix_bank_statement_imports_date', 'bank_statement_imports', ['import_date'])

    # Bank transactions table (from statements)
    op.create_table(
        'bank_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('import_id', sa.Integer(), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('post_date', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('payee', sa.String(255), nullable=True),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=True, comment='debit, credit, check, atm, pos, transfer, fee, interest'),
        sa.Column('check_number', sa.String(50), nullable=True),
        sa.Column('reference_number', sa.String(100), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('memo', sa.Text(), nullable=True),

        # Reconciliation status
        sa.Column('status', sa.String(20), nullable=False, server_default='unreconciled', comment='unreconciled, reconciled, voided'),
        sa.Column('reconciled_date', sa.Date(), nullable=True),

        # Matching information
        sa.Column('matched_journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('matched_journal_line_id', sa.Integer(), nullable=True),
        sa.Column('match_type', sa.String(50), nullable=True, comment='exact, fuzzy, manual, auto'),
        sa.Column('match_confidence', sa.Numeric(5, 2), nullable=True, comment='0.00 to 100.00'),

        # Plaid-specific fields
        sa.Column('plaid_transaction_id', sa.String(255), nullable=True),
        sa.Column('plaid_category', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('plaid_pending', sa.Boolean(), nullable=True),

        # Metadata
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['import_id'], ['bank_statement_imports.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_journal_line_id'], ['journal_entry_lines.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_transactions_account', 'bank_transactions', ['bank_account_id'])
    op.create_index('ix_bank_transactions_date', 'bank_transactions', ['transaction_date'])
    op.create_index('ix_bank_transactions_status', 'bank_transactions', ['status'])
    op.create_index('ix_bank_transactions_plaid_id', 'bank_transactions', ['plaid_transaction_id'])

    # Bank reconciliations table
    op.create_table(
        'bank_reconciliations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('reconciliation_date', sa.Date(), nullable=False),
        sa.Column('statement_date', sa.Date(), nullable=False),
        sa.Column('beginning_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('ending_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('cleared_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('book_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('difference', sa.Numeric(15, 2), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='in_progress', comment='in_progress, balanced, locked'),
        sa.Column('reconciled_by', sa.Integer(), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(), nullable=True),
        sa.Column('locked_by', sa.Integer(), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reconciled_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['locked_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_reconciliations_account', 'bank_reconciliations', ['bank_account_id'])
    op.create_index('ix_bank_reconciliations_date', 'bank_reconciliations', ['reconciliation_date'])
    op.create_index('ix_bank_reconciliations_status', 'bank_reconciliations', ['status'])

    # Bank reconciliation items table (cleared transactions)
    op.create_table(
        'bank_reconciliation_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reconciliation_id', sa.Integer(), nullable=False),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('journal_entry_line_id', sa.Integer(), nullable=True),
        sa.Column('cleared_date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('item_type', sa.String(50), nullable=True, comment='bank_transaction, journal_entry, adjustment'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reconciliation_id'], ['bank_reconciliations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_line_id'], ['journal_entry_lines.id'], ondelete='CASCADE')
    )
    op.create_index('ix_bank_reconciliation_items_recon', 'bank_reconciliation_items', ['reconciliation_id'])

    # Bank matching rules table (for auto-categorization)
    op.create_table(
        'bank_matching_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('rule_name', sa.String(255), nullable=False),
        sa.Column('match_field', sa.String(50), nullable=False, comment='description, payee, amount, check_number'),
        sa.Column('match_operator', sa.String(20), nullable=False, comment='contains, equals, starts_with, ends_with, regex, greater_than, less_than'),
        sa.Column('match_value', sa.Text(), nullable=False),
        sa.Column('target_account_id', sa.Integer(), nullable=True),
        sa.Column('target_payee', sa.String(255), nullable=True),
        sa.Column('auto_apply', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_matching_rules_account', 'bank_matching_rules', ['bank_account_id'])
    op.create_index('ix_bank_matching_rules_active', 'bank_matching_rules', ['active'])
    op.create_index('ix_bank_matching_rules_priority', 'bank_matching_rules', ['priority'])


def downgrade():
    op.drop_table('bank_matching_rules')
    op.drop_table('bank_reconciliation_items')
    op.drop_table('bank_reconciliations')
    op.drop_table('bank_transactions')
    op.drop_table('bank_statement_imports')
    op.drop_table('bank_accounts')
