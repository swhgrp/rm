"""Add email configuration settings for AR invoices

Revision ID: 20251101_0001
Revises: 20251023_1500
Create Date: 2025-11-01 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251101_0001'
down_revision = '20251023_1500'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add email configuration settings"""
    # Insert email settings with default values
    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description, created_at, updated_at)
        VALUES
            ('email_smtp_host', 'localhost', 'string', 'SMTP server hostname', NOW(), NOW()),
            ('email_smtp_port', '587', 'integer', 'SMTP server port (typically 587 for TLS, 465 for SSL)', NOW(), NOW()),
            ('email_smtp_user', '', 'string', 'SMTP username for authentication', NOW(), NOW()),
            ('email_smtp_password', '', 'string', 'SMTP password for authentication (store securely)', NOW(), NOW()),
            ('email_from_address', 'accounting@swrestaurantgroup.com', 'string', 'Email address to send AR invoices from', NOW(), NOW()),
            ('email_from_name', 'SW Hospitality Group - Accounting', 'string', 'Display name for sent emails', NOW(), NOW()),
            ('email_use_tls', 'true', 'boolean', 'Use TLS encryption for SMTP connection', NOW(), NOW())
        ON CONFLICT (setting_key) DO NOTHING;
    """)


def downgrade() -> None:
    """Remove email configuration settings"""
    op.execute("""
        DELETE FROM system_settings
        WHERE setting_key IN (
            'email_smtp_host',
            'email_smtp_port',
            'email_smtp_user',
            'email_smtp_password',
            'email_from_address',
            'email_from_name',
            'email_use_tls'
        );
    """)
