"""Add Accounts Payable tables

Revision ID: 20251018_0004
Revises: 20251018_0003
Create Date: 2025-10-18 21:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251018_0004'
down_revision = '20251018_0003'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create Accounts Payable tables:
    - vendor_bills: Main bill/invoice records
    - vendor_bill_lines: Line items for bills
    - bill_payments: Payment records
    """

    # Create vendor_bills table
    op.create_table('vendor_bills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_name', sa.String(length=200), nullable=False),
        sa.Column('vendor_id', sa.String(length=50), nullable=True),
        sa.Column('bill_number', sa.String(length=100), nullable=False),
        sa.Column('bill_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('received_date', sa.Date(), nullable=True),
        sa.Column('subtotal', sa.DECIMAL(precision=15, scale=2), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.DECIMAL(precision=15, scale=2), nullable=False, server_default='0'),
        sa.Column('total_amount', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('paid_amount', sa.DECIMAL(precision=15, scale=2), nullable=False, server_default='0'),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PARTIALLY_PAID', 'PAID', 'VOID', name='billstatus'), nullable=False, server_default='DRAFT'),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_date', sa.DateTime(), nullable=True),
        sa.Column('approval_notes', sa.Text(), nullable=True),
        sa.Column('is_1099_eligible', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for vendor_bills
    op.create_index('ix_vendor_bills_id', 'vendor_bills', ['id'])
    op.create_index('ix_vendor_bills_vendor_name', 'vendor_bills', ['vendor_name'])
    op.create_index('ix_vendor_bills_vendor_id', 'vendor_bills', ['vendor_id'])
    op.create_index('ix_vendor_bills_bill_number', 'vendor_bills', ['bill_number'])
    op.create_index('ix_vendor_bills_bill_date', 'vendor_bills', ['bill_date'])
    op.create_index('ix_vendor_bills_due_date', 'vendor_bills', ['due_date'])
    op.create_index('ix_vendor_bills_area_id', 'vendor_bills', ['area_id'])
    op.create_index('ix_vendor_bills_status', 'vendor_bills', ['status'])

    # Create vendor_bill_lines table
    op.create_table('vendor_bill_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('unit_price', sa.DECIMAL(precision=15, scale=2), nullable=True),
        sa.Column('amount', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('is_taxable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tax_amount', sa.DECIMAL(precision=15, scale=2), nullable=False, server_default='0'),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['bill_id'], ['vendor_bills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for vendor_bill_lines
    op.create_index('ix_vendor_bill_lines_id', 'vendor_bill_lines', ['id'])
    op.create_index('ix_vendor_bill_lines_bill_id', 'vendor_bill_lines', ['bill_id'])
    op.create_index('ix_vendor_bill_lines_area_id', 'vendor_bill_lines', ['area_id'])

    # Create bill_payments table
    op.create_table('bill_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column('payment_method', sa.Enum('CHECK', 'ACH', 'WIRE', 'CREDIT_CARD', 'DEBIT_CARD', 'CASH', 'OTHER', name='paymentmethod'), nullable=False),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['bank_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['bill_id'], ['vendor_bills.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for bill_payments
    op.create_index('ix_bill_payments_id', 'bill_payments', ['id'])
    op.create_index('ix_bill_payments_bill_id', 'bill_payments', ['bill_id'])
    op.create_index('ix_bill_payments_payment_date', 'bill_payments', ['payment_date'])
    op.create_index('ix_bill_payments_reference_number', 'bill_payments', ['reference_number'])


def downgrade():
    """Remove Accounts Payable tables"""

    # Drop indexes
    op.drop_index('ix_bill_payments_reference_number', table_name='bill_payments')
    op.drop_index('ix_bill_payments_payment_date', table_name='bill_payments')
    op.drop_index('ix_bill_payments_bill_id', table_name='bill_payments')
    op.drop_index('ix_bill_payments_id', table_name='bill_payments')

    op.drop_index('ix_vendor_bill_lines_area_id', table_name='vendor_bill_lines')
    op.drop_index('ix_vendor_bill_lines_bill_id', table_name='vendor_bill_lines')
    op.drop_index('ix_vendor_bill_lines_id', table_name='vendor_bill_lines')

    op.drop_index('ix_vendor_bills_status', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_area_id', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_due_date', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_bill_date', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_bill_number', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_vendor_id', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_vendor_name', table_name='vendor_bills')
    op.drop_index('ix_vendor_bills_id', table_name='vendor_bills')

    # Drop tables
    op.drop_table('bill_payments')
    op.drop_table('vendor_bill_lines')
    op.drop_table('vendor_bills')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS paymentmethod')
    op.execute('DROP TYPE IF EXISTS billstatus')
