"""self-hosted esignature columns

Revision ID: self_hosted_esig_001
Revises: hr_forms_permissions_001
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'self_hosted_esig_001'
down_revision = 'hr_permissions_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add self-hosted signing columns to signature_requests
    op.add_column('signature_requests', sa.Column('signing_token', sa.String(128), nullable=True, unique=True))
    op.add_column('signature_requests', sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('signature_requests', sa.Column('signer_ip', sa.String(45), nullable=True))
    op.add_column('signature_requests', sa.Column('signer_user_agent', sa.Text(), nullable=True))
    op.add_column('signature_requests', sa.Column('document_hash', sa.String(64), nullable=True))
    op.add_column('signature_requests', sa.Column('signed_document_hash', sa.String(64), nullable=True))
    op.add_column('signature_requests', sa.Column('template_id', sa.Integer(), sa.ForeignKey('signature_templates.id', ondelete='SET NULL'), nullable=True))
    op.add_column('signature_requests', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('signature_requests', sa.Column('cancelled_by', sa.Integer(), nullable=True))
    op.add_column('signature_requests', sa.Column('original_file_path', sa.String(500), nullable=True))
    op.add_column('signature_requests', sa.Column('signing_data', sa.JSON(), nullable=True))

    # Create index on signing_token for fast lookup
    op.create_index('ix_signature_requests_signing_token', 'signature_requests', ['signing_token'])

    # Make dropbox_signature_request_id nullable (no longer required)
    op.alter_column('signature_requests', 'dropbox_signature_request_id', nullable=True)


def downgrade():
    op.drop_index('ix_signature_requests_signing_token')
    op.drop_column('signature_requests', 'signing_data')
    op.drop_column('signature_requests', 'original_file_path')
    op.drop_column('signature_requests', 'cancelled_by')
    op.drop_column('signature_requests', 'cancelled_at')
    op.drop_column('signature_requests', 'template_id')
    op.drop_column('signature_requests', 'signed_document_hash')
    op.drop_column('signature_requests', 'document_hash')
    op.drop_column('signature_requests', 'signer_user_agent')
    op.drop_column('signature_requests', 'signer_ip')
    op.drop_column('signature_requests', 'token_expires_at')
    op.drop_column('signature_requests', 'signing_token')
    op.alter_column('signature_requests', 'dropbox_signature_request_id', nullable=False)
