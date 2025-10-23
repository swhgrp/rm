"""Add complete payment system

Revision ID: 20251022_2000
Revises: 20251022_1600
Create Date: 2025-10-22 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_2000'
down_revision = '20251022_1600'
branch_labels = None
depends_on = None


def upgrade():
    # Payment status enum (payment_method already exists from vendor_bills)
    op.execute("""
        CREATE TYPE payment_status AS ENUM (
            'DRAFT',
            'SCHEDULED',
            'PENDING',
            'PRINTED',
            'SUBMITTED',
            'CLEARED',
            'VOIDED',
            'CANCELLED',
            'STOPPED',
            'RETURNED'
        )
    """)

    # Check batches - for batch check printing
    op.create_table(
        'check_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(50), nullable=False),
        sa.Column('batch_date', sa.Date(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('starting_check_number', sa.Integer(), nullable=False),
        sa.Column('ending_check_number', sa.Integer(), nullable=True),
        sa.Column('check_count', sa.Integer(), nullable=False, default=0),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('status', sa.String(20), nullable=False, default='DRAFT'),
        sa.Column('printed_at', sa.DateTime(), nullable=True),
        sa.Column('printed_by', sa.Integer(), nullable=True),
        sa.Column('pdf_file_path', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id']),
        sa.ForeignKeyConstraint(['printed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_number')
    )
    op.create_index('idx_check_batches_date', 'check_batches', ['batch_date'])
    op.create_index('idx_check_batches_status', 'check_batches', ['status'])

    # ACH batches - for electronic payments
    op.create_table(
        'ach_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(50), nullable=False),
        sa.Column('batch_date', sa.Date(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('payment_count', sa.Integer(), nullable=False, default=0),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('status', sa.String(20), nullable=False, default='DRAFT'),
        sa.Column('nacha_file_path', sa.String(500), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('generated_by', sa.Integer(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('submitted_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id']),
        sa.ForeignKeyConstraint(['generated_by'], ['users.id']),
        sa.ForeignKeyConstraint(['submitted_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_number')
    )
    op.create_index('idx_ach_batches_date', 'ach_batches', ['batch_date'])
    op.create_index('idx_ach_batches_status', 'ach_batches', ['status'])

    # Payments - main payment records
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_number', sa.String(50), nullable=False),
        sa.Column('payment_method', postgresql.ENUM('CHECK', 'ACH', 'WIRE', 'CREDIT_CARD', 'DEBIT_CARD', 'CASH', 'OTHER', name='paymentmethod', create_type=False), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('discount_amount', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('net_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('status', postgresql.ENUM('DRAFT', 'SCHEDULED', 'PENDING', 'PRINTED', 'SUBMITTED', 'CLEARED', 'VOIDED', 'CANCELLED', 'STOPPED', 'RETURNED', name='payment_status', create_type=False), nullable=False, default='DRAFT'),

        # Check-specific fields
        sa.Column('check_number', sa.Integer(), nullable=True),
        sa.Column('check_batch_id', sa.Integer(), nullable=True),

        # ACH-specific fields
        sa.Column('ach_batch_id', sa.Integer(), nullable=True),
        sa.Column('ach_trace_number', sa.String(50), nullable=True),

        # Wire/Other fields
        sa.Column('reference_number', sa.String(100), nullable=True),
        sa.Column('confirmation_number', sa.String(100), nullable=True),

        # Dates
        sa.Column('scheduled_date', sa.Date(), nullable=True),
        sa.Column('cleared_date', sa.Date(), nullable=True),
        sa.Column('voided_date', sa.Date(), nullable=True),

        # GL integration
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),

        # Metadata
        sa.Column('memo', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('void_reason', sa.Text(), nullable=True),

        # Audit
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('voided_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id']),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id']),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id']),
        sa.ForeignKeyConstraint(['check_batch_id'], ['check_batches.id']),
        sa.ForeignKeyConstraint(['ach_batch_id'], ['ach_batches.id']),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['voided_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_number'),
        sa.UniqueConstraint('bank_account_id', 'check_number', name='uq_bank_check_number')
    )
    op.create_index('idx_payments_vendor', 'payments', ['vendor_id'])
    op.create_index('idx_payments_date', 'payments', ['payment_date'])
    op.create_index('idx_payments_status', 'payments', ['status'])
    op.create_index('idx_payments_method', 'payments', ['payment_method'])
    op.create_index('idx_payments_check', 'payments', ['bank_account_id', 'check_number'])

    # Payment applications - link payments to bills
    op.create_table(
        'payment_applications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('vendor_bill_id', sa.Integer(), nullable=False),
        sa.Column('amount_applied', sa.Numeric(15, 2), nullable=False),
        sa.Column('discount_applied', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vendor_bill_id'], ['vendor_bills.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_apps_payment', 'payment_applications', ['payment_id'])
    op.create_index('idx_payment_apps_bill', 'payment_applications', ['vendor_bill_id'])

    # Check number registry - track all check numbers
    op.create_table(
        'check_number_registry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('check_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),  # USED, VOIDED, CANCELLED, SKIPPED
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('used_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_account_id', 'check_number')
    )
    op.create_index('idx_check_registry_bank', 'check_number_registry', ['bank_account_id'])
    op.create_index('idx_check_registry_status', 'check_number_registry', ['status'])

    # Payment schedules - for recurring/scheduled payments
    op.create_table(
        'payment_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_name', sa.String(200), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('payment_method', postgresql.ENUM('CHECK', 'ACH', 'WIRE', 'CREDIT_CARD', 'DEBIT_CARD', 'CASH', 'OTHER', name='paymentmethod', create_type=False), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('frequency', sa.String(20), nullable=False),  # WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('next_payment_date', sa.Date(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('auto_approve', sa.Boolean(), nullable=False, default=False),
        sa.Column('memo_template', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id']),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_schedules_vendor', 'payment_schedules', ['vendor_id'])
    op.create_index('idx_payment_schedules_next', 'payment_schedules', ['next_payment_date'])

    # Payment approval workflow
    op.create_table(
        'payment_approvals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('approver_id', sa.Integer(), nullable=False),
        sa.Column('approval_status', sa.String(20), nullable=False),  # PENDING, APPROVED, REJECTED
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approver_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_approvals_payment', 'payment_approvals', ['payment_id'])
    op.create_index('idx_payment_approvals_status', 'payment_approvals', ['approval_status'])

    # Early payment discounts
    op.create_table(
        'payment_discounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_bill_id', sa.Integer(), nullable=False),
        sa.Column('discount_terms', sa.String(50), nullable=False),  # e.g., "2/10 Net 30"
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('discount_days', sa.Integer(), nullable=False),
        sa.Column('discount_deadline', sa.Date(), nullable=False),
        sa.Column('max_discount_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('discount_taken', sa.Numeric(15, 2), nullable=False, default=0),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('taken_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['vendor_bill_id'], ['vendor_bills.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_discounts_bill', 'payment_discounts', ['vendor_bill_id'])
    op.create_index('idx_payment_discounts_deadline', 'payment_discounts', ['discount_deadline'])


def downgrade():
    op.drop_table('payment_discounts')
    op.drop_table('payment_approvals')
    op.drop_table('payment_schedules')
    op.drop_table('check_number_registry')
    op.drop_table('payment_applications')
    op.drop_table('payments')
    op.drop_table('ach_batches')
    op.drop_table('check_batches')
    op.execute('DROP TYPE payment_status')
