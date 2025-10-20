"""add locations and user_locations tables

Revision ID: 20251015_1700
Revises: 20251015_1600
Create Date: 2025-10-15 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision = '20251015_1700'
down_revision = '20251015_1600'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create locations table
    op.create_table(
        'locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(2), nullable=True),
        sa.Column('zip_code', sa.String(10), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('manager_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_locations_id'), 'locations', ['id'], unique=False)
    op.create_index(op.f('ix_locations_name'), 'locations', ['name'], unique=False)

    # Create user_locations junction table
    op.create_table(
        'user_locations',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'location_id')
    )
    op.create_index(op.f('ix_user_locations_user_id'), 'user_locations', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_locations_location_id'), 'user_locations', ['location_id'], unique=False)


def downgrade() -> None:
    # Drop user_locations table
    op.drop_index(op.f('ix_user_locations_location_id'), table_name='user_locations')
    op.drop_index(op.f('ix_user_locations_user_id'), table_name='user_locations')
    op.drop_table('user_locations')

    # Drop locations table
    op.drop_index(op.f('ix_locations_name'), table_name='locations')
    op.drop_index(op.f('ix_locations_id'), table_name='locations')
    op.drop_table('locations')
