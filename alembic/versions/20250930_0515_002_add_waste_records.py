"""Add waste_records table

Revision ID: 002
Revises: 001
Create Date: 2025-09-30 05:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create waste_records table
    op.create_table(
        'waste_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('master_item_id', sa.Integer(), nullable=False),
        sa.Column('inventory_id', sa.Integer(), nullable=True),
        sa.Column('quantity_wasted', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('reason_code', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=False),
        sa.Column('waste_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.ForeignKeyConstraint(['master_item_id'], ['master_items.id'], ),
        sa.ForeignKeyConstraint(['inventory_id'], ['inventory.id'], ),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_waste_records_id'), 'waste_records', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_waste_records_id'), table_name='waste_records')
    op.drop_table('waste_records')