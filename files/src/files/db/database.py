"""Database configuration"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from files.core.config import settings

# HR database engine for user authentication and file metadata
engine = create_engine(
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
Base = declarative_base()

# Alias for backward compatibility
hr_engine = engine
HRSessionLocal = SessionLocal


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_hr_db():
    """Get HR database session (alias for get_db)"""
    return get_db()
