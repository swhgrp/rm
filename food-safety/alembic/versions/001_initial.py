"""Initial migration - create all tables

Revision ID: 001
Revises:
Create Date: 2026-01-10

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
    # ========== USER PERMISSIONS ==========
    op.create_table(
        'user_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hr_user_id', sa.Integer(), nullable=False),
        sa.Column('employee_name', sa.String(200), nullable=True),
        sa.Column('employee_email', sa.String(200), nullable=True),
        sa.Column('role', sa.Enum('admin', 'manager', 'supervisor', 'staff', 'readonly', name='userrole'), nullable=False),
        sa.Column('location_ids', sa.String(500), nullable=True),
        sa.Column('can_manage_templates', sa.Boolean(), nullable=True),
        sa.Column('can_manage_users', sa.Boolean(), nullable=True),
        sa.Column('can_view_reports', sa.Boolean(), nullable=True),
        sa.Column('can_sign_off', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_permissions_id'), 'user_permissions', ['id'], unique=False)
    op.create_index(op.f('ix_user_permissions_hr_user_id'), 'user_permissions', ['hr_user_id'], unique=True)
    op.create_index('ix_user_permissions_role_active', 'user_permissions', ['role', 'is_active'], unique=False)

    # ========== LOCATIONS ==========
    op.create_table(
        'locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inventory_location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_locations_id'), 'locations', ['id'], unique=False)
    op.create_index(op.f('ix_locations_inventory_location_id'), 'locations', ['inventory_location_id'], unique=True)

    # ========== SHIFTS ==========
    op.create_table(
        'shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shifts_id'), 'shifts', ['id'], unique=False)
    op.create_index(op.f('ix_shifts_location_id'), 'shifts', ['location_id'], unique=False)
    op.create_index('ix_shifts_location_active', 'shifts', ['location_id', 'is_active'], unique=False)

    # ========== EQUIPMENT ==========
    op.create_table(
        'equipment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('equipment_type', sa.String(100), nullable=False),
        sa.Column('serial_number', sa.String(100), nullable=True),
        sa.Column('asset_tag', sa.String(100), nullable=True),
        sa.Column('min_temp', sa.Numeric(5, 2), nullable=True),
        sa.Column('max_temp', sa.Numeric(5, 2), nullable=True),
        sa.Column('temp_unit', sa.String(1), nullable=True),
        sa.Column('area', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_id'), 'equipment', ['id'], unique=False)
    op.create_index(op.f('ix_equipment_location_id'), 'equipment', ['location_id'], unique=False)
    op.create_index(op.f('ix_equipment_asset_tag'), 'equipment', ['asset_tag'], unique=False)
    op.create_index('ix_equipment_location_type', 'equipment', ['location_id', 'equipment_type'], unique=False)

    # ========== TEMPERATURE THRESHOLDS ==========
    op.create_table(
        'temperature_thresholds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('equipment_type', sa.String(100), nullable=False),
        sa.Column('min_temp', sa.Numeric(5, 2), nullable=False),
        sa.Column('max_temp', sa.Numeric(5, 2), nullable=False),
        sa.Column('temp_unit', sa.String(1), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('alert_on_violation', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_temperature_thresholds_id'), 'temperature_thresholds', ['id'], unique=False)
    op.create_index(op.f('ix_temperature_thresholds_equipment_type'), 'temperature_thresholds', ['equipment_type'], unique=True)

    # ========== TEMPERATURE LOGS ==========
    op.create_table(
        'temperature_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('temperature', sa.Numeric(5, 2), nullable=False),
        sa.Column('temp_unit', sa.String(1), nullable=True),
        sa.Column('min_threshold', sa.Numeric(5, 2), nullable=True),
        sa.Column('max_threshold', sa.Numeric(5, 2), nullable=True),
        sa.Column('is_within_range', sa.Boolean(), nullable=False),
        sa.Column('alert_status', sa.Enum('active', 'acknowledged', 'resolved', name='temperaturealertstatus'), nullable=True),
        sa.Column('alert_acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('alert_acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('alert_notes', sa.Text(), nullable=True),
        sa.Column('corrective_action', sa.Text(), nullable=True),
        sa.Column('logged_by', sa.Integer(), nullable=False),
        sa.Column('logged_at', sa.DateTime(), nullable=True),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_temperature_logs_id'), 'temperature_logs', ['id'], unique=False)
    op.create_index(op.f('ix_temperature_logs_equipment_id'), 'temperature_logs', ['equipment_id'], unique=False)
    op.create_index(op.f('ix_temperature_logs_location_id'), 'temperature_logs', ['location_id'], unique=False)
    op.create_index(op.f('ix_temperature_logs_logged_at'), 'temperature_logs', ['logged_at'], unique=False)
    op.create_index('ix_temp_logs_equipment_date', 'temperature_logs', ['equipment_id', 'logged_at'], unique=False)
    op.create_index('ix_temp_logs_location_date', 'temperature_logs', ['location_id', 'logged_at'], unique=False)
    op.create_index('ix_temp_logs_alert_status', 'temperature_logs', ['alert_status'], unique=False)

    # ========== CHECKLIST TEMPLATES ==========
    op.create_table(
        'checklist_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('checklist_type', sa.Enum('opening', 'closing', 'shift_change', 'temperature', 'cleaning', 'receiving', 'prep', 'custom', name='checklisttype'), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('frequency', sa.String(50), nullable=False),
        sa.Column('requires_manager_signoff', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_checklist_templates_id'), 'checklist_templates', ['id'], unique=False)
    op.create_index(op.f('ix_checklist_templates_location_id'), 'checklist_templates', ['location_id'], unique=False)
    op.create_index('ix_checklist_templates_type_active', 'checklist_templates', ['checklist_type', 'is_active'], unique=False)
    op.create_index('ix_checklist_templates_location', 'checklist_templates', ['location_id', 'is_active'], unique=False)

    # ========== CHECKLIST ITEMS ==========
    op.create_table(
        'checklist_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('response_type', sa.String(50), nullable=False),
        sa.Column('min_value', sa.String(50), nullable=True),
        sa.Column('max_value', sa.String(50), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('section', sa.String(100), nullable=True),
        sa.Column('requires_corrective_action', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['checklist_templates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_checklist_items_id'), 'checklist_items', ['id'], unique=False)
    op.create_index(op.f('ix_checklist_items_template_id'), 'checklist_items', ['template_id'], unique=False)

    # ========== CHECKLIST SUBMISSIONS ==========
    op.create_table(
        'checklist_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('submission_date', sa.Date(), nullable=False),
        sa.Column('shift_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('in_progress', 'completed', 'pending_signoff', 'signed_off', 'rejected', name='checkliststatus'), nullable=False),
        sa.Column('completed_by', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.ForeignKeyConstraint(['shift_id'], ['shifts.id'], ),
        sa.ForeignKeyConstraint(['template_id'], ['checklist_templates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_checklist_submissions_id'), 'checklist_submissions', ['id'], unique=False)
    op.create_index(op.f('ix_checklist_submissions_template_id'), 'checklist_submissions', ['template_id'], unique=False)
    op.create_index(op.f('ix_checklist_submissions_location_id'), 'checklist_submissions', ['location_id'], unique=False)
    op.create_index(op.f('ix_checklist_submissions_submission_date'), 'checklist_submissions', ['submission_date'], unique=False)
    op.create_index('ix_checklist_submissions_location_date', 'checklist_submissions', ['location_id', 'submission_date'], unique=False)
    op.create_index('ix_checklist_submissions_status', 'checklist_submissions', ['status'], unique=False)

    # ========== CHECKLIST RESPONSES ==========
    op.create_table(
        'checklist_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('response_value', sa.String(500), nullable=True),
        sa.Column('is_passing', sa.Boolean(), nullable=True),
        sa.Column('corrective_action', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('responded_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['checklist_items.id'], ),
        sa.ForeignKeyConstraint(['submission_id'], ['checklist_submissions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_checklist_responses_id'), 'checklist_responses', ['id'], unique=False)
    op.create_index(op.f('ix_checklist_responses_submission_id'), 'checklist_responses', ['submission_id'], unique=False)
    op.create_index(op.f('ix_checklist_responses_item_id'), 'checklist_responses', ['item_id'], unique=False)

    # ========== MANAGER SIGNOFFS ==========
    op.create_table(
        'manager_signoffs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('signed_off_by', sa.Integer(), nullable=False),
        sa.Column('signed_off_at', sa.DateTime(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=False),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['submission_id'], ['checklist_submissions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_manager_signoffs_id'), 'manager_signoffs', ['id'], unique=False)
    op.create_index(op.f('ix_manager_signoffs_submission_id'), 'manager_signoffs', ['submission_id'], unique=False)

    # ========== INSPECTIONS ==========
    op.create_table(
        'inspections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('inspection_type', sa.Enum('health_department', 'internal_audit', 'corporate', 'third_party', 'self_inspection', name='inspectiontype'), nullable=False),
        sa.Column('inspection_date', sa.Date(), nullable=False),
        sa.Column('inspector_name', sa.String(200), nullable=True),
        sa.Column('inspector_agency', sa.String(200), nullable=True),
        sa.Column('score', sa.Numeric(5, 2), nullable=True),
        sa.Column('grade', sa.String(10), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('follow_up_required', sa.Boolean(), nullable=True),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('follow_up_notes', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('report_url', sa.String(500), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspections_id'), 'inspections', ['id'], unique=False)
    op.create_index(op.f('ix_inspections_location_id'), 'inspections', ['location_id'], unique=False)
    op.create_index(op.f('ix_inspections_inspection_date'), 'inspections', ['inspection_date'], unique=False)
    op.create_index('ix_inspections_location_date', 'inspections', ['location_id', 'inspection_date'], unique=False)
    op.create_index('ix_inspections_type', 'inspections', ['inspection_type'], unique=False)

    # ========== INSPECTION VIOLATIONS ==========
    op.create_table(
        'inspection_violations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.Enum('critical', 'major', 'minor', 'observation', name='violationseverity'), nullable=False),
        sa.Column('area', sa.String(100), nullable=True),
        sa.Column('correction_deadline', sa.Date(), nullable=True),
        sa.Column('is_corrected', sa.Boolean(), nullable=True),
        sa.Column('corrected_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['inspection_id'], ['inspections.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspection_violations_id'), 'inspection_violations', ['id'], unique=False)
    op.create_index(op.f('ix_inspection_violations_inspection_id'), 'inspection_violations', ['inspection_id'], unique=False)
    op.create_index('ix_inspection_violations_severity', 'inspection_violations', ['severity'], unique=False)
    op.create_index('ix_inspection_violations_corrected', 'inspection_violations', ['is_corrected'], unique=False)

    # ========== INCIDENTS ==========
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_number', sa.String(20), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('incident_type', sa.Enum('temperature_violation', 'contamination', 'foreign_object', 'pest_sighting', 'equipment_failure', 'employee_illness', 'customer_complaint', 'allergen_issue', 'cross_contamination', 'improper_storage', 'hygiene_violation', 'other', name='incidenttype'), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('incident_date', sa.Date(), nullable=False),
        sa.Column('incident_time', sa.String(10), nullable=True),
        sa.Column('status', sa.Enum('open', 'investigating', 'action_required', 'resolved', 'closed', name='incidentstatus'), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('product_involved', sa.String(200), nullable=True),
        sa.Column('area_involved', sa.String(200), nullable=True),
        sa.Column('reported_by', sa.Integer(), nullable=False),
        sa.Column('reported_at', sa.DateTime(), nullable=True),
        sa.Column('investigated_by', sa.Integer(), nullable=True),
        sa.Column('investigation_notes', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_incidents_id'), 'incidents', ['id'], unique=False)
    op.create_index(op.f('ix_incidents_incident_number'), 'incidents', ['incident_number'], unique=True)
    op.create_index(op.f('ix_incidents_location_id'), 'incidents', ['location_id'], unique=False)
    op.create_index(op.f('ix_incidents_incident_date'), 'incidents', ['incident_date'], unique=False)
    op.create_index('ix_incidents_location_date', 'incidents', ['location_id', 'incident_date'], unique=False)
    op.create_index('ix_incidents_type_status', 'incidents', ['incident_type', 'status'], unique=False)
    op.create_index('ix_incidents_status', 'incidents', ['status'], unique=False)

    # ========== CORRECTIVE ACTIONS ==========
    op.create_table(
        'corrective_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=True),
        sa.Column('inspection_violation_id', sa.Integer(), nullable=True),
        sa.Column('action_description', sa.Text(), nullable=False),
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'in_progress', 'completed', 'verified', name='correctiveactionstatus'), nullable=False),
        sa.Column('completed_by', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
        sa.ForeignKeyConstraint(['inspection_violation_id'], ['inspection_violations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_corrective_actions_id'), 'corrective_actions', ['id'], unique=False)
    op.create_index(op.f('ix_corrective_actions_incident_id'), 'corrective_actions', ['incident_id'], unique=False)
    op.create_index(op.f('ix_corrective_actions_inspection_violation_id'), 'corrective_actions', ['inspection_violation_id'], unique=False)
    op.create_index('ix_corrective_actions_status', 'corrective_actions', ['status'], unique=False)
    op.create_index('ix_corrective_actions_due_date', 'corrective_actions', ['due_date'], unique=False)

    # ========== HACCP PLANS ==========
    op.create_table(
        'haccp_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('review_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_haccp_plans_id'), 'haccp_plans', ['id'], unique=False)
    op.create_index(op.f('ix_haccp_plans_location_id'), 'haccp_plans', ['location_id'], unique=False)
    op.create_index('ix_haccp_plans_location_active', 'haccp_plans', ['location_id', 'is_active'], unique=False)

    # ========== CRITICAL CONTROL POINTS ==========
    op.create_table(
        'critical_control_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('haccp_plan_id', sa.Integer(), nullable=False),
        sa.Column('ccp_number', sa.String(20), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('process_step', sa.String(200), nullable=False),
        sa.Column('hazard_description', sa.Text(), nullable=False),
        sa.Column('critical_limits', sa.Text(), nullable=False),
        sa.Column('min_temp', sa.Numeric(5, 2), nullable=True),
        sa.Column('max_temp', sa.Numeric(5, 2), nullable=True),
        sa.Column('temp_unit', sa.String(1), nullable=True),
        sa.Column('max_time_minutes', sa.Integer(), nullable=True),
        sa.Column('monitoring_procedure', sa.Text(), nullable=False),
        sa.Column('monitoring_frequency', sa.String(100), nullable=False),
        sa.Column('corrective_action_procedure', sa.Text(), nullable=False),
        sa.Column('verification_procedure', sa.Text(), nullable=True),
        sa.Column('records_required', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['haccp_plan_id'], ['haccp_plans.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_critical_control_points_id'), 'critical_control_points', ['id'], unique=False)
    op.create_index(op.f('ix_critical_control_points_haccp_plan_id'), 'critical_control_points', ['haccp_plan_id'], unique=False)

    # ========== SEED DATA: TEMPERATURE THRESHOLDS ==========
    op.execute("""
        INSERT INTO temperature_thresholds (equipment_type, min_temp, max_temp, temp_unit, name, description, alert_on_violation, created_at)
        VALUES
        ('cooler', 33, 40, 'F', 'Walk-in Cooler', 'Standard refrigeration unit (33-40F)', true, NOW()),
        ('freezer', -10, 0, 'F', 'Walk-in Freezer', 'Standard freezer unit (-10 to 0F)', true, NOW()),
        ('reach_in_cooler', 33, 40, 'F', 'Reach-in Cooler', 'Standard reach-in refrigerator (33-40F)', true, NOW()),
        ('reach_in_freezer', -10, 0, 'F', 'Reach-in Freezer', 'Standard reach-in freezer (-10 to 0F)', true, NOW()),
        ('hot_holding', 135, 165, 'F', 'Hot Holding Unit', 'Hot food holding above 135F', true, NOW()),
        ('cold_holding', 33, 40, 'F', 'Cold Holding Unit', 'Cold food holding below 40F', true, NOW()),
        ('prep_cooler', 33, 40, 'F', 'Prep Cooler', 'Prep station refrigeration (33-40F)', true, NOW()),
        ('display_cooler', 33, 40, 'F', 'Display Cooler', 'Display refrigeration (33-40F)', true, NOW())
    """)


def downgrade() -> None:
    op.drop_table('critical_control_points')
    op.drop_table('haccp_plans')
    op.drop_table('corrective_actions')
    op.drop_table('incidents')
    op.drop_table('inspection_violations')
    op.drop_table('inspections')
    op.drop_table('manager_signoffs')
    op.drop_table('checklist_responses')
    op.drop_table('checklist_submissions')
    op.drop_table('checklist_items')
    op.drop_table('checklist_templates')
    op.drop_table('temperature_logs')
    op.drop_table('temperature_thresholds')
    op.drop_table('equipment')
    op.drop_table('shifts')
    op.drop_table('locations')
    op.drop_table('user_permissions')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS correctiveactionstatus')
    op.execute('DROP TYPE IF EXISTS incidentstatus')
    op.execute('DROP TYPE IF EXISTS incidenttype')
    op.execute('DROP TYPE IF EXISTS violationseverity')
    op.execute('DROP TYPE IF EXISTS inspectiontype')
    op.execute('DROP TYPE IF EXISTS checkliststatus')
    op.execute('DROP TYPE IF EXISTS checklisttype')
    op.execute('DROP TYPE IF EXISTS temperaturealertstatus')
    op.execute('DROP TYPE IF EXISTS userrole')
