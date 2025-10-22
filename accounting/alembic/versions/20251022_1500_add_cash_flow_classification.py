"""Add cash flow classification to accounts

Revision ID: 20251022_1500
Revises: 20251022_0300
Create Date: 2025-10-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251022_1500'
down_revision = '20251022_0300'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for cash flow classification
    cash_flow_class_enum = postgresql.ENUM(
        'OPERATING', 'INVESTING', 'FINANCING', 'NON_CASH', 'NONE',
        name='cashflowclass',
        create_type=True
    )
    cash_flow_class_enum.create(op.get_bind(), checkfirst=True)

    # Add cash_flow_class column to accounts table
    op.add_column('accounts', sa.Column(
        'cash_flow_class',
        sa.Enum('OPERATING', 'INVESTING', 'FINANCING', 'NON_CASH', 'NONE', name='cashflowclass'),
        nullable=True,
        comment='Cash flow statement classification for this account'
    ))

    # Set default classifications based on account type and number
    # This will help with automatic cash flow statement generation

    # Assets - mostly non-cash or investing
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'NONE'
        WHERE account_type = 'ASSET'
        AND account_number LIKE '1000%';  -- Cash accounts are handled separately
    """)

    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'OPERATING'
        WHERE account_type = 'ASSET'
        AND (account_number LIKE '1100%' OR account_number LIKE '1200%');  -- AR, Inventory
    """)

    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'INVESTING'
        WHERE account_type = 'ASSET'
        AND account_number LIKE '1500%';  -- Fixed assets
    """)

    # Liabilities - operating or financing
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'OPERATING'
        WHERE account_type = 'LIABILITY'
        AND (account_number LIKE '2000%' OR account_number LIKE '2100%');  -- AP, Accrued
    """)

    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'FINANCING'
        WHERE account_type = 'LIABILITY'
        AND (account_number LIKE '2500%' OR account_number LIKE '2600%');  -- Loans, Notes
    """)

    # Equity - financing
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'FINANCING'
        WHERE account_type = 'EQUITY';
    """)

    # Revenue - operating
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'OPERATING'
        WHERE account_type = 'REVENUE';
    """)

    # COGS - operating
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'OPERATING'
        WHERE account_type = 'COGS';
    """)

    # Expenses - operating
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'OPERATING'
        WHERE account_type = 'EXPENSE';
    """)

    # Mark depreciation and amortization as non-cash
    op.execute("""
        UPDATE accounts
        SET cash_flow_class = 'NON_CASH'
        WHERE account_name ILIKE '%depreciation%'
        OR account_name ILIKE '%amortization%';
    """)


def downgrade() -> None:
    # Drop the column
    op.drop_column('accounts', 'cash_flow_class')

    # Drop the enum type
    cash_flow_class_enum = postgresql.ENUM(
        'OPERATING', 'INVESTING', 'FINANCING', 'NON_CASH', 'NONE',
        name='cashflowclass'
    )
    cash_flow_class_enum.drop(op.get_bind(), checkfirst=True)
