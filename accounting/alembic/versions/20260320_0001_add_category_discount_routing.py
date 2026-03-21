"""Add category-based discount GL routing

Add discount_account_id to pos_category_gl_mappings so each sales category
can route discounts to its contra-revenue account (e.g., Beer → 4153).
Add is_override to pos_discount_gl_mappings to mark special discounts that
always go to the same account regardless of item category (Staff Meal, Waste).

Revision ID: 20260320_0001
Revises: 20260312_0001
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260320_0001'
down_revision = '20260312_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Add discount_account_id to pos_category_gl_mappings
    op.add_column('pos_category_gl_mappings',
        sa.Column('discount_account_id', sa.Integer(),
                  sa.ForeignKey('accounts.id', ondelete='RESTRICT'),
                  nullable=True))

    # Add is_override to pos_discount_gl_mappings
    op.add_column('pos_discount_gl_mappings',
        sa.Column('is_override', sa.Boolean(), nullable=False, server_default='false'))

    # Populate discount_account_id based on revenue account patterns:
    # Food (4100) → 4101, NAB (4130) → 4131, Liquor (4145) → 4146,
    # Bottled Beer (4151) → 4153, Draft Beer (4152) → 4153,
    # Wine (4155) → 4156, Merchandise (4200) → 4101, Catering (4300) → 4101
    conn = op.get_bind()

    # Get account IDs by account number
    accounts = {}
    for row in conn.execute(sa.text("SELECT id, account_number FROM accounts WHERE account_number IN ('4101','4131','4146','4153','4156','4201')")):
        accounts[row[1]] = row[0]

    # Map revenue account → discount account
    revenue_to_discount = {
        '4100': accounts.get('4101'),  # Food → Discount Food
        '4130': accounts.get('4131'),  # NAB → Discount NAB
        '4145': accounts.get('4146'),  # Liquor → Discount Liquor
        '4151': accounts.get('4153'),  # Bottled Beer → Discount Beer
        '4152': accounts.get('4153'),  # Draft Beer → Discount Beer
        '4155': accounts.get('4156'),  # Wine → Complimentary Wine
        '4200': accounts.get('4201'),  # Merchandise → Discount Merchandise
        '4300': accounts.get('4101'),  # Catering → Discount Food (fallback)
    }

    for rev_num, disc_id in revenue_to_discount.items():
        if disc_id:
            conn.execute(sa.text(
                "UPDATE pos_category_gl_mappings SET discount_account_id = :disc_id "
                "FROM accounts WHERE accounts.id = pos_category_gl_mappings.revenue_account_id "
                "AND accounts.account_number = :rev_num"
            ), {"disc_id": disc_id, "rev_num": rev_num})

    # Mark special discount mappings as overrides
    # These always go to their mapped account regardless of category
    override_names = ['Staff Meal', 'Waste', 'Rounding Adjustment']
    for name in override_names:
        conn.execute(sa.text(
            "UPDATE pos_discount_gl_mappings SET is_override = true "
            "WHERE LOWER(pos_discount_name) = LOWER(:name)"
        ), {"name": name})


def downgrade():
    op.drop_column('pos_discount_gl_mappings', 'is_override')
    op.drop_column('pos_category_gl_mappings', 'discount_account_id')
