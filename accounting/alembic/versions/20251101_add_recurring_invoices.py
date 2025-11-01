"""Add recurring invoices

Revision ID: 20251101_0002
Revises: 20251101_0001
Create Date: 2025-11-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251101_0002'
down_revision = '20251101_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add recurring invoice tables"""

    # Create recurring_invoices table
    op.execute("""
        CREATE TABLE recurring_invoices (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

            template_name VARCHAR(200) NOT NULL,
            description TEXT,

            frequency VARCHAR(20) NOT NULL CHECK (frequency IN ('WEEKLY', 'BIWEEKLY', 'MONTHLY', 'QUARTERLY', 'ANNUALLY')),
            start_date TIMESTAMP NOT NULL,
            end_date TIMESTAMP,
            next_invoice_date TIMESTAMP NOT NULL,

            terms_days INTEGER NOT NULL DEFAULT 30,
            invoice_description TEXT,
            notes TEXT,

            subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            discount_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
            discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            tax_rate NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
            tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,

            auto_send_email BOOLEAN DEFAULT TRUE,
            email_to VARCHAR(255),
            email_cc TEXT,

            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED')),

            invoices_generated INTEGER DEFAULT 0,
            last_generated_at TIMESTAMP,

            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create recurring_invoice_line_items table
    op.execute("""
        CREATE TABLE recurring_invoice_line_items (
            id SERIAL PRIMARY KEY,
            recurring_invoice_id INTEGER NOT NULL REFERENCES recurring_invoices(id) ON DELETE CASCADE,

            line_number INTEGER NOT NULL DEFAULT 1,
            description TEXT NOT NULL,
            quantity NUMERIC(10, 2) NOT NULL DEFAULT 1.00,
            unit_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
            amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,

            account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL
        )
    """)

    # Create indexes
    op.execute("""
        CREATE INDEX idx_recurring_invoices_customer ON recurring_invoices(customer_id);
        CREATE INDEX idx_recurring_invoices_status ON recurring_invoices(status);
        CREATE INDEX idx_recurring_invoices_next_date ON recurring_invoices(next_invoice_date);
        CREATE INDEX idx_recurring_invoice_line_items_recurring ON recurring_invoice_line_items(recurring_invoice_id);
    """)

    # Add recurring_invoice_id to customer_invoices table
    op.execute("""
        ALTER TABLE customer_invoices
        ADD COLUMN recurring_invoice_id INTEGER REFERENCES recurring_invoices(id) ON DELETE SET NULL;
    """)

    op.execute("""
        CREATE INDEX idx_customer_invoices_recurring ON customer_invoices(recurring_invoice_id);
    """)


def downgrade() -> None:
    """Remove recurring invoice tables"""
    op.execute("ALTER TABLE customer_invoices DROP COLUMN IF EXISTS recurring_invoice_id CASCADE")
    op.execute("DROP TABLE IF EXISTS recurring_invoice_line_items CASCADE")
    op.execute("DROP TABLE IF EXISTS recurring_invoices CASCADE")
