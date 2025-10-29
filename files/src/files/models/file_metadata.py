"""File and folder metadata models"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, BigInteger, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from files.db.database import Base


# Association table for folder permissions (many-to-many)
folder_permissions = Table(
    'folder_permissions',
    Base.metadata,
    Column('folder_id', Integer, ForeignKey('folders.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('can_read', Boolean, default=True),
    Column('can_write', Boolean, default=False),
    Column('can_delete', Boolean, default=False),
    Column('granted_at', DateTime(timezone=True), server_default=func.now())
)


class Folder(Base):
    """Folder metadata model"""
    __tablename__ = "folders"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True, index=True)
    parent_id = Column(Integer, ForeignKey('folders.id', ondelete='CASCADE'), nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    parent = relationship("Folder", remote_side=[id], backref="subfolders")
    owner = relationship("User", backref="owned_folders")
    permitted_users = relationship("User", secondary=folder_permissions, backref="accessible_folders")


class FileMetadata(Base):
    """File metadata model"""
    __tablename__ = "file_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True, index=True)
    folder_id = Column(Integer, ForeignKey('folders.id', ondelete='CASCADE'), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    size = Column(BigInteger, default=0)
    mime_type = Column(String, nullable=True)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    folder = relationship("Folder", backref="files")
    owner = relationship("User", backref="owned_files")
