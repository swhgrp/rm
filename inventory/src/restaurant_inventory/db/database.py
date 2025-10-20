"""
Database configuration and connection management
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from restaurant_inventory.core.config import settings

# Create SQLAlchemy engine with optimized connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,              # Number of persistent connections (default: 5)
    max_overflow=20,           # Additional connections when pool is full (default: 10)
    pool_timeout=30,           # Timeout for getting connection from pool (seconds)
    pool_recycle=3600,         # Recycle connections after 1 hour (prevent stale connections)
    pool_pre_ping=True,        # Verify connection health before using (prevent errors)
    echo=False                 # Disable SQL logging in production
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
