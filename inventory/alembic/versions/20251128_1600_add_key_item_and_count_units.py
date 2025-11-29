"""add key_item flag and additional count units to master_items

Revision ID: add_key_item_count_units
Revises: make_master_item_optional
Create Date: 2025-11-28

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_key_item_count_units'
down_revision = ('20251009_1330', 'make_master_item_optional')  # Merge both heads
branch_labels = None
depends_on = None

def upgrade():
    # Add is_key_item flag
    op.add_column('master_items', sa.Column('is_key_item', sa.Boolean(), nullable=True, default=False))

    # Add additional count unit fields
    op.add_column('master_items', sa.Column('count_unit_2_id', sa.Integer(), nullable=True))
    op.add_column('master_items', sa.Column('count_unit_3_id', sa.Integer(), nullable=True))

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_master_items_count_unit_2',
        'master_items', 'units_of_measure',
        ['count_unit_2_id'], ['id']
    )
    op.create_foreign_key(
        'fk_master_items_count_unit_3',
        'master_items', 'units_of_measure',
        ['count_unit_3_id'], ['id']
    )

    # Set default value for existing rows
    op.execute("UPDATE master_items SET is_key_item = false WHERE is_key_item IS NULL")

def downgrade():
    # Remove foreign key constraints
    op.drop_constraint('fk_master_items_count_unit_3', 'master_items', type_='foreignkey')
    op.drop_constraint('fk_master_items_count_unit_2', 'master_items', type_='foreignkey')

    # Remove columns
    op.drop_column('master_items', 'count_unit_3_id')
    op.drop_column('master_items', 'count_unit_2_id')
    op.drop_column('master_items', 'is_key_item')
