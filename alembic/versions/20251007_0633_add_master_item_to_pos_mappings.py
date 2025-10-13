"""add master_item_id to pos_item_mappings

Revision ID: 20251007_0633
Revises: 20250930_0832_b69b8511d78b
Create Date: 2025-10-07 06:33:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251007_0633'
down_revision = '20250930_0832_b69b8511d78b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add master_item_id column
    op.add_column('pos_item_mappings', sa.Column('master_item_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_pos_item_mappings_master_item_id', 'pos_item_mappings', 'master_items', ['master_item_id'], ['id'])

    # Make recipe_id nullable
    op.alter_column('pos_item_mappings', 'recipe_id', nullable=True)


def downgrade() -> None:
    # Remove master_item_id column
    op.drop_constraint('fk_pos_item_mappings_master_item_id', 'pos_item_mappings', type_='foreignkey')
    op.drop_column('pos_item_mappings', 'master_item_id')

    # Make recipe_id required again
    op.alter_column('pos_item_mappings', 'recipe_id', nullable=False)
