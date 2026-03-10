"""Recipe library API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from sqlalchemy.orm import Session
from sqlalchemy import or_

from restaurant_cookbook.core.deps import get_db, get_current_user
from restaurant_cookbook.models.recipe import Recipe
from restaurant_cookbook.models.user import User

router = APIRouter()


def _recipe_to_dict(r: Recipe) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "ingredients": r.ingredients,
        "instructions": r.instructions,
        "technique_notes": r.technique_notes,
        "wine_pairing": r.wine_pairing,
        "cuisine_style": r.cuisine_style,
        "cooking_method": r.cooking_method,
        "primary_ingredients": r.primary_ingredients,
        "books_referenced": r.books_referenced,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
def list_recipes(
    search: Optional[str] = QueryParam(None),
    cuisine_style: Optional[str] = QueryParam(None),
    cooking_method: Optional[str] = QueryParam(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all saved recipes with optional filters."""
    query = db.query(Recipe)

    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                Recipe.title.ilike(term),
                Recipe.primary_ingredients.ilike(term),
                Recipe.description.ilike(term),
            )
        )

    if cuisine_style:
        query = query.filter(Recipe.cuisine_style == cuisine_style)
    if cooking_method:
        query = query.filter(Recipe.cooking_method == cooking_method)

    recipes = query.order_by(Recipe.created_at.desc()).all()
    return [_recipe_to_dict(r) for r in recipes]


@router.get("/filters")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available filter options for cuisine styles and cooking methods."""
    styles = (
        db.query(Recipe.cuisine_style)
        .filter(Recipe.cuisine_style.isnot(None), Recipe.cuisine_style != "")
        .distinct()
        .all()
    )
    methods = (
        db.query(Recipe.cooking_method)
        .filter(Recipe.cooking_method.isnot(None), Recipe.cooking_method != "")
        .distinct()
        .all()
    )
    return {
        "cuisine_styles": sorted([s[0] for s in styles]),
        "cooking_methods": sorted([m[0] for m in methods]),
    }


@router.get("/{recipe_id}")
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single recipe by ID."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_to_dict(recipe)


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.delete(recipe)
    db.commit()
    return {"message": f"Recipe '{recipe.title}' deleted"}
