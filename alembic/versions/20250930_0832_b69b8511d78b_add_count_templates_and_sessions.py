"""add_count_templates_and_sessions

Revision ID: b69b8511d78b
Revises: 6c648cca79b0
Create Date: 2025-09-30 08:32:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b69b8511d78b'
down_revision = '6c648cca79b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add barcode_type to master_items
    op.add_column('master_items', sa.Column('barcode_type', sa.String(), nullable=True))
    op.create_index('ix_master_items_barcode', 'master_items', ['barcode'])

    # Create count_templates table
    op.create_table('count_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('storage_area_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['storage_area_id'], ['storage_areas.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_count_templates_id'), 'count_templates', ['id'], unique=False)

    # Create count_template_items table
    op.create_table('count_template_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('master_item_id', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['master_item_id'], ['master_items.id'], ),
        sa.ForeignKeyConstraint(['template_id'], ['count_templates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_count_template_items_id'), 'count_template_items', ['id'], unique=False)

    # Create count status enum
    op.execute("CREATE TYPE countstatus AS ENUM ('IN_PROGRESS', 'COMPLETED', 'APPROVED', 'CANCELLED')")

    # Create count_sessions table
    op.create_table('count_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('storage_area_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('IN_PROGRESS', 'COMPLETED', 'APPROVED', 'CANCELLED', name='countstatus'), nullable=False),
        sa.Column('locked', sa.Boolean(), nullable=True, default=False),
        sa.Column('started_by', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_by', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['started_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['storage_area_id'], ['storage_areas.id'], ),
        sa.ForeignKeyConstraint(['template_id'], ['count_templates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_count_sessions_id'), 'count_sessions', ['id'], unique=False)

    # Create count_session_items table
    op.create_table('count_session_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('master_item_id', sa.Integer(), nullable=False),
        sa.Column('inventory_id', sa.Integer(), nullable=True),
        sa.Column('expected_quantity', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('counted_quantity', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('variance', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('variance_percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('flagged', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_new_item', sa.Boolean(), nullable=True, default=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('counted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('counted_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['counted_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['inventory_id'], ['inventory.id'], ),
        sa.ForeignKeyConstraint(['master_item_id'], ['master_items.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['count_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_count_session_items_id'), 'count_session_items', ['id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_count_session_items_id'), table_name='count_session_items')
    op.drop_table('count_session_items')

    op.drop_index(op.f('ix_count_sessions_id'), table_name='count_sessions')
    op.drop_table('count_sessions')

    op.execute('DROP TYPE countstatus')

    op.drop_index(op.f('ix_count_template_items_id'), table_name='count_template_items')
    op.drop_table('count_template_items')

    op.drop_index(op.f('ix_count_templates_id'), table_name='count_templates')
    op.drop_table('count_templates')

    # Remove barcode_type and index from master_items
    op.drop_index('ix_master_items_barcode', table_name='master_items')
    op.drop_column('master_items', 'barcode_type')