"""Add daily_review_runs and daily_review_findings tables

Revision ID: 20260326_0001
Revises: 20260320_0002
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa


revision = '20260326_0001'
down_revision = '20260320_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'daily_review_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False, index=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_window_hours', sa.Integer(), nullable=False, server_default='48'),
        sa.Column('total_findings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('critical_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('info_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'daily_review_findings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False, index=True),
        sa.Column('section', sa.String(50), nullable=False, index=True),
        sa.Column('check_name', sa.String(100), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('record_type', sa.String(50), nullable=True),
        sa.Column('record_id', sa.Integer(), nullable=True),
        sa.Column('record_id_secondary', sa.Integer(), nullable=True),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('flagged_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('expected_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('ix_daily_review_findings_run_section', 'daily_review_findings', ['run_id', 'section'])


def downgrade():
    op.drop_index('ix_daily_review_findings_run_section')
    op.drop_table('daily_review_findings')
    op.drop_table('daily_review_runs')
