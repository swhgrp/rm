"""add safe_account_id to areas

Revision ID: 20251023_1300
Revises: 20251023_1200
Create Date: 2025-10-23 13:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_1300'
down_revision = '20251023_1200'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('areas', sa.Column('safe_account_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_areas_safe_account', 'areas', 'accounts', ['safe_account_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_areas_safe_account', 'areas', type_='foreignkey')
    op.drop_column('areas', 'safe_account_id')
