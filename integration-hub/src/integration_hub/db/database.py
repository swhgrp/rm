"""
Database connection and session management for Integration Hub
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=60,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Shared inventory engine (cross-database reads)
INVENTORY_DATABASE_URL = os.getenv("INVENTORY_DATABASE_URL")
_inventory_engine = None


def get_inventory_engine():
    """Get or create the shared inventory database engine."""
    global _inventory_engine
    if _inventory_engine is None:
        inv_url = INVENTORY_DATABASE_URL
        if not inv_url:
            raise ValueError("INVENTORY_DATABASE_URL environment variable is required")
        _inventory_engine = create_engine(
            inv_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=60,
        )
    return _inventory_engine


def get_db():
    """Dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
