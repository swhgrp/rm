"""Add vendor_parsing_rules table

Revision ID: 20260125_0002
Revises: 20260125_0001
Create Date: 2026-01-25

This migration adds the vendor_parsing_rules table for storing vendor-specific
invoice parsing configuration. Rules help the AI parser and post-processing
correctly interpret vendor-specific invoice formats.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260125_0002'
down_revision = '20260125_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create vendor_parsing_rules table
    op.create_table(
        'vendor_parsing_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=False),

        # Column identification rules
        sa.Column('quantity_column', sa.String(100), nullable=True,
                  comment='Which column to use for quantity (e.g., "Qty Ship", "Shipped")'),
        sa.Column('item_code_column', sa.String(100), nullable=True,
                  comment='Which column has the item SKU (e.g., "Item Code", "ITEM#")'),
        sa.Column('price_column', sa.String(100), nullable=True,
                  comment='Which column has unit price (e.g., "Unit Price", "Price")'),

        # Format hints
        sa.Column('pack_size_format', sa.String(100), nullable=True,
                  comment='Pack size format pattern (e.g., "NxM UNIT" for "2x5 LB")'),
        sa.Column('date_format', sa.String(50), nullable=True,
                  comment='Invoice date format if non-standard'),

        # AI prompt additions
        sa.Column('ai_instructions', sa.Text(), nullable=True,
                  comment='Additional instructions to include in AI prompt for this vendor'),

        # Post-parse corrections (JSON)
        sa.Column('post_parse_rules', sa.Text(), nullable=True,
                  comment='JSON rules for post-parse corrections'),

        # Notes
        sa.Column('notes', sa.Text(), nullable=True,
                  comment='Human-readable notes about this vendor invoice format'),

        # Status
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create unique index on vendor_id (one rule set per vendor)
    op.create_index('ix_vendor_parsing_rules_vendor_id', 'vendor_parsing_rules', ['vendor_id'], unique=True)

    # Seed initial rules for Gordon Food Service
    op.execute("""
        INSERT INTO vendor_parsing_rules (vendor_id, quantity_column, item_code_column, price_column, pack_size_format, ai_instructions, notes)
        SELECT id, 'Qty Ship', 'Item Code', 'Unit Price', 'NxM UNIT',
               'For Gordon Food Service invoices:
- Use "Qty Ship" column for quantity (NOT "Qty Ord" or pack size numbers)
- "Qty Ord" is quantity ordered, "Qty Ship" is quantity actually shipped
- Pack Size like "2x5 LB" means packaging (2 bags of 5lb), NOT quantity
- Item Code is in the first column, NOT the UPC barcode
- Unit Price is the CASE price',
               'Gordon invoices have Qty Ord, Qty Ship, and Pack Size columns. Always use Qty Ship for the actual quantity.'
        FROM vendors WHERE LOWER(name) LIKE '%gordon%'
        LIMIT 1
    """)


def downgrade() -> None:
    op.drop_index('ix_vendor_parsing_rules_vendor_id', table_name='vendor_parsing_rules')
    op.drop_table('vendor_parsing_rules')
