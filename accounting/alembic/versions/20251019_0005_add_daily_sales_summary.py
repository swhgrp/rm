"""Add daily sales summary tables

Revision ID: 20251019_0005
Revises: 20251018_0004
Create Date: 2025-10-19 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '20251019_0005'
down_revision = '20251018_0004'
branch_labels = None
depends_on = None


def upgrade():
    # Daily Sales Summary table
    op.create_table('daily_sales_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False, index=True),
        sa.Column('area_id', sa.Integer(), nullable=False, index=True),
        sa.Column('pos_system', sa.String(50), nullable=True),  # 'CLOVER', 'SQUARE', etc.
        sa.Column('pos_location_id', sa.String(100), nullable=True),  # External POS location ID

        # Sales totals
        sa.Column('gross_sales', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('discounts', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('refunds', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('net_sales', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('tax_collected', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('tips', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('total_collected', sa.Numeric(15, 2), nullable=False, server_default='0.00'),

        # Payment method breakdowns (stored as JSONB for flexibility)
        sa.Column('payment_breakdown', JSONB, nullable=True),
        # Example: {"cash": 500.00, "credit_card": 1200.00, "gift_card": 100.00}

        # Category breakdowns
        sa.Column('category_breakdown', JSONB, nullable=True),
        # Example: {"food": 1200.00, "beverage": 400.00, "alcohol": 200.00}

        # Status and metadata
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        # Status: 'draft', 'verified', 'posted'

        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('imported_from', sa.String(100), nullable=True),  # Source system/file
        sa.Column('imported_at', sa.DateTime(), nullable=True),

        # Audit fields
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('posted_by', sa.Integer(), nullable=True),
        sa.Column('posted_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True, onupdate=sa.func.now()),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['posted_by'], ['users.id'], ondelete='SET NULL'),
    )

    # Unique constraint: one DSS per business date per location
    op.create_index('ix_dss_business_date_area', 'daily_sales_summaries',
                    ['business_date', 'area_id'], unique=True)

    # Sales Line Items (optional detailed breakdown)
    op.create_table('sales_line_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dss_id', sa.Integer(), nullable=False, index=True),
        sa.Column('category', sa.String(100), nullable=True),  # 'Food', 'Beverage', 'Alcohol'
        sa.Column('item_name', sa.String(200), nullable=True),
        sa.Column('quantity', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit_price', sa.Numeric(15, 2), nullable=True),
        sa.Column('gross_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('discount_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('net_amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('revenue_account_id', sa.Integer(), nullable=True),  # GL account for revenue

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['dss_id'], ['daily_sales_summaries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revenue_account_id'], ['accounts.id'], ondelete='SET NULL'),
    )

    # Payment Details (optional detailed payment tracking)
    op.create_table('sales_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dss_id', sa.Integer(), nullable=False, index=True),
        sa.Column('payment_type', sa.String(50), nullable=False),  # 'CASH', 'CREDIT_CARD', etc.
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.Column('tips', sa.Numeric(15, 2), nullable=False, server_default='0.00'),
        sa.Column('deposit_account_id', sa.Integer(), nullable=True),  # GL account (cash/bank)
        sa.Column('processor', sa.String(100), nullable=True),  # 'Visa', 'Mastercard', 'Square'
        sa.Column('reference_number', sa.String(100), nullable=True),  # Batch number, etc.

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['dss_id'], ['daily_sales_summaries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deposit_account_id'], ['accounts.id'], ondelete='SET NULL'),
    )


def downgrade():
    op.drop_table('sales_payments')
    op.drop_table('sales_line_items')
    op.drop_index('ix_dss_business_date_area', table_name='daily_sales_summaries')
    op.drop_table('daily_sales_summaries')
