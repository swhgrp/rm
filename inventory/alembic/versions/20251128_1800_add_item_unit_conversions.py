"""
Add item-specific unit conversions table

For items like sausage patties where:
- Purchase unit: Pound (LB)
- Count unit: Each (2oz patties)
- Conversion: 1 LB = 8 patties (16oz / 2oz)

Create Date: 2025-11-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_item_unit_conversions'
down_revision = 'add_key_item_count_units'
branch_labels = None
depends_on = None

def upgrade():
    # Create item_unit_conversions table for item-specific unit conversions
    op.create_table(
        'item_unit_conversions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('master_item_id', sa.Integer(), nullable=False),

        # The source unit (e.g., Pound)
        sa.Column('from_unit_id', sa.Integer(), nullable=False),

        # The target unit (e.g., Each)
        sa.Column('to_unit_id', sa.Integer(), nullable=False),

        # Conversion factor: how many "to_units" in one "from_unit"
        # Example: 1 LB = 8 patties -> conversion_factor = 8
        sa.Column('conversion_factor', sa.Numeric(20, 6), nullable=False),

        # Optional: individual unit weight/volume for reference
        # Example: each patty is 2 oz
        sa.Column('individual_weight_oz', sa.Numeric(10, 4), nullable=True),
        sa.Column('individual_volume_oz', sa.Numeric(10, 4), nullable=True),

        # Notes for clarity
        sa.Column('notes', sa.Text(), nullable=True),

        # Status and timestamps
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['master_item_id'], ['master_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_unit_id'], ['units_of_measure.id']),
        sa.ForeignKeyConstraint(['to_unit_id'], ['units_of_measure.id']),
    )

    # Create index for faster lookups
    op.create_index('ix_item_unit_conversions_master_item_id', 'item_unit_conversions', ['master_item_id'])

    # Unique constraint: only one conversion per item per unit pair
    op.create_unique_constraint(
        'uq_item_unit_conversion',
        'item_unit_conversions',
        ['master_item_id', 'from_unit_id', 'to_unit_id']
    )


def downgrade():
    op.drop_index('ix_item_unit_conversions_master_item_id', table_name='item_unit_conversions')
    op.drop_table('item_unit_conversions')
