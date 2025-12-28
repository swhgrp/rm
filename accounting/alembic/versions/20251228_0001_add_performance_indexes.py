"""Add performance indexes for commonly queried columns

Revision ID: 20251228_0001_perf
Revises: 20251129_add_vendor_aliases
Create Date: 2025-12-28

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20251228_0001_perf'
down_revision = '20251129_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    from alembic import op

    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # Vendor bills - frequently queried by status, vendor, date
    if 'vendor_bills' in existing_tables:
        op.create_index('ix_vendor_bills_status', 'vendor_bills', ['status'], unique=False, if_not_exists=True)
        op.create_index('ix_vendor_bills_due_date', 'vendor_bills', ['due_date'], unique=False, if_not_exists=True)
        op.create_index('ix_vendor_bills_vendor_status', 'vendor_bills', ['vendor_id', 'status'], unique=False, if_not_exists=True)

    # Payments - frequently queried by status, date, vendor
    if 'payments' in existing_tables:
        op.create_index('ix_payments_status', 'payments', ['status'], unique=False, if_not_exists=True)
        op.create_index('ix_payments_date', 'payments', ['payment_date'], unique=False, if_not_exists=True)
        op.create_index('ix_payments_vendor_date', 'payments', ['vendor_id', 'payment_date'], unique=False, if_not_exists=True)

    # Journal entries - frequently queried by date and status
    if 'journal_entries' in existing_tables:
        op.create_index('ix_journal_entries_date', 'journal_entries', ['entry_date'], unique=False, if_not_exists=True)
        op.create_index('ix_journal_entries_status', 'journal_entries', ['status'], unique=False, if_not_exists=True)

    # Journal entry lines - frequently queried by account and area
    if 'journal_entry_lines' in existing_tables:
        op.create_index('ix_journal_entry_lines_account', 'journal_entry_lines', ['account_id'], unique=False, if_not_exists=True)
        op.create_index('ix_journal_entry_lines_area', 'journal_entry_lines', ['area_id'], unique=False, if_not_exists=True)

    # Bank statement lines - frequently queried by reconciliation status
    if 'bank_statement_lines' in existing_tables:
        op.create_index('ix_bank_statement_lines_reconciled', 'bank_statement_lines', ['is_reconciled'], unique=False, if_not_exists=True)
        op.create_index('ix_bank_statement_lines_matched', 'bank_statement_lines', ['is_matched'], unique=False, if_not_exists=True)


def downgrade() -> None:
    # Use IF EXISTS for safe downgrade
    op.execute('DROP INDEX IF EXISTS ix_bank_statement_lines_matched')
    op.execute('DROP INDEX IF EXISTS ix_bank_statement_lines_reconciled')
    op.execute('DROP INDEX IF EXISTS ix_journal_entry_lines_area')
    op.execute('DROP INDEX IF EXISTS ix_journal_entry_lines_account')
    op.execute('DROP INDEX IF EXISTS ix_journal_entries_status')
    op.execute('DROP INDEX IF EXISTS ix_journal_entries_date')
    op.execute('DROP INDEX IF EXISTS ix_payments_vendor_date')
    op.execute('DROP INDEX IF EXISTS ix_payments_date')
    op.execute('DROP INDEX IF EXISTS ix_payments_status')
    op.execute('DROP INDEX IF EXISTS ix_vendor_bills_vendor_status')
    op.execute('DROP INDEX IF EXISTS ix_vendor_bills_due_date')
    op.execute('DROP INDEX IF EXISTS ix_vendor_bills_status')
