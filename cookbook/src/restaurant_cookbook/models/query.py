from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func

from restaurant_cookbook.db.database import Base


class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    query_text = Column(Text, nullable=False)
    mode = Column(String(50), nullable=False)  # lookup, create
    books_referenced = Column(JSON, nullable=True)
    response_text = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
