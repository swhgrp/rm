"""Add payment reminder settings

Revision ID: 20251101_0003
Revises: 20251101_0002
Create Date: 2025-11-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251101_0003'
down_revision = '20251101_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add payment reminder settings to system_settings"""

    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description, created_at, updated_at)
        VALUES
            ('reminder_enabled', 'true', 'boolean', 'Enable automated payment reminders', NOW(), NOW()),
            ('reminder_days_1', '7', 'integer', 'First reminder: days after due date', NOW(), NOW()),
            ('reminder_days_2', '14', 'integer', 'Second reminder: days after due date', NOW(), NOW()),
            ('reminder_days_3', '30', 'integer', 'Final reminder: days after due date', NOW(), NOW()),
            ('reminder_email_from', '', 'string', 'Email address for reminder emails (leave empty to use default AR email)', NOW(), NOW()),
            ('reminder_subject_template', 'Payment Reminder: Invoice {invoice_number}', 'string', 'Subject template for reminder emails', NOW(), NOW()),
            ('reminder_min_amount', '0.00', 'decimal', 'Minimum invoice amount to send reminders (0 = all invoices)', NOW(), NOW())
        ON CONFLICT (setting_key) DO NOTHING
    """)

    # Create payment_reminders table to track reminder history
    op.execute("""
        CREATE TABLE payment_reminders (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES customer_invoices(id) ON DELETE CASCADE,
            reminder_number INTEGER NOT NULL CHECK (reminder_number IN (1, 2, 3)),
            sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_to VARCHAR(255) NOT NULL,
            days_overdue INTEGER NOT NULL,
            amount_due NUMERIC(10, 2) NOT NULL,
            email_subject TEXT,
            email_body TEXT,
            email_status VARCHAR(20) DEFAULT 'sent' CHECK (email_status IN ('sent', 'failed', 'bounced')),
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    op.execute("""
        CREATE INDEX idx_payment_reminders_invoice ON payment_reminders(invoice_id);
        CREATE INDEX idx_payment_reminders_sent_at ON payment_reminders(sent_at);
    """)


def downgrade() -> None:
    """Remove payment reminder settings and table"""
    op.execute("DROP TABLE IF EXISTS payment_reminders CASCADE")
    op.execute("""
        DELETE FROM system_settings
        WHERE setting_key IN (
            'reminder_enabled',
            'reminder_days_1',
            'reminder_days_2',
            'reminder_days_3',
            'reminder_email_from',
            'reminder_subject_template',
            'reminder_min_amount'
        )
    """)
