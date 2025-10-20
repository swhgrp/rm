"""Add storage areas and vendor/par fields

Revision ID: 004
Revises: 003
Create Date: 2025-09-30 07:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create storage_areas table
    op.create_table(
        'storage_areas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_storage_areas_id', 'storage_areas', ['id'])
    op.create_index('ix_storage_areas_location_id', 'storage_areas', ['location_id'])

    # Add vendor and par_level to master_items
    op.add_column('master_items', sa.Column('vendor', sa.String(), nullable=True))
    op.add_column('master_items', sa.Column('par_level', sa.Numeric(10, 3), nullable=True))
    op.create_index('ix_master_items_vendor', 'master_items', ['vendor'])

    # Add storage_area_id to inventory
    op.add_column('inventory', sa.Column('storage_area_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_inventory_storage_area', 'inventory', 'storage_areas', ['storage_area_id'], ['id'])
    op.create_index('ix_inventory_storage_area_id', 'inventory', ['storage_area_id'])


def downgrade() -> None:
    # Remove storage_area_id from inventory
    op.drop_index('ix_inventory_storage_area_id', 'inventory')
    op.drop_constraint('fk_inventory_storage_area', 'inventory', type_='foreignkey')
    op.drop_column('inventory', 'storage_area_id')

    # Remove vendor and par_level from master_items
    op.drop_index('ix_master_items_vendor', 'master_items')
    op.drop_column('master_items', 'par_level')
    op.drop_column('master_items', 'vendor')

    # Drop storage_areas table
    op.drop_index('ix_storage_areas_location_id', 'storage_areas')
    op.drop_index('ix_storage_areas_id', 'storage_areas')
    op.drop_table('storage_areas')