"""Add vendor_aliases table for normalizing vendor names

Revision ID: 20251218_0001
Revises:
Create Date: 2025-12-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251218_0001'
down_revision = 'add_item_unit_conversions'
branch_labels = None
depends_on = None


def upgrade():
    # Create vendor_aliases table
    op.create_table(
        'vendor_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alias_name', sa.String(200), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('case_insensitive', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    # Create indexes
    op.create_index('ix_vendor_aliases_id', 'vendor_aliases', ['id'])
    op.create_index('ix_vendor_aliases_alias_name', 'vendor_aliases', ['alias_name'], unique=True)
    op.create_index('ix_vendor_aliases_vendor_id', 'vendor_aliases', ['vendor_id'])

    # Create a lowercase index for case-insensitive lookups
    op.execute("CREATE INDEX ix_vendor_aliases_alias_name_lower ON vendor_aliases (LOWER(alias_name))")


def downgrade():
    op.drop_index('ix_vendor_aliases_alias_name_lower', 'vendor_aliases')
    op.drop_index('ix_vendor_aliases_vendor_id', 'vendor_aliases')
    op.drop_index('ix_vendor_aliases_alias_name', 'vendor_aliases')
    op.drop_index('ix_vendor_aliases_id', 'vendor_aliases')
    op.drop_table('vendor_aliases')
