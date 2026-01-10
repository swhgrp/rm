"""Initial migration - create all tables

Revision ID: 001
Revises:
Create Date: 2026-01-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Equipment categories
    op.create_table(
        'equipment_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['parent_id'], ['equipment_categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_categories_id'), 'equipment_categories', ['id'], unique=False)

    # Equipment
    op.create_table(
        'equipment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('serial_number', sa.String(100), nullable=True),
        sa.Column('model_number', sa.String(100), nullable=True),
        sa.Column('manufacturer', sa.String(200), nullable=True),
        sa.Column('qr_code', sa.String(100), nullable=True),
        sa.Column('status', sa.Enum('operational', 'needs_maintenance', 'under_repair', 'out_of_service', 'retired', name='equipmentstatus'), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('warranty_expiration', sa.Date(), nullable=True),
        sa.Column('installation_date', sa.Date(), nullable=True),
        sa.Column('last_maintenance_date', sa.Date(), nullable=True),
        sa.Column('next_maintenance_date', sa.Date(), nullable=True),
        sa.Column('purchase_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('specifications', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['equipment_categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_id'), 'equipment', ['id'], unique=False)
    op.create_index(op.f('ix_equipment_location_id'), 'equipment', ['location_id'], unique=False)
    op.create_index(op.f('ix_equipment_serial_number'), 'equipment', ['serial_number'], unique=False)
    op.create_index(op.f('ix_equipment_qr_code'), 'equipment', ['qr_code'], unique=True)
    op.create_index('ix_equipment_location_status', 'equipment', ['location_id', 'status'], unique=False)

    # Equipment history
    op.create_table(
        'equipment_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_history_id'), 'equipment_history', ['id'], unique=False)
    op.create_index(op.f('ix_equipment_history_equipment_id'), 'equipment_history', ['equipment_id'], unique=False)

    # Vendors
    op.create_table(
        'vendors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('contact_name', sa.String(200), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('service_types', sa.Text(), nullable=True),
        sa.Column('contract_number', sa.String(100), nullable=True),
        sa.Column('contract_expiration', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vendors_id'), 'vendors', ['id'], unique=False)

    # Maintenance schedules
    op.create_table(
        'maintenance_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('frequency', sa.Enum('daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'semiannual', 'annual', 'custom', name='schedulefrequency'), nullable=False),
        sa.Column('custom_interval_days', sa.Integer(), nullable=True),
        sa.Column('last_performed', sa.Date(), nullable=True),
        sa.Column('next_due', sa.Date(), nullable=False),
        sa.Column('estimated_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('checklist', sa.Text(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('is_external', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_schedules_id'), 'maintenance_schedules', ['id'], unique=False)
    op.create_index(op.f('ix_maintenance_schedules_equipment_id'), 'maintenance_schedules', ['equipment_id'], unique=False)

    # Work orders
    op.create_table(
        'work_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=True),
        sa.Column('schedule_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'critical', name='workorderpriority'), nullable=False),
        sa.Column('status', sa.Enum('open', 'in_progress', 'on_hold', 'completed', 'cancelled', name='workorderstatus'), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('reported_by', sa.Integer(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('is_external', sa.Boolean(), nullable=True),
        sa.Column('vendor_id', sa.Integer(), nullable=True),
        sa.Column('reported_date', sa.DateTime(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('started_date', sa.DateTime(), nullable=True),
        sa.Column('completed_date', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('actual_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('labor_hours', sa.Numeric(6, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
        sa.ForeignKeyConstraint(['schedule_id'], ['maintenance_schedules.id'], ),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_orders_id'), 'work_orders', ['id'], unique=False)
    op.create_index(op.f('ix_work_orders_equipment_id'), 'work_orders', ['equipment_id'], unique=False)
    op.create_index(op.f('ix_work_orders_location_id'), 'work_orders', ['location_id'], unique=False)
    op.create_index('ix_work_orders_status_priority', 'work_orders', ['status', 'priority'], unique=False)
    op.create_index('ix_work_orders_location_status', 'work_orders', ['location_id', 'status'], unique=False)

    # Work order comments
    op.create_table(
        'work_order_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('is_internal', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_comments_id'), 'work_order_comments', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_comments_work_order_id'), 'work_order_comments', ['work_order_id'], unique=False)

    # Work order parts
    op.create_table(
        'work_order_parts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_order_id', sa.Integer(), nullable=False),
        sa.Column('part_name', sa.String(200), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=True),
        sa.Column('quantity', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['work_order_id'], ['work_orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_order_parts_id'), 'work_order_parts', ['id'], unique=False)
    op.create_index(op.f('ix_work_order_parts_work_order_id'), 'work_order_parts', ['work_order_id'], unique=False)


def downgrade() -> None:
    op.drop_table('work_order_parts')
    op.drop_table('work_order_comments')
    op.drop_table('work_orders')
    op.drop_table('maintenance_schedules')
    op.drop_table('vendors')
    op.drop_table('equipment_history')
    op.drop_table('equipment')
    op.drop_table('equipment_categories')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS workorderstatus')
    op.execute('DROP TYPE IF EXISTS workorderpriority')
    op.execute('DROP TYPE IF EXISTS schedulefrequency')
    op.execute('DROP TYPE IF EXISTS equipmentstatus')
