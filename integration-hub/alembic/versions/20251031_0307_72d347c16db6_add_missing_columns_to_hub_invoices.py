"""Add missing columns to hub_invoices

Revision ID: 72d347c16db6
Revises: e5edc49586fd
Create Date: 2025-10-31 03:07:51.150088

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72d347c16db6'
down_revision: Union[str, None] = 'e5edc49586fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to hub_invoices
    op.add_column('hub_invoices', sa.Column('vendor_id', sa.Integer(), nullable=True))
    op.add_column('hub_invoices', sa.Column('vendor_account_number', sa.String(length=100), nullable=True))
    op.add_column('hub_invoices', sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('hub_invoices', sa.Column('source_filename', sa.String(length=500), nullable=True))
    op.add_column('hub_invoices', sa.Column('location_id', sa.Integer(), nullable=True))
    op.add_column('hub_invoices', sa.Column('location_name', sa.String(length=100), nullable=True))
    op.add_column('hub_invoices', sa.Column('inventory_sync_error', sa.Text(), nullable=True))
    op.add_column('hub_invoices', sa.Column('accounting_sync_error', sa.Text(), nullable=True))
    op.add_column('hub_invoices', sa.Column('approved_by', sa.Integer(), nullable=True))
    op.add_column('hub_invoices', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('hub_invoices', 'approved_at')
    op.drop_column('hub_invoices', 'approved_by')
    op.drop_column('hub_invoices', 'accounting_sync_error')
    op.drop_column('hub_invoices', 'inventory_sync_error')
    op.drop_column('hub_invoices', 'location_name')
    op.drop_column('hub_invoices', 'location_id')
    op.drop_column('hub_invoices', 'source_filename')
    op.drop_column('hub_invoices', 'tax_amount')
    op.drop_column('hub_invoices', 'vendor_account_number')
    op.drop_column('hub_invoices', 'vendor_id')
