"""add_email_monitoring_fields

Revision ID: 534492aec643
Revises: 124329d95960
Create Date: 2025-10-31 03:45:04.037043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '534492aec643'
down_revision: Union[str, None] = '124329d95960'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email monitoring fields to hub_invoices (pdf_path already exists from earlier migration)
    op.add_column('hub_invoices', sa.Column('invoice_hash', sa.String(length=64), nullable=True, index=True))
    op.add_column('hub_invoices', sa.Column('email_subject', sa.String(length=500), nullable=True))
    op.add_column('hub_invoices', sa.Column('email_from', sa.String(length=200), nullable=True))
    op.add_column('hub_invoices', sa.Column('email_received_at', sa.DateTime(timezone=True), nullable=True))

    # Add unique constraint on invoice_hash separately (can't be part of add_column)
    op.create_unique_constraint('uq_hub_invoices_invoice_hash', 'hub_invoices', ['invoice_hash'])


def downgrade() -> None:
    op.drop_constraint('uq_hub_invoices_invoice_hash', 'hub_invoices')
    op.drop_column('hub_invoices', 'email_received_at')
    op.drop_column('hub_invoices', 'email_from')
    op.drop_column('hub_invoices', 'email_subject')
    op.drop_column('hub_invoices', 'invoice_hash')
