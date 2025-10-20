"""
Database configuration and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from accounting.core.config import settings

# Create database engine with optimized connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,              # Number of persistent connections
    max_overflow=20,           # Additional connections when pool is full
    pool_timeout=30,           # Timeout for getting connection from pool (seconds)
    pool_recycle=3600,         # Recycle connections after 1 hour (prevent stale connections)
    pool_pre_ping=True,        # Verify connection health before using (prevent errors)
    echo=False                 # Disable SQL logging in production
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
