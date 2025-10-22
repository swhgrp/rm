"""make master_item_id optional in vendor_items

Revision ID: make_master_item_optional
Revises: 
Create Date: 2025-01-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'make_master_item_optional'
down_revision = None  # Update this if you have previous migrations
branch_labels = None
depends_on = None

def upgrade():
    # Make master_item_id nullable
    op.alter_column('vendor_items', 'master_item_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)

def downgrade():
    # Make master_item_id required again
    op.alter_column('vendor_items', 'master_item_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)
