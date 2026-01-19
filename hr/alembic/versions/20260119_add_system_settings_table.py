"""Add system_settings table

Revision ID: add_system_settings
Revises:
Create Date: 2026-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_system_settings'
down_revision = 'esignature_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('is_encrypted', sa.Boolean(), default=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Insert default timezone setting
    op.execute("""
        INSERT INTO system_settings (category, key, value, description)
        VALUES ('general', 'system_timezone', 'America/New_York', 'System-wide timezone for all services')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('system_settings')
