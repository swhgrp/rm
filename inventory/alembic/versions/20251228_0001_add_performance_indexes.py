"""Add performance indexes for commonly queried columns

Revision ID: 20251228_0001_perf
Revises: 20251221_0001
Create Date: 2025-12-28

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20251228_0001_perf'
down_revision = '20251218_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Inventory table - frequently queried by location and master_item
    op.create_index('ix_inventory_location_item', 'inventory', ['location_id', 'master_item_id'], unique=False)
    op.create_index('ix_inventory_master_item', 'inventory', ['master_item_id'], unique=False)

    # Inventory transactions - frequently filtered by date and type
    op.create_index('ix_inventory_transaction_date', 'inventory_transactions', ['transaction_date'], unique=False)
    op.create_index('ix_inventory_transaction_type', 'inventory_transactions', ['transaction_type'], unique=False)
    op.create_index('ix_inventory_transaction_item_location', 'inventory_transactions', ['master_item_id', 'location_id'], unique=False)

    # POS Sales - index on inventory_deducted for processing queries
    # Note: order_date and location already have composite index idx_pos_sales_date_location
    op.create_index('ix_pos_sales_deducted', 'pos_sales', ['inventory_deducted'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pos_sales_deducted', table_name='pos_sales')
    op.drop_index('ix_inventory_transaction_item_location', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transaction_type', table_name='inventory_transactions')
    op.drop_index('ix_inventory_transaction_date', table_name='inventory_transactions')
    op.drop_index('ix_inventory_master_item', table_name='inventory')
    op.drop_index('ix_inventory_location_item', table_name='inventory')
