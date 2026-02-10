"""Add maintenance_logs and maintenance_documents tables

Revision ID: 002
Revises: 001
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'maintenance_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=False),
        sa.Column('completed_date', sa.Date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['schedule_id'], ['maintenance_schedules.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_maintenance_logs_id', 'maintenance_logs', ['id'], unique=False)
    op.create_index('ix_maintenance_logs_schedule_id', 'maintenance_logs', ['schedule_id'], unique=False)

    op.create_table(
        'maintenance_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('log_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['log_id'], ['maintenance_logs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_maintenance_documents_id', 'maintenance_documents', ['id'], unique=False)
    op.create_index('ix_maintenance_documents_log_id', 'maintenance_documents', ['log_id'], unique=False)


def downgrade() -> None:
    op.drop_table('maintenance_documents')
    op.drop_table('maintenance_logs')
