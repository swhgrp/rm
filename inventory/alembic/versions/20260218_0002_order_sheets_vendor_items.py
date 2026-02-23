"""Switch order sheet items from master_items to hub vendor items

Revision ID: 20260218_0002
Revises: 20260218_0001
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260218_0002'
down_revision = '20260218_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- order_sheet_template_items ---
    # Drop FK constraint and unique constraint on master_item_id
    op.drop_constraint('uq_osti_template_item', 'order_sheet_template_items', type_='unique')
    op.drop_constraint('order_sheet_template_items_master_item_id_fkey', 'order_sheet_template_items', type_='foreignkey')

    # Rename column
    op.alter_column('order_sheet_template_items', 'master_item_id',
                     new_column_name='hub_vendor_item_id')

    # Add snapshot columns for vendor item data (denormalized since cross-DB)
    op.add_column('order_sheet_template_items', sa.Column('item_name', sa.String(), nullable=True))
    op.add_column('order_sheet_template_items', sa.Column('vendor_sku', sa.String(), nullable=True))
    op.add_column('order_sheet_template_items', sa.Column('vendor_name', sa.String(), nullable=True))
    op.add_column('order_sheet_template_items', sa.Column('category', sa.String(), nullable=True))
    op.add_column('order_sheet_template_items', sa.Column('unit_abbr', sa.String(20), nullable=True))

    # New unique constraint on (template_id, hub_vendor_item_id)
    op.create_unique_constraint('uq_osti_template_vendor_item', 'order_sheet_template_items',
                                ['template_id', 'hub_vendor_item_id'])

    # --- order_sheet_items ---
    # Drop FK constraint on master_item_id
    op.drop_constraint('order_sheet_items_master_item_id_fkey', 'order_sheet_items', type_='foreignkey')

    # Rename column
    op.alter_column('order_sheet_items', 'master_item_id',
                     new_column_name='hub_vendor_item_id')

    # Add snapshot columns
    op.add_column('order_sheet_items', sa.Column('item_name', sa.String(), nullable=True))
    op.add_column('order_sheet_items', sa.Column('vendor_sku', sa.String(), nullable=True))
    op.add_column('order_sheet_items', sa.Column('vendor_name', sa.String(), nullable=True))
    op.add_column('order_sheet_items', sa.Column('category', sa.String(), nullable=True))


def downgrade() -> None:
    # --- order_sheet_items ---
    op.drop_column('order_sheet_items', 'category')
    op.drop_column('order_sheet_items', 'vendor_name')
    op.drop_column('order_sheet_items', 'vendor_sku')
    op.drop_column('order_sheet_items', 'item_name')

    op.alter_column('order_sheet_items', 'hub_vendor_item_id',
                     new_column_name='master_item_id')

    op.create_foreign_key('order_sheet_items_master_item_id_fkey', 'order_sheet_items',
                          'master_items', ['master_item_id'], ['id'])

    # --- order_sheet_template_items ---
    op.drop_constraint('uq_osti_template_vendor_item', 'order_sheet_template_items', type_='unique')

    op.drop_column('order_sheet_template_items', 'unit_abbr')
    op.drop_column('order_sheet_template_items', 'category')
    op.drop_column('order_sheet_template_items', 'vendor_name')
    op.drop_column('order_sheet_template_items', 'vendor_sku')
    op.drop_column('order_sheet_template_items', 'item_name')

    op.alter_column('order_sheet_template_items', 'hub_vendor_item_id',
                     new_column_name='master_item_id')

    op.create_foreign_key('order_sheet_template_items_master_item_id_fkey', 'order_sheet_template_items',
                          'master_items', ['master_item_id'], ['id'])
    op.create_unique_constraint('uq_osti_template_item', 'order_sheet_template_items',
                                ['template_id', 'master_item_id'])
