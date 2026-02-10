"""Add logo_path to areas table

Revision ID: 20260208_0001
Revises: 20260126_0001
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260208_0001'
down_revision = '20260126_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('areas', sa.Column('logo_path', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('areas', 'logo_path')
