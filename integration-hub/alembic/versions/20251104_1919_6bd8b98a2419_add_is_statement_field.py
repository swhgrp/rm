"""add_is_statement_field

Revision ID: 6bd8b98a2419
Revises: d609c0b4e864
Create Date: 2025-11-04 19:19:29.722384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bd8b98a2419'
down_revision: Union[str, None] = 'd609c0b4e864'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_statement column
    op.add_column('hub_invoices', sa.Column('is_statement', sa.Boolean(), nullable=True))
    # Set default value for existing rows
    op.execute("UPDATE hub_invoices SET is_statement = FALSE WHERE is_statement IS NULL")
    # Make column non-nullable
    op.alter_column('hub_invoices', 'is_statement', nullable=False, server_default=sa.false())
    # Create index
    op.create_index(op.f('ix_hub_invoices_is_statement'), 'hub_invoices', ['is_statement'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hub_invoices_is_statement'), table_name='hub_invoices')
    op.drop_column('hub_invoices', 'is_statement')
