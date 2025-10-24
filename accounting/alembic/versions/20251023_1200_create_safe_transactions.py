"""create safe_transactions table

Revision ID: 20251023_1200
Revises: 20251023_1100
Create Date: 2025-10-23 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_1200'
down_revision = '20251023_1100'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('safe_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('balance_after', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('is_posted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('posted_by', sa.Integer(), nullable=True),
        sa.Column('posted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['posted_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_safe_transactions_area_id'), 'safe_transactions', ['area_id'], unique=False)
    op.create_index(op.f('ix_safe_transactions_transaction_date'), 'safe_transactions', ['transaction_date'], unique=False)
    op.create_index(op.f('ix_safe_transactions_transaction_type'), 'safe_transactions', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_safe_transactions_is_posted'), 'safe_transactions', ['is_posted'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_safe_transactions_is_posted'), table_name='safe_transactions')
    op.drop_index(op.f('ix_safe_transactions_transaction_type'), table_name='safe_transactions')
    op.drop_index(op.f('ix_safe_transactions_transaction_date'), table_name='safe_transactions')
    op.drop_index(op.f('ix_safe_transactions_area_id'), table_name='safe_transactions')
    op.drop_table('safe_transactions')
