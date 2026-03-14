"""Add GL anomaly review tables

Revision ID: 20260312_0001
Revises: 20260208_0001
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260312_0001'
down_revision = '20260208_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gl_anomaly_flags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('journal_entry_line_id', sa.Integer(), sa.ForeignKey('journal_entry_lines.id', ondelete='SET NULL'), nullable=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('flag_type', sa.String(60), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='warning'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('flagged_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('expected_range_low', sa.Numeric(15, 2), nullable=True),
        sa.Column('expected_range_high', sa.Numeric(15, 2), nullable=True),
        sa.Column('period_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='open'),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('ai_confidence', sa.String(20), nullable=True),
        sa.Column('run_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_gl_anomaly_flags_area', 'gl_anomaly_flags', ['area_id'])
    op.create_index('idx_gl_anomaly_flags_status', 'gl_anomaly_flags', ['status'])
    op.create_index('idx_gl_anomaly_flags_period', 'gl_anomaly_flags', ['period_date'])
    op.create_index('idx_gl_anomaly_flags_run', 'gl_anomaly_flags', ['run_id'])

    op.create_table(
        'gl_account_baselines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_code', sa.String(30), nullable=True),
        sa.Column('months_of_data', sa.Integer(), nullable=True),
        sa.Column('avg_monthly_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('stddev_monthly_balance', sa.Numeric(15, 2), nullable=True),
        sa.Column('avg_monthly_activity', sa.Numeric(15, 2), nullable=True),
        sa.Column('stddev_monthly_activity', sa.Numeric(15, 2), nullable=True),
        sa.Column('min_observed', sa.Numeric(15, 2), nullable=True),
        sa.Column('max_observed', sa.Numeric(15, 2), nullable=True),
        sa.Column('typical_posting_days', postgresql.JSONB(), nullable=True),
        sa.Column('last_computed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('area_id', 'account_id', name='uq_gl_baseline_area_account'),
    )


def downgrade() -> None:
    op.drop_table('gl_account_baselines')
    op.drop_index('idx_gl_anomaly_flags_run', table_name='gl_anomaly_flags')
    op.drop_index('idx_gl_anomaly_flags_period', table_name='gl_anomaly_flags')
    op.drop_index('idx_gl_anomaly_flags_status', table_name='gl_anomaly_flags')
    op.drop_index('idx_gl_anomaly_flags_area', table_name='gl_anomaly_flags')
    op.drop_table('gl_anomaly_flags')
