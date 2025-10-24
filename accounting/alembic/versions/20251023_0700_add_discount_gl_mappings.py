"""add discount gl mappings

Revision ID: 20251023_0700
Revises: 20251023_0600
Create Date: 2025-10-23 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_0700'
down_revision = '20251023_0600'
branch_labels = None
depends_on = None


def upgrade():
    # Create pos_discount_gl_mappings table
    op.create_table(
        'pos_discount_gl_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('pos_discount_name', sa.String(length=255), nullable=False),
        sa.Column('discount_account_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['discount_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pos_discount_gl_mappings_area_id'), 'pos_discount_gl_mappings', ['area_id'], unique=False)
    op.create_index(op.f('ix_pos_discount_gl_mappings_id'), 'pos_discount_gl_mappings', ['id'], unique=False)
    op.create_index(op.f('ix_pos_discount_gl_mappings_is_active'), 'pos_discount_gl_mappings', ['is_active'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_pos_discount_gl_mappings_is_active'), table_name='pos_discount_gl_mappings')
    op.drop_index(op.f('ix_pos_discount_gl_mappings_id'), table_name='pos_discount_gl_mappings')
    op.drop_index(op.f('ix_pos_discount_gl_mappings_area_id'), table_name='pos_discount_gl_mappings')
    op.drop_table('pos_discount_gl_mappings')
