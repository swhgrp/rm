"""add payment gl mappings table

Revision ID: 20251023_0900
Revises: 20251023_0800
Create Date: 2025-10-23 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_0900'
down_revision = '20251023_0800'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pos_payment_gl_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('pos_payment_type', sa.String(length=255), nullable=False),
        sa.Column('deposit_account_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deposit_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pos_payment_gl_mappings_area_id'), 'pos_payment_gl_mappings', ['area_id'], unique=False)
    op.create_index(op.f('ix_pos_payment_gl_mappings_is_active'), 'pos_payment_gl_mappings', ['is_active'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_pos_payment_gl_mappings_is_active'), table_name='pos_payment_gl_mappings')
    op.drop_index(op.f('ix_pos_payment_gl_mappings_area_id'), table_name='pos_payment_gl_mappings')
    op.drop_table('pos_payment_gl_mappings')
