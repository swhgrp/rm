"""make_location_id_nullable

Revision ID: 6c648cca79b0
Revises: 004
Create Date: 2025-09-30 08:22:51.278457+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6c648cca79b0'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make location_id nullable since it can be inferred from storage_area
    op.alter_column('inventory', 'location_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)


def downgrade() -> None:
    # Revert to NOT NULL
    op.alter_column('inventory', 'location_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)