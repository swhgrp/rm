"""Change sync_frequency_minutes to sync_time

Revision ID: 20251023_1400
Revises: 20251023_1300
Create Date: 2025-10-23 14:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_1400'
down_revision = '20251023_1300'
branch_labels = None
depends_on = None


def upgrade():
    # Add new sync_time column
    op.add_column('pos_configurations', sa.Column('sync_time', sa.String(5), nullable=False, server_default='02:00'))
    
    # Drop old sync_frequency_minutes column
    op.drop_column('pos_configurations', 'sync_frequency_minutes')


def downgrade():
    # Add back sync_frequency_minutes column
    op.add_column('pos_configurations', sa.Column('sync_frequency_minutes', sa.Integer(), nullable=False, server_default='60'))
    
    # Drop sync_time column
    op.drop_column('pos_configurations', 'sync_time')
