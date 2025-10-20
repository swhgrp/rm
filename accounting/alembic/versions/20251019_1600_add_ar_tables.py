"""add AR tables (customers and invoices)

Revision ID: 20251019_1600
Revises: 20251019_1500
Create Date: 2025-10-19 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251019_1600'
down_revision = '20251019_1500'
branch_labels = None
depends_on = None


def upgrade():
    # Create customers table
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_name', sa.String(length=200), nullable=False),
        sa.Column('customer_code', sa.String(length=50), nullable=True),
        sa.Column('customer_type', sa.String(length=50), nullable=True),
        sa.Column('contact_name', sa.String(length=200), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('mobile', sa.String(length=20), nullable=True),
        sa.Column('fax', sa.String(length=20), nullable=True),
        sa.Column('website', sa.String(length=200), nullable=True),
        sa.Column('address_line1', sa.String(length=200), nullable=True),
        sa.Column('address_line2', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('zip_code', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True, server_default='United States'),
        sa.Column('billing_email', sa.String(length=100), nullable=True),
        sa.Column('billing_contact', sa.String(length=200), nullable=True),
        sa.Column('tax_exempt', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tax_exempt_id', sa.String(length=50), nullable=True),
        sa.Column('tax_rate', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('payment_terms', sa.String(length=50), nullable=True),
        sa.Column('credit_limit', sa.DECIMAL(15, 2), nullable=True),
        sa.Column('discount_percentage', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customers_id', 'customers', ['id'])
    op.create_index('ix_customers_customer_name', 'customers', ['customer_name'], unique=True)
    op.create_index('ix_customers_customer_code', 'customers', ['customer_code'], unique=True)

    # Create customer_invoices table
    op.create_table(
        'customer_invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=True),
        sa.Column('event_location', sa.String(length=200), nullable=True),
        sa.Column('guest_count', sa.Integer(), nullable=True),
        sa.Column('subtotal', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('discount_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('deposit_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('total_amount', sa.DECIMAL(15, 2), nullable=False),
        sa.Column('paid_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='draft'),
        sa.Column('is_tax_exempt', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tax_rate', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('po_number', sa.String(length=100), nullable=True),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('terms_conditions', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_date', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customer_invoices_id', 'customer_invoices', ['id'])
    op.create_index('ix_customer_invoices_customer_id', 'customer_invoices', ['customer_id'])
    op.create_index('ix_customer_invoices_invoice_number', 'customer_invoices', ['invoice_number'], unique=True)
    op.create_index('ix_customer_invoices_invoice_date', 'customer_invoices', ['invoice_date'])
    op.create_index('ix_customer_invoices_due_date', 'customer_invoices', ['due_date'])
    op.create_index('ix_customer_invoices_status', 'customer_invoices', ['status'])

    # Create customer_invoice_lines table
    op.create_table(
        'customer_invoice_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.DECIMAL(10, 2), nullable=True, server_default='1'),
        sa.Column('unit_price', sa.DECIMAL(15, 2), nullable=False),
        sa.Column('amount', sa.DECIMAL(15, 2), nullable=False),
        sa.Column('discount_percentage', sa.DECIMAL(5, 2), nullable=True),
        sa.Column('discount_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('is_taxable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tax_amount', sa.DECIMAL(15, 2), nullable=False, server_default='0'),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['customer_invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customer_invoice_lines_id', 'customer_invoice_lines', ['id'])
    op.create_index('ix_customer_invoice_lines_invoice_id', 'customer_invoice_lines', ['invoice_id'])

    # Create invoice_payments table
    op.create_table(
        'invoice_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.DECIMAL(15, 2), nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=False),
        sa.Column('reference_number', sa.String(length=100), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('is_deposit', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['invoice_id'], ['customer_invoices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_invoice_payments_id', 'invoice_payments', ['id'])
    op.create_index('ix_invoice_payments_invoice_id', 'invoice_payments', ['invoice_id'])
    op.create_index('ix_invoice_payments_payment_date', 'invoice_payments', ['payment_date'])
    op.create_index('ix_invoice_payments_reference_number', 'invoice_payments', ['reference_number'])


def downgrade():
    op.drop_index('ix_invoice_payments_reference_number', table_name='invoice_payments')
    op.drop_index('ix_invoice_payments_payment_date', table_name='invoice_payments')
    op.drop_index('ix_invoice_payments_invoice_id', table_name='invoice_payments')
    op.drop_index('ix_invoice_payments_id', table_name='invoice_payments')
    op.drop_table('invoice_payments')

    op.drop_index('ix_customer_invoice_lines_invoice_id', table_name='customer_invoice_lines')
    op.drop_index('ix_customer_invoice_lines_id', table_name='customer_invoice_lines')
    op.drop_table('customer_invoice_lines')

    op.drop_index('ix_customer_invoices_status', table_name='customer_invoices')
    op.drop_index('ix_customer_invoices_due_date', table_name='customer_invoices')
    op.drop_index('ix_customer_invoices_invoice_date', table_name='customer_invoices')
    op.drop_index('ix_customer_invoices_invoice_number', table_name='customer_invoices')
    op.drop_index('ix_customer_invoices_customer_id', table_name='customer_invoices')
    op.drop_index('ix_customer_invoices_id', table_name='customer_invoices')
    op.drop_table('customer_invoices')

    op.drop_index('ix_customers_customer_code', table_name='customers')
    op.drop_index('ix_customers_customer_name', table_name='customers')
    op.drop_index('ix_customers_id', table_name='customers')
    op.drop_table('customers')
