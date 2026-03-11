"""Add structured recipe fields (category, yield, prep/cook time)

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("category", sa.String(50), nullable=True))
    op.add_column("recipes", sa.Column("yield_quantity", sa.String(50), nullable=True))
    op.add_column("recipes", sa.Column("yield_unit", sa.String(50), nullable=True))
    op.add_column("recipes", sa.Column("prep_time_minutes", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("cook_time_minutes", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("ingredients_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "ingredients_json")
    op.drop_column("recipes", "cook_time_minutes")
    op.drop_column("recipes", "prep_time_minutes")
    op.drop_column("recipes", "yield_unit")
    op.drop_column("recipes", "yield_quantity")
    op.drop_column("recipes", "category")
