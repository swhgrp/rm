"""User model - mirrors HR database"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from files.db.database import Base


class User(Base):
    """User model from HR database"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    can_access_nextcloud = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
