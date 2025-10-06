"""
Recipe models for menu item costing and ingredient tracking
"""

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from restaurant_inventory.db.database import Base


class RecipeCategory(str, enum.Enum):
    """Recipe category types"""
    APPETIZER = "appetizer"
    ENTREE = "entree"
    SIDE = "side"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    SAUCE = "sauce"
    PREP = "prep"
    OTHER = "other"


class Recipe(Base):
    """Recipe master table"""
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Use String instead of Enum - Postgres handles the enum constraint at DB level
    category = Column(String(50), nullable=False, default="other")

    # Yield and portioning
    yield_quantity = Column(Numeric(10, 3), nullable=False)  # How many portions this makes
    yield_unit = Column(String(50), nullable=False)  # "servings", "portions", "lbs", "gallons", etc.
    portion_size = Column(Numeric(10, 3), nullable=True)  # Size of one serving
    portion_unit = Column(String(50), nullable=True)  # "oz", "cups", "each", etc.

    # Instructions
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    instructions = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Equipment and storage
    equipment_needed = Column(Text, nullable=True)  # "Oven, mixer, 12-qt pot"
    storage_container = Column(String(100), nullable=True)  # "Cambro 12qt", "Hotel pan full"
    shelf_life_days = Column(Integer, nullable=True)  # How long it keeps
    image_url = Column(String(500), nullable=True)  # Path to uploaded recipe image

    # Costing (calculated fields)
    ingredient_cost = Column(Numeric(10, 4), nullable=True)  # Total cost of all ingredients
    labor_cost = Column(Numeric(10, 4), nullable=True)  # Estimated labor cost
    overhead_cost = Column(Numeric(10, 4), nullable=True)  # Overhead cost
    total_cost = Column(Numeric(10, 4), nullable=True)  # Total recipe cost
    cost_per_portion = Column(Numeric(10, 4), nullable=True)  # Cost per single serving
    selling_price = Column(Numeric(10, 2), nullable=True)  # Menu price (what we sell it for)
    food_cost_percentage = Column(Numeric(5, 2), nullable=True)  # (cost_per_portion / selling_price) * 100
    last_costed = Column(DateTime(timezone=True), nullable=True)  # When cost was last calculated

    # Labor estimate (deprecated - using labor_cost above)
    labor_minutes = Column(Integer, nullable=True)  # Total labor time

    # Metadata
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # Optional: location-specific recipe
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)  # If false, only visible to creating location
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")
    created_by = relationship("User", foreign_keys=[created_by_id])
    location = relationship("Location", foreign_keys=[location_id])

    def __repr__(self):
        return f"<Recipe(id={self.id}, name='{self.name}', category={self.category})>"


class RecipeIngredient(Base):
    """Ingredients that make up a recipe"""
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    master_item_id = Column(Integer, ForeignKey("master_items.id"), nullable=False)

    # Quantity needed
    quantity = Column(Numeric(10, 4), nullable=False)  # How much of this ingredient
    unit = Column(String(50), nullable=False)  # "lbs", "oz", "each", "cups", etc.

    # Costing
    unit_cost = Column(Numeric(10, 4), nullable=True)  # Cost per unit at time of calculation
    total_cost = Column(Numeric(10, 4), nullable=True)  # quantity * unit_cost
    cost_percentage = Column(Numeric(5, 2), nullable=True)  # What % of recipe cost is this ingredient

    # Preparation notes
    preparation = Column(String(200), nullable=True)  # "diced", "chopped fine", "melted", etc.
    notes = Column(Text, nullable=True)

    # Ordering in recipe
    sort_order = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    recipe = relationship("Recipe", back_populates="ingredients")
    master_item = relationship("MasterItem")

    def __repr__(self):
        return f"<RecipeIngredient(recipe_id={self.recipe_id}, item_id={self.master_item_id}, qty={self.quantity})>"
