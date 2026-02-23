"""Add order sheet templates and order sheets tables

Revision ID: 20260218_0001
Revises: 20260117_0001
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260218_0001'
down_revision = '20260117_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Order sheet templates (reusable item lists with par levels per location)
    op.create_table(
        'order_sheet_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('location_id', 'name', name='uq_ost_location_name'),
    )

    # Order sheet template items (master items + par levels)
    op.create_table(
        'order_sheet_template_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('order_sheet_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('master_item_id', sa.Integer(), sa.ForeignKey('master_items.id'), nullable=False),
        sa.Column('par_level', sa.Numeric(10, 3), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.UniqueConstraint('template_id', 'master_item_id', name='uq_osti_template_item'),
    )

    # Order sheets (filled-out instances)
    ordersheetstatus = sa.Enum('DRAFT', 'COMPLETED', 'SENT', name='ordersheetstatus', create_type=True)

    op.create_table(
        'order_sheets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('order_sheet_templates.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('status', ordersheetstatus, server_default='DRAFT', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_to_emails', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Order sheet items (snapshotted line items with on-hand and to-order)
    op.create_table(
        'order_sheet_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('order_sheet_id', sa.Integer(), sa.ForeignKey('order_sheets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('master_item_id', sa.Integer(), sa.ForeignKey('master_items.id'), nullable=False),
        sa.Column('par_level', sa.Numeric(10, 3), nullable=True),
        sa.Column('on_hand', sa.Numeric(10, 3), nullable=True),
        sa.Column('to_order', sa.Numeric(10, 3), nullable=True),
        sa.Column('unit_abbr', sa.String(20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('order_sheet_items')
    op.drop_table('order_sheets')
    op.drop_table('order_sheet_template_items')
    op.drop_table('order_sheet_templates')
    sa.Enum(name='ordersheetstatus').drop(op.get_bind(), checkfirst=True)
