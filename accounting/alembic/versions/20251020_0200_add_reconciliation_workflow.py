"""add reconciliation workflow

Revision ID: 20251020_0200
Revises: 20251020_0001
Create Date: 2025-10-20 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251020_0200'
down_revision = '20251020_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Bank statements table (monthly periods with workflow status)
    op.create_table(
        'bank_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('statement_period_start', sa.Date(), nullable=False),
        sa.Column('statement_period_end', sa.Date(), nullable=False),
        sa.Column('statement_date', sa.Date(), nullable=False, comment='Official statement date from bank'),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('closing_balance', sa.Numeric(15, 2), nullable=False),

        # Workflow status
        sa.Column('status', sa.String(20), nullable=False, server_default='draft',
                  comment='draft, in_progress, reconciled, locked'),
        sa.Column('gl_balance', sa.Numeric(15, 2), nullable=True, comment='Calculated GL balance'),
        sa.Column('difference', sa.Numeric(15, 2), nullable=True, comment='Bank vs GL difference'),

        # Reconciliation tracking
        sa.Column('reconciled_by', sa.Integer(), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(), nullable=True),
        sa.Column('locked_by', sa.Integer(), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('locked_reason', sa.Text(), nullable=True),

        # Audit trail
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reconciled_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['locked_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_statements_account', 'bank_statements', ['bank_account_id'])
    op.create_index('ix_bank_statements_period', 'bank_statements', ['statement_period_start', 'statement_period_end'])
    op.create_index('ix_bank_statements_status', 'bank_statements', ['status'])

    # Add statement_id to bank_transactions
    op.add_column('bank_transactions',
                  sa.Column('statement_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_bank_transactions_statement', 'bank_transactions', 'bank_statements',
                          ['statement_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_bank_transactions_statement', 'bank_transactions', ['statement_id'])

    # Add fields for suggested matches to bank_transactions
    op.add_column('bank_transactions',
                  sa.Column('suggested_account_id', sa.Integer(), nullable=True,
                            comment='Suggested GL account from matching engine'))
    op.add_column('bank_transactions',
                  sa.Column('suggested_by_rule_id', sa.Integer(), nullable=True,
                            comment='Rule that suggested this match'))
    op.add_column('bank_transactions',
                  sa.Column('suggestion_confidence', sa.Numeric(5, 2), nullable=True,
                            comment='Confidence score 0-100'))
    op.add_column('bank_transactions',
                  sa.Column('confirmed_by', sa.Integer(), nullable=True,
                            comment='User who confirmed the match'))
    op.add_column('bank_transactions',
                  sa.Column('confirmed_at', sa.DateTime(), nullable=True))

    op.create_foreign_key('fk_bank_transactions_suggested_account', 'bank_transactions', 'accounts',
                          ['suggested_account_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_bank_transactions_suggested_rule', 'bank_transactions', 'bank_matching_rules',
                          ['suggested_by_rule_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_bank_transactions_confirmed_by', 'bank_transactions', 'users',
                          ['confirmed_by'], ['id'], ondelete='SET NULL')

    # Bank transaction matches table (audit trail for all matches, including composites)
    op.create_table(
        'bank_transaction_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=False),
        sa.Column('journal_entry_line_id', sa.Integer(), nullable=True,
                  comment='GL line being matched (can be null for expense categorization)'),

        # Match metadata
        sa.Column('match_type', sa.String(50), nullable=False,
                  comment='exact, fuzzy, composite, manual, rule_based'),
        sa.Column('confidence_score', sa.Numeric(5, 2), nullable=True, comment='0-100'),
        sa.Column('match_reason', sa.Text(), nullable=True, comment='Human-readable explanation'),
        sa.Column('amount_difference', sa.Numeric(15, 2), nullable=True, comment='Difference for fee calc'),
        sa.Column('date_difference', sa.Integer(), nullable=True, comment='Days between bank and GL date'),

        # Rule and confirmation
        sa.Column('matched_by_rule_id', sa.Integer(), nullable=True),
        sa.Column('confirmed_by', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),

        # Clearing journal entry (created when match is finalized)
        sa.Column('clearing_journal_entry_id', sa.Integer(), nullable=True,
                  comment='JE created to clear Undeposited Funds'),
        sa.Column('adjustment_journal_entry_id', sa.Integer(), nullable=True,
                  comment='JE created for fees/commissions'),

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending, confirmed, cleared, rejected'),

        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_line_id'], ['journal_entry_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['matched_by_rule_id'], ['bank_matching_rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['clearing_journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['adjustment_journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_transaction_matches_bank_txn', 'bank_transaction_matches', ['bank_transaction_id'])
    op.create_index('ix_bank_transaction_matches_status', 'bank_transaction_matches', ['status'])
    op.create_index('ix_bank_transaction_matches_je_line', 'bank_transaction_matches', ['journal_entry_line_id'])

    # Composite matches (many-to-one or one-to-many relationships)
    op.create_table(
        'bank_composite_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_group_id', sa.String(50), nullable=False, comment='UUID to group related matches'),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True,
                  comment='Bank txn (null if many bank to one GL)'),
        sa.Column('journal_entry_line_id', sa.Integer(), nullable=True,
                  comment='GL line (null if one bank to many GL)'),
        sa.Column('match_amount', sa.Numeric(15, 2), nullable=False,
                  comment='Portion of amount matched'),
        sa.Column('composite_type', sa.String(50), nullable=False,
                  comment='many_to_one, one_to_many'),

        sa.Column('confirmed_by', sa.Integer(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),

        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_line_id'], ['journal_entry_lines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_composite_matches_group', 'bank_composite_matches', ['match_group_id'])
    op.create_index('ix_bank_composite_matches_bank_txn', 'bank_composite_matches', ['bank_transaction_id'])
    op.create_index('ix_bank_composite_matches_je_line', 'bank_composite_matches', ['journal_entry_line_id'])

    # Enhanced matching rules with JSON conditions
    op.create_table(
        'bank_matching_rules_v2',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=True, comment='Null = applies to all accounts'),
        sa.Column('area_id', sa.Integer(), nullable=True, comment='Null = applies to all areas'),
        sa.Column('rule_name', sa.String(255), nullable=False),
        sa.Column('rule_type', sa.String(50), nullable=False,
                  comment='recurring_deposit, recurring_expense, vendor_match, composite_match'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),

        # Conditions (flexible JSON structure)
        sa.Column('conditions', postgresql.JSONB(), nullable=False,
                  comment='Example: {"description_contains": "CHEVRON", "amount_min": 40, "amount_max": 60}'),

        # Actions
        sa.Column('action_type', sa.String(50), nullable=False,
                  comment='suggest_gl_account, auto_match, create_expense'),
        sa.Column('target_account_id', sa.Integer(), nullable=True, comment='GL account to use'),
        sa.Column('requires_confirmation', sa.Boolean(), nullable=False, server_default='true'),

        # Fee/adjustment handling
        sa.Column('fee_account_id', sa.Integer(), nullable=True, comment='GL account for fees'),
        sa.Column('fee_calculation', sa.String(50), nullable=True,
                  comment='fixed_amount, percentage, difference'),
        sa.Column('fee_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('fee_percentage', sa.Numeric(5, 2), nullable=True),

        # Statistics and status
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('times_suggested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_confirmed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),

        # Metadata
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['target_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['fee_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_matching_rules_v2_account', 'bank_matching_rules_v2', ['bank_account_id'])
    op.create_index('ix_bank_matching_rules_v2_area', 'bank_matching_rules_v2', ['area_id'])
    op.create_index('ix_bank_matching_rules_v2_active', 'bank_matching_rules_v2', ['active'])
    op.create_index('ix_bank_matching_rules_v2_priority', 'bank_matching_rules_v2', ['priority'])
    op.create_index('ix_bank_matching_rules_v2_type', 'bank_matching_rules_v2', ['rule_type'])

    # Statement snapshots (immutable audit trail)
    op.create_table(
        'bank_statement_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('statement_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_type', sa.String(50), nullable=False,
                  comment='reconciled, locked, unlocked, edited'),
        sa.Column('snapshot_data', postgresql.JSONB(), nullable=False,
                  comment='Full state including all matches and balances'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('reason', sa.Text(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['statement_id'], ['bank_statements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_bank_statement_snapshots_statement', 'bank_statement_snapshots', ['statement_id'])
    op.create_index('ix_bank_statement_snapshots_type', 'bank_statement_snapshots', ['snapshot_type'])


def downgrade():
    op.drop_table('bank_statement_snapshots')
    op.drop_table('bank_matching_rules_v2')
    op.drop_table('bank_composite_matches')
    op.drop_table('bank_transaction_matches')

    # Remove added columns from bank_transactions
    op.drop_constraint('fk_bank_transactions_confirmed_by', 'bank_transactions', type_='foreignkey')
    op.drop_constraint('fk_bank_transactions_suggested_rule', 'bank_transactions', type_='foreignkey')
    op.drop_constraint('fk_bank_transactions_suggested_account', 'bank_transactions', type_='foreignkey')
    op.drop_constraint('fk_bank_transactions_statement', 'bank_transactions', type_='foreignkey')
    op.drop_index('ix_bank_transactions_statement', 'bank_transactions')
    op.drop_column('bank_transactions', 'confirmed_at')
    op.drop_column('bank_transactions', 'confirmed_by')
    op.drop_column('bank_transactions', 'suggestion_confidence')
    op.drop_column('bank_transactions', 'suggested_by_rule_id')
    op.drop_column('bank_transactions', 'suggested_account_id')
    op.drop_column('bank_transactions', 'statement_id')

    op.drop_table('bank_statements')
