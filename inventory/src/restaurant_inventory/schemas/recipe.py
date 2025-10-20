"""
Recipe schemas for request/response models
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


class RecipeIngredientBase(BaseModel):
    master_item_id: int
    quantity: Decimal
    unit: str
    notes: Optional[str] = None


class RecipeIngredientCreate(RecipeIngredientBase):
    pass


class RecipeIngredientUpdate(BaseModel):
    master_item_id: Optional[int] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class RecipeIngredientResponse(RecipeIngredientBase):
    id: int
    recipe_id: int
    unit_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    master_item_name: Optional[str] = None

    class Config:
        from_attributes = True


class RecipeBase(BaseModel):
    name: str
    category: str
    description: Optional[str] = None
    yield_quantity: Decimal
    yield_unit: str
    portion_size: Optional[Decimal] = None
    portion_unit: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    instructions: Optional[str] = None
    notes: Optional[str] = None
    image_url: Optional[str] = None
    selling_price: Optional[Decimal] = None
    is_active: bool = True


class RecipeCreate(RecipeBase):
    ingredients: List[RecipeIngredientCreate] = []


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    yield_quantity: Optional[Decimal] = None
    yield_unit: Optional[str] = None
    portion_size: Optional[Decimal] = None
    portion_unit: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    instructions: Optional[str] = None
    notes: Optional[str] = None
    image_url: Optional[str] = None
    selling_price: Optional[Decimal] = None
    is_active: Optional[bool] = None


class RecipeResponse(RecipeBase):
    id: int
    ingredient_cost: Optional[Decimal] = None
    labor_cost: Optional[Decimal] = None
    overhead_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    cost_per_portion: Optional[Decimal] = None
    food_cost_percentage: Optional[Decimal] = None
    last_costed: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ingredients: List[RecipeIngredientResponse] = []

    class Config:
        from_attributes = True


class RecipeCostCalculation(BaseModel):
    recipe_id: int
    recipe_name: str
    ingredient_cost: Decimal
    labor_cost: Decimal
    overhead_cost: Decimal
    total_cost: Decimal
    cost_per_portion: Optional[Decimal] = None
    portions: Optional[int] = None
    ingredient_breakdown: List[dict] = []
