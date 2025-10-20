"""Initial schema for Integration Hub

Revision ID: 001
Revises:
Create Date: 2025-10-19 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create hub_invoices table
    op.create_table(
        'hub_invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_name', sa.String(length=200), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), nullable=False),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),

        # Source tracking
        sa.Column('source', sa.String(length=50), nullable=True),  # 'email', 'upload', 'api'
        sa.Column('source_email', sa.String(length=200), nullable=True),
        sa.Column('pdf_path', sa.String(length=500), nullable=True),
        sa.Column('raw_data', JSON, nullable=True),

        # Routing status
        sa.Column('sent_to_inventory', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('sent_to_accounting', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=False),
        # Status values: 'pending', 'mapping', 'ready', 'sent', 'error', 'partial'

        # Sync tracking
        sa.Column('inventory_invoice_id', sa.Integer(), nullable=True),
        sa.Column('accounting_je_id', sa.Integer(), nullable=True),
        sa.Column('inventory_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accounting_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inventory_error', sa.Text(), nullable=True),
        sa.Column('accounting_error', sa.Text(), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_invoices_vendor_name', 'hub_invoices', ['vendor_name'])
    op.create_index('ix_hub_invoices_invoice_number', 'hub_invoices', ['invoice_number'])
    op.create_index('ix_hub_invoices_invoice_date', 'hub_invoices', ['invoice_date'])
    op.create_index('ix_hub_invoices_status', 'hub_invoices', ['status'])

    # Create hub_invoice_items table
    op.create_table(
        'hub_invoice_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('item_description', sa.String(length=500), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit_of_measure', sa.String(length=50), nullable=True),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=False),

        # Mapping to inventory
        sa.Column('inventory_item_id', sa.Integer(), nullable=True),
        sa.Column('inventory_item_name', sa.String(length=200), nullable=True),
        sa.Column('inventory_category', sa.String(length=100), nullable=True),

        # Mapping to GL accounts
        sa.Column('gl_asset_account', sa.Integer(), nullable=True),
        sa.Column('gl_cogs_account', sa.Integer(), nullable=True),
        sa.Column('gl_waste_account', sa.Integer(), nullable=True),

        # Mapping status
        sa.Column('is_mapped', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('mapping_confidence', sa.Numeric(precision=3, scale=2), nullable=True),  # 0.00 to 1.00
        sa.Column('mapping_method', sa.String(length=50), nullable=True),  # 'manual', 'exact', 'fuzzy', 'category'
        sa.Column('mapped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mapped_by_id', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['invoice_id'], ['hub_invoices.id'], ondelete='CASCADE')
    )
    op.create_index('ix_hub_invoice_items_invoice_id', 'hub_invoice_items', ['invoice_id'])
    op.create_index('ix_hub_invoice_items_is_mapped', 'hub_invoice_items', ['is_mapped'])
    op.create_index('ix_hub_invoice_items_inventory_item_id', 'hub_invoice_items', ['inventory_item_id'])

    # Create item_gl_mapping table (master mapping for specific items)
    op.create_table(
        'item_gl_mapping',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inventory_item_id', sa.Integer(), nullable=False),
        sa.Column('inventory_item_name', sa.String(length=200), nullable=False),
        sa.Column('inventory_category', sa.String(length=100), nullable=True),

        # GL account mappings
        sa.Column('gl_asset_account', sa.Integer(), nullable=False),
        sa.Column('gl_cogs_account', sa.Integer(), nullable=False),
        sa.Column('gl_waste_account', sa.Integer(), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inventory_item_id', name='uq_item_gl_mapping_inventory_item_id')
    )
    op.create_index('ix_item_gl_mapping_inventory_item_id', 'item_gl_mapping', ['inventory_item_id'])
    op.create_index('ix_item_gl_mapping_category', 'item_gl_mapping', ['inventory_category'])

    # Create category_gl_mapping table (default mapping by category)
    op.create_table(
        'category_gl_mapping',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inventory_category', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),

        # GL account mappings (defaults for this category)
        sa.Column('gl_asset_account', sa.Integer(), nullable=False),
        sa.Column('gl_cogs_account', sa.Integer(), nullable=False),
        sa.Column('gl_waste_account', sa.Integer(), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inventory_category', name='uq_category_gl_mapping_category')
    )
    op.create_index('ix_category_gl_mapping_category', 'category_gl_mapping', ['inventory_category'])


def downgrade() -> None:
    op.drop_index('ix_category_gl_mapping_category', table_name='category_gl_mapping')
    op.drop_table('category_gl_mapping')

    op.drop_index('ix_item_gl_mapping_category', table_name='item_gl_mapping')
    op.drop_index('ix_item_gl_mapping_inventory_item_id', table_name='item_gl_mapping')
    op.drop_table('item_gl_mapping')

    op.drop_index('ix_hub_invoice_items_inventory_item_id', table_name='hub_invoice_items')
    op.drop_index('ix_hub_invoice_items_is_mapped', table_name='hub_invoice_items')
    op.drop_index('ix_hub_invoice_items_invoice_id', table_name='hub_invoice_items')
    op.drop_table('hub_invoice_items')

    op.drop_index('ix_hub_invoices_status', table_name='hub_invoices')
    op.drop_index('ix_hub_invoices_invoice_date', table_name='hub_invoices')
    op.drop_index('ix_hub_invoices_invoice_number', table_name='hub_invoices')
    op.drop_index('ix_hub_invoices_vendor_name', table_name='hub_invoices')
    op.drop_table('hub_invoices')
