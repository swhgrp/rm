"""Seed category GL mappings

Revision ID: 002
Revises: 001
Create Date: 2025-10-19 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Seed category_gl_mapping table with default GL account mappings

    Based on chart of accounts mapping:
    - Asset Accounts: 1400-1499 (Inventory)
    - COGS Accounts: 5100-5199 (Cost of Goods Sold)
    - Waste Accounts: 7180-7183 (Waste Expense)
    """

    # Create category mappings
    op.execute("""
        INSERT INTO category_gl_mapping (inventory_category, display_name, gl_asset_account, gl_cogs_account, gl_waste_account)
        VALUES
            ('produce', 'Produce', 1405, 5105, 7180),
            ('dairy', 'Dairy', 1410, 5110, 7180),
            ('poultry', 'Poultry', 1418, 5118, 7180),
            ('beef', 'Beef', 1417, 5117, 7180),
            ('seafood', 'Seafood', 1420, 5120, 7180),
            ('pork', 'Pork', 1422, 5122, 7180),
            ('lamb', 'Lamb', 1425, 5125, 7180),
            ('dry_goods', 'Dry Goods', 1430, 5130, 7180),
            ('frozen', 'Frozen Foods', 1435, 5135, 7180),
            ('paper_goods', 'Paper Goods', 1440, 5140, NULL),
            ('cleaning_supplies', 'Cleaning Supplies', 1445, 5145, NULL),
            ('beverage_na', 'Non-Alcoholic Beverages', 1447, 5147, 7181),
            ('beer_draft', 'Beer - Draft', 1450, 5150, 7182),
            ('beer_bottled', 'Beer - Bottled/Canned', 1452, 5152, 7182),
            ('wine', 'Wine', 1455, 5155, 7182),
            ('liquor', 'Liquor/Spirits', 1460, 5160, 7182),
            ('supplies', 'Supplies', 1465, 5165, NULL),
            ('merchandise', 'Merchandise', 1470, 5170, 7183)
        ON CONFLICT (inventory_category) DO NOTHING;
    """)


def downgrade() -> None:
    """Remove seeded category mappings"""
    op.execute("""
        DELETE FROM category_gl_mapping
        WHERE inventory_category IN (
            'produce', 'dairy', 'poultry', 'beef', 'seafood', 'pork', 'lamb',
            'dry_goods', 'frozen', 'paper_goods', 'cleaning_supplies',
            'beverage_na', 'beer_draft', 'beer_bottled', 'wine', 'liquor',
            'supplies', 'merchandise'
        );
    """)
