"""add esignature tables

Revision ID: esignature_001
Revises: portal_access_001
Create Date: 2026-01-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'esignature_001'
down_revision = 'portal_access_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create signature_templates table
    op.create_table(
        'signature_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dropbox_template_id', sa.String(100), nullable=True, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('template_file_path', sa.String(500), nullable=True),
        sa.Column('signature_fields', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_signature_templates_id', 'signature_templates', ['id'])

    # Create signature_requests table
    op.create_table(
        'signature_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dropbox_signature_request_id', sa.String(100), nullable=False, unique=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_title', sa.String(255), nullable=False),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('signer_email', sa.String(255), nullable=False),
        sa.Column('signer_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('signed_document_id', sa.Integer(), sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('request_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_signature_requests_id', 'signature_requests', ['id'])
    op.create_index('ix_signature_requests_dropbox_id', 'signature_requests', ['dropbox_signature_request_id'])


def downgrade():
    op.drop_index('ix_signature_requests_dropbox_id')
    op.drop_index('ix_signature_requests_id')
    op.drop_table('signature_requests')
    op.drop_index('ix_signature_templates_id')
    op.drop_table('signature_templates')
