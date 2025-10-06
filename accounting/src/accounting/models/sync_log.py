"""
Inventory Sync Log model
"""
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.sql import func
from accounting.db.database import Base
import enum


class SyncStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class InventorySyncLog(Base):
    __tablename__ = "inventory_sync_log"

    id = Column(Integer, primary_key=True, index=True)
    sync_type = Column(String(50), nullable=False, index=True)  # 'INVOICE', 'TRANSFER', 'WASTE', 'COUNT'
    inventory_reference_id = Column(Integer, nullable=False, index=True)
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=True)

    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(SyncStatus), default=SyncStatus.PENDING, nullable=False)
    error_message = Column(Text, nullable=True)
