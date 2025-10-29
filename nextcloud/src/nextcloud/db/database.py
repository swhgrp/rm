"""
Database configuration and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

from nextcloud.core.config import settings

# Create database engine with optimized connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,              # Persistent connections
    max_overflow=20,           # Additional when pool full
    pool_timeout=30,           # Timeout for getting connection
    pool_recycle=3600,         # Recycle connections after 1 hour
    pool_pre_ping=True,        # Verify connection before use (prevent stale connections)
    echo=False                 # No SQL logging in production
)

# HR database engine for user authentication
hr_engine = create_engine(
    settings.HR_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
HRSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=hr_engine)
Base = declarative_base()


def get_db():
    """
    Dependency: Get database session

    Yields:
        Database session (automatically closed after use)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
