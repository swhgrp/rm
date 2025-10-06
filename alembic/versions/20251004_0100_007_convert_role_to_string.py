"""convert role from enum to string

Revision ID: 007_convert_role_to_string
Revises: 006_add_roles
Create Date: 2025-10-04 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_convert_role_to_string'
down_revision = '006_add_roles'
branch_labels = None
depends_on = None


def upgrade():
    # First convert the column to text (this automatically converts enum to text)
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR USING role::text;")

    # Now update the values to proper role names
    op.execute("""
        UPDATE users
        SET role = CASE
            WHEN role = 'admin' THEN 'Admin'
            WHEN role = 'manager' THEN 'Manager'
            WHEN role = 'staff' THEN 'Staff'
            ELSE role
        END;
    """)

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS userrole;")


def downgrade():
    # Create the enum type
    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'manager', 'staff');")

    # Convert role names back to enum values
    op.execute("""
        UPDATE users
        SET role = CASE
            WHEN role = 'Admin' THEN 'admin'
            WHEN role = 'Manager' THEN 'manager'
            WHEN role = 'Staff' THEN 'staff'
            ELSE 'staff'
        END;
    """)

    # Convert column back to enum
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole;")
