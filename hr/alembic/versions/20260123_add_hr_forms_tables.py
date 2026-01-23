"""Add HR Forms tables (Corrective Action and First Report of Injury)

Revision ID: hr_forms_001
Revises: add_system_settings
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = 'hr_forms_001'
down_revision = 'add_system_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Create corrective_actions table
    op.create_table(
        'corrective_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_number', sa.String(20), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),

        # Disciplinary level
        sa.Column('disciplinary_level', sa.String(20), nullable=False),
        sa.Column('final_warning_type', sa.String(50), nullable=True),

        # Subject
        sa.Column('subject', sa.String(30), nullable=False),

        # Prior notifications (JSON)
        sa.Column('prior_notifications', JSON, nullable=True),

        # Incident details
        sa.Column('incident_description', sa.Text(), nullable=False),
        sa.Column('incident_date', sa.Date(), nullable=False),
        sa.Column('incident_time', sa.String(10), nullable=True),
        sa.Column('incident_location', sa.String(200), nullable=True),
        sa.Column('persons_present', sa.Text(), nullable=True),
        sa.Column('organizational_impact', sa.Text(), nullable=True),

        # Performance Improvement Plan
        sa.Column('improvement_goals', sa.Text(), nullable=True),
        sa.Column('training_provided', sa.Text(), nullable=True),
        sa.Column('interim_evaluation_needed', sa.Boolean(), default=False),
        sa.Column('personal_improvement_input', sa.Text(), nullable=True),

        # Outcomes
        sa.Column('positive_outcome', sa.Text(), nullable=True),
        sa.Column('negative_outcome', sa.Text(), nullable=True),

        # Review
        sa.Column('scheduled_review_date', sa.Date(), nullable=True),

        # Employee comments
        sa.Column('employee_comments', sa.Text(), nullable=True),

        # Status
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),

        # Employee signature
        sa.Column('employee_signature', sa.Text(), nullable=True),
        sa.Column('employee_signature_date', sa.DateTime(), nullable=True),
        sa.Column('employee_typed_name', sa.String(200), nullable=True),
        sa.Column('employee_signature_ip', sa.String(50), nullable=True),
        sa.Column('employee_signature_user_agent', sa.String(500), nullable=True),

        # Supervisor signature
        sa.Column('supervisor_signature', sa.Text(), nullable=True),
        sa.Column('supervisor_signature_date', sa.DateTime(), nullable=True),
        sa.Column('supervisor_typed_name', sa.String(200), nullable=True),
        sa.Column('supervisor_signature_ip', sa.String(50), nullable=True),
        sa.Column('supervisor_signature_user_agent', sa.String(500), nullable=True),

        # Witness (if employee refuses)
        sa.Column('witness_name', sa.String(200), nullable=True),
        sa.Column('witness_signature', sa.Text(), nullable=True),
        sa.Column('witness_date', sa.DateTime(), nullable=True),
        sa.Column('witness_conference_time', sa.String(50), nullable=True),
        sa.Column('witness_typed_name', sa.String(200), nullable=True),
        sa.Column('witness_signature_ip', sa.String(50), nullable=True),

        # Supervisor and creator
        sa.Column('supervisor_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),

        # Audit
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),

        # Document reference
        sa.Column('document_id', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supervisor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
    )

    op.create_index('ix_corrective_actions_id', 'corrective_actions', ['id'])
    op.create_index('ix_corrective_actions_reference', 'corrective_actions', ['reference_number'], unique=True)
    op.create_index('ix_corrective_actions_employee', 'corrective_actions', ['employee_id'])
    op.create_index('ix_corrective_actions_status', 'corrective_actions', ['status'])
    op.create_index('ix_corrective_actions_date', 'corrective_actions', ['incident_date'])

    # Create first_report_of_injury table
    op.create_table(
        'first_report_of_injury',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_number', sa.String(20), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),

        # Accident details
        sa.Column('accident_date', sa.Date(), nullable=False),
        sa.Column('accident_time', sa.String(10), nullable=True),
        sa.Column('accident_am_pm', sa.String(2), nullable=True),
        sa.Column('accident_description', sa.Text(), nullable=False),

        # Injury details
        sa.Column('injury_type', sa.String(30), nullable=False),
        sa.Column('injury_description', sa.String(500), nullable=True),
        sa.Column('body_part', sa.String(30), nullable=False),
        sa.Column('body_part_detail', sa.String(200), nullable=True),

        # Location
        sa.Column('location_id', sa.Integer(), nullable=False),

        # Accident location
        sa.Column('accident_street', sa.String(200), nullable=True),
        sa.Column('accident_city', sa.String(100), nullable=True),
        sa.Column('accident_state', sa.String(50), nullable=True),
        sa.Column('accident_zip', sa.String(20), nullable=True),
        sa.Column('accident_county', sa.String(100), nullable=True),

        # Employment details
        sa.Column('date_employed', sa.Date(), nullable=True),
        sa.Column('paid_for_injury_date', sa.Boolean(), default=False),
        sa.Column('last_date_worked', sa.Date(), nullable=True),
        sa.Column('returned_to_work', sa.Boolean(), default=False),
        sa.Column('return_to_work_date', sa.Date(), nullable=True),

        # Pay rate
        sa.Column('rate_of_pay', sa.String(20), nullable=True),
        sa.Column('pay_period', sa.String(10), nullable=True),
        sa.Column('hours_per_day', sa.String(10), nullable=True),
        sa.Column('hours_per_week', sa.String(10), nullable=True),
        sa.Column('days_per_week', sa.String(10), nullable=True),

        # Medical
        sa.Column('physician_name', sa.String(200), nullable=True),
        sa.Column('physician_address', sa.Text(), nullable=True),
        sa.Column('physician_phone', sa.String(50), nullable=True),
        sa.Column('hospital_name', sa.String(200), nullable=True),
        sa.Column('treatment_authorized_by_employer', sa.Boolean(), default=True),

        # Employer agreement
        sa.Column('employer_agrees_with_description', sa.Boolean(), default=True),
        sa.Column('employer_disagreement_notes', sa.Text(), nullable=True),

        # Wages
        sa.Column('will_continue_wages', sa.Boolean(), default=False),
        sa.Column('last_day_wages_paid', sa.Date(), nullable=True),

        # Death
        sa.Column('date_of_death', sa.Date(), nullable=True),

        # Status
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),

        # Employee signature
        sa.Column('employee_signature', sa.Text(), nullable=True),
        sa.Column('employee_signature_date', sa.DateTime(), nullable=True),
        sa.Column('employee_typed_name', sa.String(200), nullable=True),
        sa.Column('employee_signature_ip', sa.String(50), nullable=True),
        sa.Column('employee_signature_user_agent', sa.String(500), nullable=True),

        # Employer signature
        sa.Column('employer_signature', sa.Text(), nullable=True),
        sa.Column('employer_signature_date', sa.DateTime(), nullable=True),
        sa.Column('employer_typed_name', sa.String(200), nullable=True),
        sa.Column('employer_signature_ip', sa.String(50), nullable=True),
        sa.Column('employer_signature_user_agent', sa.String(500), nullable=True),
        sa.Column('employer_signer_id', sa.Integer(), nullable=True),

        # Reporting
        sa.Column('date_first_reported', sa.Date(), nullable=True),

        # Audit
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('created_by', sa.Integer(), nullable=False),

        # Document reference
        sa.Column('document_id', sa.Integer(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employer_signer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
    )

    op.create_index('ix_first_report_injury_id', 'first_report_of_injury', ['id'])
    op.create_index('ix_first_report_injury_reference', 'first_report_of_injury', ['reference_number'], unique=True)
    op.create_index('ix_first_report_injury_employee', 'first_report_of_injury', ['employee_id'])
    op.create_index('ix_first_report_injury_status', 'first_report_of_injury', ['status'])
    op.create_index('ix_first_report_injury_date', 'first_report_of_injury', ['accident_date'])


def downgrade():
    op.drop_table('first_report_of_injury')
    op.drop_table('corrective_actions')
