from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add the src directory to Python path
sys.path.insert(0, '/app/src')

# Import the database base and models
from accounting.db.database import Base
from accounting.models.account import Account
from accounting.models.journal_entry import JournalEntry, JournalEntryLine
from accounting.models.fiscal_period import FiscalPeriod
from accounting.models.account_balance import AccountBalance
from accounting.models.sync_log import InventorySyncLog
from accounting.models.cogs import COGSTransaction
from accounting.gl_review.models import GLAnomalyFlag, GLAccountBaseline

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get database URL from environment
database_url = os.getenv("DATABASE_URL", "postgresql://accounting_user:Acc0unt1ng_Pr0d_2024!@accounting-db:5432/accounting_db")
config.set_main_option("sqlalchemy.url", database_url)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
