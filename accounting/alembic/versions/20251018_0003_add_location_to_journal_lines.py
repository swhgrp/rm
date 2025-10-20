"""Add area_id (location) to journal entry lines for multi-location accounting

Revision ID: 20251018_0003
Revises: 20251018_0002
Create Date: 2025-10-18 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251018_0003'
down_revision = '20251018_0002'
branch_labels = None
depends_on = None


def upgrade():
    # Add area_id column to journal_entry_lines table
    # This allows each journal entry line to be tagged with a location/area
    # Following Restaurant365 model: shared COA + location tagging
    op.add_column('journal_entry_lines',
        sa.Column('area_id', sa.Integer(), nullable=True)
    )

    # Add foreign key constraint to areas table
    op.create_foreign_key(
        'journal_entry_lines_area_id_fkey',
        'journal_entry_lines',
        'areas',
        ['area_id'],
        ['id'],
        ondelete='SET NULL'  # If area is deleted, set to NULL (not CASCADE)
    )

    # Add index for performance on area-filtered queries
    op.create_index(
        'ix_journal_entry_lines_area_id',
        'journal_entry_lines',
        ['area_id']
    )

    # Note: area_id is nullable to support:
    # 1. Legacy entries (already exist without location)
    # 2. Corporate-level entries (not specific to one location)
    # 3. Intercompany/consolidated entries


def downgrade():
    # Remove index
    op.drop_index('ix_journal_entry_lines_area_id', table_name='journal_entry_lines')

    # Remove foreign key constraint
    op.drop_constraint('journal_entry_lines_area_id_fkey', 'journal_entry_lines', type_='foreignkey')

    # Remove column
    op.drop_column('journal_entry_lines', 'area_id')
