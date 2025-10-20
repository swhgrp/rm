"""add vendors table

Revision ID: 20251019_1500
Revises: 20251019_0008
Create Date: 2025-10-19 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251019_1500'
down_revision = '20251019_0008'  # Previous migration
branch_labels = None
depends_on = None


def upgrade():
    # Create vendors table
    op.create_table(
        'vendors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_name', sa.String(length=200), nullable=False),
        sa.Column('vendor_code', sa.String(length=50), nullable=True),
        sa.Column('contact_name', sa.String(length=200), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('fax', sa.String(length=20), nullable=True),
        sa.Column('website', sa.String(length=200), nullable=True),
        sa.Column('address_line1', sa.String(length=200), nullable=True),
        sa.Column('address_line2', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=50), nullable=True),
        sa.Column('zip_code', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True, server_default='United States'),
        sa.Column('tax_id', sa.String(length=50), nullable=True),
        sa.Column('is_1099_vendor', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('payment_terms', sa.String(length=50), nullable=True),
        sa.Column('credit_limit', sa.Integer(), nullable=True),
        sa.Column('account_number', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_vendors_id', 'vendors', ['id'])
    op.create_index('ix_vendors_vendor_name', 'vendors', ['vendor_name'], unique=True)
    op.create_index('ix_vendors_vendor_code', 'vendors', ['vendor_code'], unique=True)


def downgrade():
    op.drop_index('ix_vendors_vendor_code', table_name='vendors')
    op.drop_index('ix_vendors_vendor_name', table_name='vendors')
    op.drop_index('ix_vendors_id', table_name='vendors')
    op.drop_table('vendors')
