"""add pos integration

Revision ID: 20251023_0100
Revises: 20251022_2100
Create Date: 2025-10-23 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251023_0100'
down_revision = '20251022_2100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create pos_configurations table
    op.create_table(
        'pos_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='clover'),
        sa.Column('merchant_id', sa.String(length=255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('api_environment', sa.String(length=20), nullable=False, server_default='production'),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sync_frequency_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('last_sync_date', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area_id', name='uq_pos_config_area')
    )
    op.create_index(op.f('ix_pos_configurations_area_id'), 'pos_configurations', ['area_id'], unique=False)
    op.create_index(op.f('ix_pos_configurations_is_active'), 'pos_configurations', ['is_active'], unique=False)

    # Create pos_daily_sales_cache table
    op.create_table(
        'pos_daily_sales_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=False),
        sa.Column('sale_date', sa.Date(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='clover'),
        sa.Column('total_sales', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('total_tax', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('total_tips', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('total_discounts', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('gross_sales', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
        sa.Column('transaction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('order_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('payment_methods', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('categories', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('raw_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area_id', 'sale_date', 'provider', name='uq_pos_cache_area_date_provider')
    )
    op.create_index(op.f('ix_pos_daily_sales_cache_area_id'), 'pos_daily_sales_cache', ['area_id'], unique=False)
    op.create_index(op.f('ix_pos_daily_sales_cache_sale_date'), 'pos_daily_sales_cache', ['sale_date'], unique=False)

    # Create pos_category_gl_mappings table
    op.create_table(
        'pos_category_gl_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('area_id', sa.Integer(), nullable=True),
        sa.Column('pos_category', sa.String(length=255), nullable=False),
        sa.Column('revenue_account_id', sa.Integer(), nullable=False),
        sa.Column('tax_account_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revenue_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tax_account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area_id', 'pos_category', name='uq_pos_mapping_area_category')
    )
    op.create_index(op.f('ix_pos_category_gl_mappings_area_id'), 'pos_category_gl_mappings', ['area_id'], unique=False)
    op.create_index(op.f('ix_pos_category_gl_mappings_is_active'), 'pos_category_gl_mappings', ['is_active'], unique=False)

    # Add columns to daily_sales_summaries table to track POS imports
    op.add_column('daily_sales_summaries', sa.Column('imported_from_pos', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('daily_sales_summaries', sa.Column('pos_sync_date', sa.DateTime(), nullable=True))
    op.add_column('daily_sales_summaries', sa.Column('pos_transaction_count', sa.Integer(), nullable=True))

    op.create_index(op.f('ix_daily_sales_summaries_imported_from_pos'), 'daily_sales_summaries', ['imported_from_pos'], unique=False)


def downgrade() -> None:
    # Drop indexes and columns from daily_sales_summaries
    op.drop_index(op.f('ix_daily_sales_summaries_imported_from_pos'), table_name='daily_sales_summaries')
    op.drop_column('daily_sales_summaries', 'pos_transaction_count')
    op.drop_column('daily_sales_summaries', 'pos_sync_date')
    op.drop_column('daily_sales_summaries', 'imported_from_pos')

    # Drop pos_category_gl_mappings
    op.drop_index(op.f('ix_pos_category_gl_mappings_is_active'), table_name='pos_category_gl_mappings')
    op.drop_index(op.f('ix_pos_category_gl_mappings_area_id'), table_name='pos_category_gl_mappings')
    op.drop_table('pos_category_gl_mappings')

    # Drop pos_daily_sales_cache
    op.drop_index(op.f('ix_pos_daily_sales_cache_sale_date'), table_name='pos_daily_sales_cache')
    op.drop_index(op.f('ix_pos_daily_sales_cache_area_id'), table_name='pos_daily_sales_cache')
    op.drop_table('pos_daily_sales_cache')

    # Drop pos_configurations
    op.drop_index(op.f('ix_pos_configurations_is_active'), table_name='pos_configurations')
    op.drop_index(op.f('ix_pos_configurations_area_id'), table_name='pos_configurations')
    op.drop_table('pos_configurations')
