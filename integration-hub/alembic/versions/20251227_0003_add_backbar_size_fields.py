"""Add Backbar-style size fields to hub_vendor_items

Revision ID: 20251227_0003
Revises: 20251227_0002
Create Date: 2025-12-27

This migration adds the Backbar-style sizing model:
- hub_size_units table: volume/weight/count units with conversion factors
- hub_containers table: bottle, can, bag, etc.
- New fields on hub_vendor_items: size_quantity, size_unit_id, container_id, units_per_case, case_cost
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251227_0003'
down_revision = '20251227_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create hub_size_units table
    op.create_table(
        'hub_size_units',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False, unique=True),
        sa.Column('measure_type', sa.String(20), nullable=False),
        sa.Column('base_unit_symbol', sa.String(20), nullable=False),
        sa.Column('conversion_to_base', sa.Numeric(15, 6), nullable=False, server_default='1.0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
    )

    # Create hub_containers table
    op.create_table(
        'hub_containers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
    )

    # Seed size units
    op.execute("""
        INSERT INTO hub_size_units (name, symbol, measure_type, base_unit_symbol, conversion_to_base, sort_order) VALUES
        -- Volume units
        ('Milliliter', 'ml', 'volume', 'ml', 1, 1),
        ('Centiliter', 'cl', 'volume', 'ml', 10, 2),
        ('Liter', 'L', 'volume', 'ml', 1000, 3),
        ('Fluid Ounce', 'fl oz', 'volume', 'ml', 29.5735, 4),
        ('Gallon', 'gal', 'volume', 'ml', 3785.41, 5),
        -- Weight units
        ('Gram', 'g', 'weight', 'g', 1, 10),
        ('Kilogram', 'kg', 'weight', 'g', 1000, 11),
        ('Ounce', 'oz', 'weight', 'g', 28.3495, 12),
        ('Pound', 'lb', 'weight', 'g', 453.592, 13),
        -- Count units
        ('Each', 'each', 'count', 'each', 1, 20),
        ('Count', 'count', 'count', 'each', 1, 21)
    """)

    # Seed containers
    op.execute("""
        INSERT INTO hub_containers (name, sort_order) VALUES
        ('bottle', 1),
        ('can', 2),
        ('keg', 3),
        ('box', 4),
        ('bag', 5),
        ('carton', 6),
        ('jar', 7),
        ('pouch', 8),
        ('bucket', 9),
        ('tub', 10),
        ('jug', 11),
        ('sleeve', 12),
        ('cask', 13),
        ('growler', 14),
        ('firkin', 15),
        ('each', 16),
        ('unit', 17)
    """)

    # Add new Backbar-style fields to hub_vendor_items
    op.add_column('hub_vendor_items', sa.Column('size_quantity', sa.Numeric(10, 4), nullable=True))
    op.add_column('hub_vendor_items', sa.Column('size_unit_id', sa.Integer(), nullable=True))
    op.add_column('hub_vendor_items', sa.Column('container_id', sa.Integer(), nullable=True))
    op.add_column('hub_vendor_items', sa.Column('units_per_case', sa.Integer(), nullable=True))
    op.add_column('hub_vendor_items', sa.Column('case_cost', sa.Numeric(10, 4), nullable=True))

    # Add foreign keys
    op.create_foreign_key(
        'fk_hub_vendor_items_size_unit',
        'hub_vendor_items', 'hub_size_units',
        ['size_unit_id'], ['id']
    )
    op.create_foreign_key(
        'fk_hub_vendor_items_container',
        'hub_vendor_items', 'hub_containers',
        ['container_id'], ['id']
    )

    # Create indexes
    op.create_index('ix_hub_vendor_items_size_unit_id', 'hub_vendor_items', ['size_unit_id'])
    op.create_index('ix_hub_vendor_items_container_id', 'hub_vendor_items', ['container_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_hub_vendor_items_container_id', table_name='hub_vendor_items')
    op.drop_index('ix_hub_vendor_items_size_unit_id', table_name='hub_vendor_items')

    # Drop foreign keys
    op.drop_constraint('fk_hub_vendor_items_container', 'hub_vendor_items', type_='foreignkey')
    op.drop_constraint('fk_hub_vendor_items_size_unit', 'hub_vendor_items', type_='foreignkey')

    # Drop columns from hub_vendor_items
    op.drop_column('hub_vendor_items', 'case_cost')
    op.drop_column('hub_vendor_items', 'units_per_case')
    op.drop_column('hub_vendor_items', 'container_id')
    op.drop_column('hub_vendor_items', 'size_unit_id')
    op.drop_column('hub_vendor_items', 'size_quantity')

    # Drop tables
    op.drop_table('hub_containers')
    op.drop_table('hub_size_units')
