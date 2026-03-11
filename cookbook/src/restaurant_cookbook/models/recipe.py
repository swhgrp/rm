from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func

from restaurant_cookbook.db.database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    yield_quantity = Column(String(50), nullable=True)
    yield_unit = Column(String(50), nullable=True)
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    ingredients = Column(Text, nullable=True)
    ingredients_json = Column(JSON, nullable=True)
    instructions = Column(Text, nullable=True)
    technique_notes = Column(Text, nullable=True)
    wine_pairing = Column(Text, nullable=True)
    cuisine_style = Column(String(200), nullable=True, index=True)
    cooking_method = Column(String(200), nullable=True, index=True)
    primary_ingredients = Column(String(500), nullable=True)
    books_referenced = Column(JSON, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
