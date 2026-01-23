"""Initial schema for Forms Service

Revision ID: 001_initial
Revises:
Create Date: 2024-01-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types first (before tables)
    formcategory = postgresql.ENUM('hr_employment', 'safety_compliance', 'operations', name='formcategory', create_type=False)
    submissionstatus = postgresql.ENUM('draft', 'submitted', 'pending_signature', 'pending_review', 'approved', 'rejected', 'archived', name='submissionstatus', create_type=False)
    signaturetype = postgresql.ENUM('employee', 'manager', 'witness', 'hr_representative', name='signaturetype', create_type=False)
    signaturemethod = postgresql.ENUM('drawn', 'typed', 'uploaded', name='signaturemethod', create_type=False)
    workflowstatus = postgresql.ENUM('in_progress', 'completed', 'cancelled', name='workflowstatus', create_type=False)
    auditaction = postgresql.ENUM('created', 'viewed', 'edited', 'signed', 'status_changed', 'exported', 'printed', 'workflow_advanced', 'archived', name='auditaction', create_type=False)

    formcategory.create(op.get_bind(), checkfirst=True)
    submissionstatus.create(op.get_bind(), checkfirst=True)
    signaturetype.create(op.get_bind(), checkfirst=True)
    signaturemethod.create(op.get_bind(), checkfirst=True)
    workflowstatus.create(op.get_bind(), checkfirst=True)
    auditaction.create(op.get_bind(), checkfirst=True)

    # Workflows table
    op.create_table(
        'workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('steps', postgresql.JSONB, nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer, nullable=True),
        sa.Column('updated_by', sa.Integer, nullable=True),
    )

    # Form templates table
    op.create_table(
        'form_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('category', postgresql.ENUM('hr_employment', 'safety_compliance', 'operations', name='formcategory', create_type=False), nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('schema', postgresql.JSONB, nullable=False),
        sa.Column('ui_schema', postgresql.JSONB, nullable=True),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('requires_signature', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('requires_manager_signature', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('retention_days', sa.Integer, nullable=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer, nullable=True),
        sa.Column('updated_by', sa.Integer, nullable=True),
    )
    op.create_index('ix_form_templates_active', 'form_templates', ['is_active'], postgresql_where=sa.text('is_active = true'))

    # Form submissions table
    op.create_table(
        'form_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_templates.id'), nullable=False, index=True),
        sa.Column('template_version', sa.Integer, nullable=False),
        sa.Column('location_id', sa.Integer, nullable=False, index=True),
        sa.Column('subject_employee_id', sa.Integer, nullable=True, index=True),
        sa.Column('submitted_by_employee_id', sa.Integer, nullable=False, index=True),
        sa.Column('data', postgresql.JSONB, nullable=False),
        sa.Column('status', postgresql.ENUM('draft', 'submitted', 'pending_signature', 'pending_review', 'approved', 'rejected', 'archived', name='submissionstatus', create_type=False), nullable=False, server_default='draft', index=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reference_number', sa.String(50), nullable=True, unique=True, index=True),
        sa.Column('related_submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id'), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer, nullable=True),
        sa.Column('updated_by', sa.Integer, nullable=True),
    )
    op.create_index('ix_form_submissions_created_desc', 'form_submissions', [sa.text('created_at DESC')])

    # Signatures table
    op.create_table(
        'signatures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('employee_id', sa.Integer, nullable=False, index=True),
        sa.Column('signature_type', postgresql.ENUM('employee', 'manager', 'witness', 'hr_representative', name='signaturetype', create_type=False), nullable=False),
        sa.Column('signature_data', sa.Text, nullable=False),
        sa.Column('signature_method', postgresql.ENUM('drawn', 'typed', 'uploaded', name='signaturemethod', create_type=False), nullable=False),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Signature requests table
    op.create_table(
        'signature_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('requested_employee_id', sa.Integer, nullable=False, index=True),
        sa.Column('signature_type', postgresql.ENUM('employee', 'manager', 'witness', 'hr_representative', name='signaturetype', create_type=False), nullable=False),
        sa.Column('is_fulfilled', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('token', sa.String(255), nullable=True, unique=True, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer, nullable=True),
    )

    # Workflow instances table
    op.create_table(
        'workflow_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id'), nullable=False),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('current_step', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('in_progress', 'completed', 'cancelled', name='workflowstatus', create_type=False), nullable=False, server_default='in_progress', index=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Workflow step history table
    op.create_table(
        'workflow_step_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workflow_instance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflow_instances.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('step_number', sa.Integer, nullable=False),
        sa.Column('assigned_to_employee_id', sa.Integer, nullable=False),
        sa.Column('action_taken', sa.String(50), nullable=True),
        sa.Column('comments', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Attachments table
    op.create_table(
        'attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('file_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(100), nullable=False),
        sa.Column('file_size', sa.BigInteger, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer, nullable=True),
    )

    # Audit log table
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_submissions.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('form_templates.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('employee_id', sa.Integer, nullable=True, index=True),
        sa.Column('action', postgresql.ENUM('created', 'viewed', 'edited', 'signed', 'status_changed', 'exported', 'printed', 'workflow_advanced', 'archived', name='auditaction', create_type=False), nullable=False, index=True),
        sa.Column('details', postgresql.JSONB, nullable=True),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('performed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_log_performed_desc', 'audit_log', [sa.text('performed_at DESC')])

    # Notification preferences table
    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('employee_id', sa.Integer, nullable=False, unique=True),
        sa.Column('email_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('digest_mode', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('notify_on_submission', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('notify_on_signature_request', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('notify_on_workflow_complete', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('notify_on_escalation', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_index('ix_audit_log_performed_desc', 'audit_log')
    op.drop_table('audit_log')
    op.drop_table('attachments')
    op.drop_table('workflow_step_history')
    op.drop_table('workflow_instances')
    op.drop_table('signature_requests')
    op.drop_table('signatures')
    op.drop_index('ix_form_submissions_created_desc', 'form_submissions')
    op.drop_table('form_submissions')
    op.drop_index('ix_form_templates_active', 'form_templates')
    op.drop_table('form_templates')
    op.drop_table('workflows')

    op.execute('DROP TYPE IF EXISTS auditaction')
    op.execute('DROP TYPE IF EXISTS workflowstatus')
    op.execute('DROP TYPE IF EXISTS signaturemethod')
    op.execute('DROP TYPE IF EXISTS signaturetype')
    op.execute('DROP TYPE IF EXISTS submissionstatus')
    op.execute('DROP TYPE IF EXISTS formcategory')
