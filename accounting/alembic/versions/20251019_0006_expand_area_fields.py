"""Expand area fields for legal entity information

Revision ID: 20251019_0006
Revises: 20251019_0005
Create Date: 2025-10-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251019_0006'
down_revision = '20251019_0005'
branch_labels = None
depends_on = None


def upgrade():
    """Add legal entity and contact fields to areas table"""

    # Add legal entity information
    op.add_column('areas', sa.Column('legal_name', sa.String(200), nullable=True))
    op.add_column('areas', sa.Column('ein', sa.String(20), nullable=True))
    op.add_column('areas', sa.Column('entity_type', sa.String(50), nullable=True))

    # Add address information
    op.add_column('areas', sa.Column('address_line1', sa.String(200), nullable=True))
    op.add_column('areas', sa.Column('address_line2', sa.String(200), nullable=True))
    op.add_column('areas', sa.Column('city', sa.String(100), nullable=True))
    op.add_column('areas', sa.Column('state', sa.String(50), nullable=True))
    op.add_column('areas', sa.Column('zip_code', sa.String(20), nullable=True))
    op.add_column('areas', sa.Column('country', sa.String(100), nullable=True, server_default='United States'))

    # Add contact information
    op.add_column('areas', sa.Column('phone', sa.String(20), nullable=True))
    op.add_column('areas', sa.Column('email', sa.String(100), nullable=True))
    op.add_column('areas', sa.Column('website', sa.String(200), nullable=True))


def downgrade():
    """Remove added fields from areas table"""

    # Remove contact information
    op.drop_column('areas', 'website')
    op.drop_column('areas', 'email')
    op.drop_column('areas', 'phone')

    # Remove address information
    op.drop_column('areas', 'country')
    op.drop_column('areas', 'zip_code')
    op.drop_column('areas', 'state')
    op.drop_column('areas', 'city')
    op.drop_column('areas', 'address_line2')
    op.drop_column('areas', 'address_line1')

    # Remove legal entity information
    op.drop_column('areas', 'entity_type')
    op.drop_column('areas', 'ein')
    op.drop_column('areas', 'legal_name')
