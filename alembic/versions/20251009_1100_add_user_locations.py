"""add user_locations junction table

Revision ID: 20251009_1100
Revises: 20251007_0800
Create Date: 2025-10-09 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251009_1100'
down_revision: Union[str, None] = '20251007_0800'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_locations junction table
    op.create_table('user_locations',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'location_id')
    )

    # Create indexes for better query performance
    op.create_index('ix_user_locations_user_id', 'user_locations', ['user_id'])
    op.create_index('ix_user_locations_location_id', 'user_locations', ['location_id'])


def downgrade() -> None:
    op.drop_index('ix_user_locations_location_id', table_name='user_locations')
    op.drop_index('ix_user_locations_user_id', table_name='user_locations')
    op.drop_table('user_locations')
