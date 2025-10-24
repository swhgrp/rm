"""Create system settings table

Revision ID: 20251023_1100
Revises: 20251023_1000
Create Date: 2025-10-23 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251023_1100'
down_revision = '20251023_1000'
branch_labels = None
depends_on = None


def upgrade():
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('setting_value', sa.Text(), nullable=True),
        sa.Column('setting_type', sa.String(length=20), nullable=False, server_default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('setting_key'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL')
    )

    # Create index on setting_key for faster lookups
    op.create_index('ix_system_settings_key', 'system_settings', ['setting_key'])

    # Insert default settings
    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description)
        VALUES
            ('cash_over_short_account_id', '7250', 'account_id', 'GL Account for Cash Over/Short variances'),
            ('company_name', 'SW Hospitality Group', 'string', 'Company name'),
            ('base_currency', 'USD', 'string', 'Base currency'),
            ('fiscal_year_end', '12-31', 'string', 'Fiscal year end (MM-DD)'),
            ('decimal_places', '2', 'integer', 'Number of decimal places for currency'),
            ('auto_journal_numbering', 'true', 'boolean', 'Auto-generate journal entry numbers')
    """)


def downgrade():
    op.drop_index('ix_system_settings_key', table_name='system_settings')
    op.drop_table('system_settings')
