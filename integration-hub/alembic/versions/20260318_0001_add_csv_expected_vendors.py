"""Add csv_expected_vendors table

Tracks vendor+location combinations that receive CSV invoices via fintech.
PDFs from these vendors are stored as reference only (status='pdf_reference').

Revision ID: 20260318_0001
Revises: 20260226_0001
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260318_0001'
down_revision = '20260226_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Create csv_expected_vendors table
    op.create_table(
        'csv_expected_vendors',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('vendor_id', sa.Integer(), nullable=False, index=True),
        sa.Column('location_id', sa.Integer(), nullable=True, index=True),
        sa.Column('location_name', sa.String(100), nullable=True),
        sa.Column('distributor_name', sa.String(200), nullable=True),
        sa.Column('customer_id', sa.String(100), nullable=True),
        sa.Column('store_id', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('vendor_id', 'location_id', name='uq_csv_expected_vendor_location'),
    )

    # Seed data from ActiveRelationships.csv (fintech)
    # Vendor IDs: Breakthru/Premier=2, Double Eagle/Western=3, Gold Coast Bev=4,
    #             JJ Taylor=46, Republic=6, Southern Eagle=8, Southern Glazer's=9
    # Location IDs: Seaside=1, Okee=4 (store 200), Nest=2 (store 300),
    #               SW Grill=3 (store 500), Park=5 (store 700), Links=6 (store 600)
    op.execute("""
        INSERT INTO csv_expected_vendors (vendor_id, location_id, location_name, distributor_name, customer_id, store_id, is_active) VALUES
        -- Gold Coast Beverage (vendor_id=4)
        (4, 4, 'Okee Grill', 'Gold Coast Beverage, LLC', '55672', '200', true),
        (4, 2, 'The Nest Eatery', 'Gold Coast Beverage, LLC', '54197', '300', true),
        (4, 3, 'SW Grill', 'Gold Coast Beverage, LLC', '56836', '500', true),
        (4, 5, 'Park Bistro', 'Gold Coast Beverage, LLC', '58535', '700', true),
        (4, 6, 'Links Grill', 'Gold Coast Beverage, LLC', '08651', '600', true),

        -- Breakthru Beverage / Premier (vendor_id=2)
        (2, 4, 'Okee Grill', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700419384', '200', true),
        (2, 2, 'The Nest Eatery', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700259244', '300', true),
        (2, 3, 'SW Grill', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700420166', '500', true),
        (2, 5, 'Park Bistro', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700420205', '700', true),
        (2, 1, 'Seaside Grill', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700419136', '400', true),
        (2, 6, 'Links Grill', 'Premier Beverage Co.dba Breakthru Beverage Florida', '0700419643', '600', true),

        -- Southern Eagle Distributing (vendor_id=8)
        (8, 4, 'Okee Grill', 'Southern Eagle Distributing, Inc.', '602992', '200', true),
        (8, 5, 'Park Bistro', 'Southern Eagle Distributing, Inc.', '602843', '700', true),
        (8, 1, 'Seaside Grill', 'Southern Eagle Distributing, Inc.', '18598', '400', true),
        (8, 6, 'Links Grill', 'Southern Eagle Distributing, Inc.', '607160', '600', true),

        -- Southern Glazer's (vendor_id=9)
        (9, 4, 'Okee Grill', 'Southern Glazer''s Wine & Spirits of FL', '0061708', '200', true),
        (9, 2, 'The Nest Eatery', 'Southern Glazer''s Wine & Spirits of FL', '0049748', '300', true),
        (9, 3, 'SW Grill', 'Southern Glazer''s Wine & Spirits of FL', '0070638', '500', true),
        (9, 5, 'Park Bistro', 'Southern Glazer''s Wine & Spirits of FL', '0092001', '700', true),
        (9, 1, 'Seaside Grill', 'Southern Glazer''s Wine & Spirits of FL', '0089778', '400', true),
        (9, 6, 'Links Grill', 'Southern Glazer''s Wine & Spirits of FL', '0087564', '600', true),

        -- Republic National (vendor_id=6)
        (6, 2, 'The Nest Eatery', 'Republic National Dist - Deerfield Bch.', '6017885', '300', true),
        (6, 3, 'SW Grill', 'Republic National Dist - Deerfield Bch.', '6018595', '500', true),

        -- Western Beverage / Double Eagle (vendor_id=3)
        (3, 2, 'The Nest Eatery', 'Western Beverage DBA Eagle Brands Sales', '56201', '300', true),
        (3, 3, 'SW Grill', 'Western Beverage DBA Eagle Brands Sales', '58021', '500', true),

        -- JJ Taylor (vendor_id=46)
        (46, 1, 'Seaside Grill', 'JJ Taylor Distributing - Tampa', '30957', '400', true)
    """)


def downgrade():
    op.drop_table('csv_expected_vendors')
