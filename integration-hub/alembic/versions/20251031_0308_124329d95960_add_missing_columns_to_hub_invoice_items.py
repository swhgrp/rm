"""Add missing columns to hub_invoice_items

Revision ID: 124329d95960
Revises: 72d347c16db6
Create Date: 2025-10-31 03:08:30.126968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '124329d95960'
down_revision: Union[str, None] = '72d347c16db6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to hub_invoice_items
    op.add_column('hub_invoice_items', sa.Column('item_code', sa.String(length=100), nullable=True))
    op.add_column('hub_invoice_items', sa.Column('total_amount', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('hub_invoice_items', sa.Column('suggested_item_id', sa.Integer(), nullable=True))
    op.add_column('hub_invoice_items', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('hub_invoice_items', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('hub_invoice_items', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # Rename mapped_by_id to mapped_by
    op.alter_column('hub_invoice_items', 'mapped_by_id', new_column_name='mapped_by')

    # Copy line_total to total_amount for existing records
    op.execute('UPDATE hub_invoice_items SET total_amount = line_total WHERE total_amount IS NULL')


def downgrade() -> None:
    op.alter_column('hub_invoice_items', 'mapped_by', new_column_name='mapped_by_id')
    op.drop_column('hub_invoice_items', 'updated_at')
    op.drop_column('hub_invoice_items', 'created_at')
    op.drop_column('hub_invoice_items', 'notes')
    op.drop_column('hub_invoice_items', 'suggested_item_id')
    op.drop_column('hub_invoice_items', 'total_amount')
    op.drop_column('hub_invoice_items', 'item_code')
