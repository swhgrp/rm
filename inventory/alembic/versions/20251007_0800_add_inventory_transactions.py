"""add inventory transactions table

Revision ID: 20251007_0800
Revises: 20251007_0633
Create Date: 2025-10-07 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251007_0800'
down_revision: Union[str, None] = '20251007_0633'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create inventory_transactions table
    op.create_table('inventory_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('master_item_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('storage_area_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('transaction_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('quantity_change', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit_of_measure', sa.String(length=50), nullable=True),
        sa.Column('quantity_before', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('quantity_after', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('unit_cost', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('pos_sale_id', sa.Integer(), nullable=True),
        sa.Column('pos_sale_item_id', sa.Integer(), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('transfer_id', sa.Integer(), nullable=True),
        sa.Column('waste_id', sa.Integer(), nullable=True),
        sa.Column('count_session_id', sa.Integer(), nullable=True),
        sa.Column('recipe_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_inventory_transactions_id', 'inventory_transactions', ['id'], unique=False)
    op.create_index('ix_inventory_transactions_master_item_id', 'inventory_transactions', ['master_item_id'], unique=False)
    op.create_index('ix_inventory_transactions_location_id', 'inventory_transactions', ['location_id'], unique=False)
    op.create_index('ix_inventory_transactions_transaction_type', 'inventory_transactions', ['transaction_type'], unique=False)
    op.create_index('ix_inventory_transactions_transaction_date', 'inventory_transactions', ['transaction_date'], unique=False)
    op.create_index('ix_inventory_transactions_pos_sale_id', 'inventory_transactions', ['pos_sale_id'], unique=False)

    # Create foreign keys
    op.create_foreign_key('fk_inventory_transactions_master_item', 'inventory_transactions', 'master_items', ['master_item_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_location', 'inventory_transactions', 'locations', ['location_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_storage_area', 'inventory_transactions', 'storage_areas', ['storage_area_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_pos_sale', 'inventory_transactions', 'pos_sales', ['pos_sale_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_pos_sale_item', 'inventory_transactions', 'pos_sale_items', ['pos_sale_item_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_invoice', 'inventory_transactions', 'invoices', ['invoice_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_transfer', 'inventory_transactions', 'transfers', ['transfer_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_waste', 'inventory_transactions', 'waste', ['waste_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_count_session', 'inventory_transactions', 'count_sessions', ['count_session_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_recipe', 'inventory_transactions', 'recipes', ['recipe_id'], ['id'])
    op.create_foreign_key('fk_inventory_transactions_created_by', 'inventory_transactions', 'users', ['created_by_id'], ['id'])


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint('fk_inventory_transactions_created_by', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_recipe', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_count_session', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_waste', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_transfer', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_invoice', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_pos_sale_item', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_pos_sale', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_storage_area', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_location', 'inventory_transactions', type_='foreignkey')
    op.drop_constraint('fk_inventory_transactions_master_item', 'inventory_transactions', type_='foreignkey')

    # Drop indexes
    op.drop_index('ix_inventory_transactions_pos_sale_id', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transactions_transaction_date', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transactions_transaction_type', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transactions_location_id', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transactions_master_item_id', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transactions_id', table_name='inventory_transactions')

    # Drop table
    op.drop_table('inventory_transactions')
