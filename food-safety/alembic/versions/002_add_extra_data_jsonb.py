"""Add extra_data JSONB column to incidents table

Revision ID: 002
Revises: 001
Create Date: 2026-02-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('extra_data', JSONB, nullable=True, server_default='{}'))

    # Add missing incident type enum values (workplace safety, security types)
    new_types = [
        'WORKPLACE_INJURY', 'SLIP_FALL', 'BURN', 'CUT_LACERATION',
        'CHEMICAL_EXPOSURE', 'FIRE_HAZARD', 'ELECTRICAL_HAZARD',
        'PROPERTY_DAMAGE', 'NEAR_MISS', 'SECURITY_INCIDENT',
        'CUSTOMER_INJURY', 'VEHICLE_INCIDENT'
    ]
    for t in new_types:
        op.execute(f"ALTER TYPE incidenttype ADD VALUE IF NOT EXISTS '{t}'")


def downgrade() -> None:
    op.drop_column('incidents', 'extra_data')
    # Note: PostgreSQL does not support removing enum values
