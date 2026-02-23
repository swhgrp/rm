"""Make order sheet quantities whole numbers (Integer instead of Numeric)

Revision ID: 20260218_0003
Revises: 20260218_0002
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260218_0003'
down_revision = '20260218_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # order_sheet_template_items: par_level Numeric → Integer
    op.alter_column('order_sheet_template_items', 'par_level',
                     type_=sa.Integer(),
                     existing_type=sa.Numeric(10, 3),
                     postgresql_using='par_level::integer')

    # order_sheet_items: par_level, on_hand, to_order Numeric → Integer
    op.alter_column('order_sheet_items', 'par_level',
                     type_=sa.Integer(),
                     existing_type=sa.Numeric(10, 3),
                     postgresql_using='par_level::integer')
    op.alter_column('order_sheet_items', 'on_hand',
                     type_=sa.Integer(),
                     existing_type=sa.Numeric(10, 3),
                     postgresql_using='on_hand::integer')
    op.alter_column('order_sheet_items', 'to_order',
                     type_=sa.Integer(),
                     existing_type=sa.Numeric(10, 3),
                     postgresql_using='to_order::integer')


def downgrade() -> None:
    op.alter_column('order_sheet_items', 'to_order',
                     type_=sa.Numeric(10, 3),
                     existing_type=sa.Integer())
    op.alter_column('order_sheet_items', 'on_hand',
                     type_=sa.Numeric(10, 3),
                     existing_type=sa.Integer())
    op.alter_column('order_sheet_items', 'par_level',
                     type_=sa.Numeric(10, 3),
                     existing_type=sa.Integer())
    op.alter_column('order_sheet_template_items', 'par_level',
                     type_=sa.Numeric(10, 3),
                     existing_type=sa.Integer())
