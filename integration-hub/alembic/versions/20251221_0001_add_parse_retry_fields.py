"""Add parse retry tracking fields to hub_invoices

Revision ID: 20251221_0001
Revises: 6bd8b98a2419
Create Date: 2025-12-21

Adds fields to track parse attempts, errors, and retry scheduling:
- parse_attempts: Number of times parsing has been attempted
- parse_error: Last parse error message
- next_parse_retry_at: When to next attempt parsing
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251221_0001'
down_revision = '6bd8b98a2419'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add parse retry tracking fields
    op.add_column('hub_invoices', sa.Column('parse_attempts', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('hub_invoices', sa.Column('parse_error', sa.Text(), nullable=True))
    op.add_column('hub_invoices', sa.Column('next_parse_retry_at', sa.DateTime(timezone=True), nullable=True))

    # Update existing pending invoices that have never been parsed to have 0 attempts
    op.execute("""
        UPDATE hub_invoices
        SET parse_attempts = 0
        WHERE parse_attempts IS NULL
    """)

    # Create index for efficient retry queries
    op.create_index('ix_hub_invoices_next_parse_retry', 'hub_invoices', ['next_parse_retry_at'],
                    postgresql_where=sa.text("next_parse_retry_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index('ix_hub_invoices_next_parse_retry', table_name='hub_invoices')
    op.drop_column('hub_invoices', 'next_parse_retry_at')
    op.drop_column('hub_invoices', 'parse_error')
    op.drop_column('hub_invoices', 'parse_attempts')
