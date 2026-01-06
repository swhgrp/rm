"""Add unit_of_measure to waste_records

Revision ID: 20260105_0001
Revises: 20251228_0001_add_performance_indexes
Create Date: 2026-01-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260105_0001'
down_revision = '20251228_0001_perf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unit_of_measure column to waste_records table
    op.add_column(
        'waste_records',
        sa.Column('unit_of_measure', sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('waste_records', 'unit_of_measure')
