"""add_starting_pay_rate_to_employees

Revision ID: d56ff029a98b
Revises: 96d068f0529c
Create Date: 2025-10-16 03:39:43.413362+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd56ff029a98b'
down_revision = '20251015_1700'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add starting_pay_rate column to employees table
    op.add_column('employees', sa.Column('starting_pay_rate', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    # Remove starting_pay_rate column from employees table
    op.drop_column('employees', 'starting_pay_rate')
