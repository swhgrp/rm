"""Add post-parse validation fields to invoices and items

Revision ID: 20260213_0001
Revises: 20260212_0003
Create Date: 2026-02-13

Adds needs_review flag, review_reason, parsed_with_vendor_rules,
line_items_total to hub_invoices, and validation_flags to hub_invoice_items.
These support post-parse sanity checks, invoice-level total reconciliation,
auto-reparse with vendor rules, and confidence-based hold queue.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '20260213_0001'
down_revision = '20260212_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hub_invoices: review/hold queue fields
    op.add_column('hub_invoices', sa.Column('needs_review', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('hub_invoices', sa.Column('review_reason', sa.Text(), nullable=True))
    op.add_column('hub_invoices', sa.Column('parsed_with_vendor_rules', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('hub_invoices', sa.Column('line_items_total', sa.Numeric(12, 2), nullable=True))
    op.create_index('ix_hub_invoices_needs_review', 'hub_invoices', ['needs_review'])

    # hub_invoice_items: per-item validation flags
    op.add_column('hub_invoice_items', sa.Column('validation_flags', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('hub_invoice_items', 'validation_flags')
    op.drop_index('ix_hub_invoices_needs_review', 'hub_invoices')
    op.drop_column('hub_invoices', 'line_items_total')
    op.drop_column('hub_invoices', 'parsed_with_vendor_rules')
    op.drop_column('hub_invoices', 'review_reason')
    op.drop_column('hub_invoices', 'needs_review')
