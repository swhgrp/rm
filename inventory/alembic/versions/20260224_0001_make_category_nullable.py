"""Make master_items.category nullable (set by Hub on vendor item sync)

Revision ID: 20260224_0001
Revises: 20260218_0003
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260224_0001'
down_revision = '20260218_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('master_items', 'category',
                    existing_type=sa.String(),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('master_items', 'category',
                    existing_type=sa.String(),
                    nullable=False)
