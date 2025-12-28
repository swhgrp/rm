"""Add waste_account_name to category_gl_mapping

Revision ID: 20251228_0001
Revises: 20251227_0003_add_backbar_size_fields
Create Date: 2025-12-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251228_0001'
down_revision = '20251227_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add waste_account_name column to category_gl_mapping table
    op.add_column('category_gl_mapping', sa.Column('waste_account_name', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('category_gl_mapping', 'waste_account_name')
