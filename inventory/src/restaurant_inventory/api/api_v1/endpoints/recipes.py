"""
Recipe CRUD endpoints with costing
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from decimal import Decimal
import os
import uuid
from pathlib import Path

from restaurant_inventory.core.deps import get_db, get_current_user, require_manager_or_admin
from restaurant_inventory.models.recipe import Recipe, RecipeIngredient
from restaurant_inventory.models.item import MasterItem
from restaurant_inventory.models.user import User
from restaurant_inventory.schemas.recipe import (
    RecipeCreate, RecipeUpdate, RecipeResponse,
    RecipeIngredientCreate, RecipeIngredientUpdate, RecipeIngredientResponse,
    RecipeCostCalculation
)
from restaurant_inventory.core.audit import log_audit_event, create_change_dict
from restaurant_inventory.core.recipe_pdf import RecipePDFGenerator

router = APIRouter()


@router.get("/", response_model=List[RecipeResponse])
async def get_recipes(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in name or description"),
    active_only: bool = Query(True, description="Show only active recipes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all recipes with filtering"""
    query = db.query(Recipe)

    if active_only:
        query = query.filter(Recipe.is_active == True)

    if category:
        query = query.filter(Recipe.category == category)

    if search:
        query = query.filter(
            (Recipe.name.ilike(f"%{search}%")) |
            (Recipe.description.ilike(f"%{search}%"))
        )

    recipes = query.offset(skip).limit(limit).all()

    # Load ingredients for each recipe
    result = []
    for recipe in recipes:
        recipe_data = RecipeResponse.from_orm(recipe)

        # Get ingredients with master item names
        ingredients = db.query(RecipeIngredient).filter(
            RecipeIngredient.recipe_id == recipe.id
        ).all()

        ingredient_list = []
        for ing in ingredients:
            master_item = db.query(MasterItem).filter(MasterItem.id == ing.master_item_id).first()
            ing_data = RecipeIngredientResponse.from_orm(ing)
            if master_item:
                ing_data.master_item_name = master_item.name
            ingredient_list.append(ing_data)

        recipe_data.ingredients = ingredient_list
        result.append(recipe_data)

    return result


@router.get("/categories")
async def get_recipe_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique recipe categories"""
    categories = db.query(Recipe.category).distinct().all()
    return [cat[0] for cat in categories]


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single recipe by ID"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    recipe_data = RecipeResponse.from_orm(recipe)

    # Get ingredients with master item names
    ingredients = db.query(RecipeIngredient).filter(
        RecipeIngredient.recipe_id == recipe.id
    ).all()

    ingredient_list = []
    for ing in ingredients:
        master_item = db.query(MasterItem).filter(MasterItem.id == ing.master_item_id).first()
        ing_data = RecipeIngredientResponse.from_orm(ing)
        if master_item:
            ing_data.master_item_name = master_item.name
        ingredient_list.append(ing_data)

    recipe_data.ingredients = ingredient_list

    return recipe_data


@router.post("/", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    recipe: RecipeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Create a new recipe"""

    # Create recipe - build manually to avoid enum issues
    db_recipe = Recipe(
        name=recipe.name,
        description=recipe.description,
        category=recipe.category.lower(),  # Pass as lowercase string
        yield_quantity=recipe.yield_quantity,
        yield_unit=recipe.yield_unit,
        portion_size=recipe.portion_size,
        portion_unit=recipe.portion_unit,
        prep_time_minutes=recipe.prep_time_minutes,
        cook_time_minutes=recipe.cook_time_minutes,
        instructions=recipe.instructions,
        notes=recipe.notes,
        created_by_id=current_user.id,
        is_active=recipe.is_active
    )
    db.add(db_recipe)
    db.flush()  # Get the recipe ID

    # Add ingredients
    for ingredient in recipe.ingredients:
        db_ingredient = RecipeIngredient(
            recipe_id=db_recipe.id,
            **ingredient.dict()
        )
        db.add(db_ingredient)

    db.commit()
    db.refresh(db_recipe)

    # Calculate costs
    calculate_recipe_cost(db_recipe.id, db)

    log_audit_event(
        db=db,
        user=current_user,
        action="recipe_create",
        entity_type="recipe",
        entity_id=db_recipe.id,
        changes={"name": db_recipe.name}
    )

    return await get_recipe(db_recipe.id, db, current_user)


@router.put("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: int,
    recipe_update: RecipeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a recipe"""
    db_recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not db_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Track changes for audit
    changes = {}
    update_data = recipe_update.dict(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(db_recipe, field):
            old_value = getattr(db_recipe, field)
            if old_value != value:
                changes[field] = {"old": str(old_value), "new": str(value)}
                setattr(db_recipe, field, value)

    if changes:
        db.commit()
        db.refresh(db_recipe)

        # Recalculate costs
        calculate_recipe_cost(recipe_id, db)

        log_audit_event(
            db=db,
            user=current_user,
            action="recipe_update",
            entity_type="recipe",
            entity_id=recipe_id,
            changes=changes
        )

    return await get_recipe(recipe_id, db, current_user)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Delete a recipe (soft delete by setting is_active=False)"""
    db_recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not db_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    db_recipe.is_active = False
    db.commit()

    log_audit_event(
        db=db,
        user=current_user,
        action="recipe_delete",
        entity_type="recipe",
        entity_id=recipe_id,
        changes={"is_active": {"old": True, "new": False}}
    )

    return None


# Recipe Ingredient endpoints

@router.post("/{recipe_id}/ingredients", response_model=RecipeIngredientResponse, status_code=status.HTTP_201_CREATED)
async def add_ingredient(
    recipe_id: int,
    ingredient: RecipeIngredientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Add an ingredient to a recipe"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Verify master item exists
    master_item = db.query(MasterItem).filter(MasterItem.id == ingredient.master_item_id).first()
    if not master_item:
        raise HTTPException(status_code=404, detail="Master item not found")

    db_ingredient = RecipeIngredient(
        recipe_id=recipe_id,
        **ingredient.dict()
    )

    # Calculate costs for this ingredient
    if master_item.current_cost:
        db_ingredient.unit_cost = master_item.current_cost
        db_ingredient.total_cost = master_item.current_cost * ingredient.quantity

    db.add(db_ingredient)
    db.commit()
    db.refresh(db_ingredient)

    # Recalculate recipe cost
    calculate_recipe_cost(recipe_id, db)

    log_audit_event(
        db=db,
        user=current_user,
        action="recipe_ingredient_add",
        entity_type="recipe",
        entity_id=recipe_id,
        changes={"ingredient": master_item.name}
    )

    ing_response = RecipeIngredientResponse.from_orm(db_ingredient)
    ing_response.master_item_name = master_item.name
    return ing_response


@router.put("/ingredients/{ingredient_id}", response_model=RecipeIngredientResponse)
async def update_ingredient(
    ingredient_id: int,
    ingredient_update: RecipeIngredientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Update a recipe ingredient"""
    db_ingredient = db.query(RecipeIngredient).filter(RecipeIngredient.id == ingredient_id).first()
    if not db_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    update_data = ingredient_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_ingredient, field, value)

    # Recalculate costs if quantity changed
    if 'quantity' in update_data or 'master_item_id' in update_data:
        master_item = db.query(MasterItem).filter(MasterItem.id == db_ingredient.master_item_id).first()
        if master_item and master_item.current_cost:
            db_ingredient.unit_cost = master_item.current_cost
            db_ingredient.total_cost = master_item.current_cost * db_ingredient.quantity

    db.commit()
    db.refresh(db_ingredient)

    # Recalculate recipe cost
    calculate_recipe_cost(db_ingredient.recipe_id, db)

    return RecipeIngredientResponse.from_orm(db_ingredient)


@router.delete("/ingredients/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient(
    ingredient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Remove an ingredient from a recipe"""
    db_ingredient = db.query(RecipeIngredient).filter(RecipeIngredient.id == ingredient_id).first()
    if not db_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    recipe_id = db_ingredient.recipe_id

    db.delete(db_ingredient)
    db.commit()

    # Recalculate recipe cost
    calculate_recipe_cost(recipe_id, db)

    return None


# Costing endpoints

@router.post("/{recipe_id}/calculate-cost", response_model=RecipeCostCalculation)
async def calculate_cost(
    recipe_id: int,
    labor_rate_per_hour: Optional[Decimal] = Query(None, description="Labor rate per hour"),
    overhead_percentage: Optional[Decimal] = Query(None, description="Overhead as % of ingredient cost"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate and update recipe cost"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    result = calculate_recipe_cost(
        recipe_id,
        db,
        labor_rate=labor_rate_per_hour,
        overhead_pct=overhead_percentage
    )

    return result


@router.post("/calculate-all-costs")
async def calculate_all_costs(
    labor_rate_per_hour: Optional[Decimal] = Query(None, description="Labor rate per hour"),
    overhead_percentage: Optional[Decimal] = Query(None, description="Overhead as % of ingredient cost"),
    active_only: bool = Query(True, description="Only recalculate active recipes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Recalculate costs for all recipes"""
    query = db.query(Recipe)

    if active_only:
        query = query.filter(Recipe.is_active == True)

    recipes = query.all()

    results = {
        "total_recipes": len(recipes),
        "updated": 0,
        "failed": 0,
        "errors": []
    }

    for recipe in recipes:
        try:
            calculate_recipe_cost(
                recipe.id,
                db,
                labor_rate=labor_rate_per_hour,
                overhead_pct=overhead_percentage
            )
            results["updated"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "recipe_id": recipe.id,
                "recipe_name": recipe.name,
                "error": str(e)
            })

    # Audit log
    log_audit_event(
        db=db,
        user=current_user,
        action="bulk_cost_calculation",
        entity_type="recipe",
        changes=results
    )

    return results


def calculate_recipe_cost(
    recipe_id: int,
    db: Session,
    labor_rate: Optional[Decimal] = None,
    overhead_pct: Optional[Decimal] = None
) -> RecipeCostCalculation:
    """
    Calculate total recipe cost including ingredients, labor, and overhead
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise ValueError("Recipe not found")

    # Get all ingredients
    ingredients = db.query(RecipeIngredient).filter(
        RecipeIngredient.recipe_id == recipe_id
    ).all()

    # Fetch pricing from Hub (source of truth for vendor item costs)
    # This matches how the items API fetches pricing for display
    hub_pricing = {}
    try:
        from sqlalchemy import create_engine, text
        import os
        HUB_DATABASE_URL = os.getenv("HUB_DATABASE_URL", "postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db")
        hub_engine = create_engine(HUB_DATABASE_URL)
        with hub_engine.connect() as conn:
            # Get unit_cost from hub_vendor_items (preferred or most recent)
            pricing_query = text("""
                SELECT DISTINCT ON (inventory_master_item_id)
                    inventory_master_item_id,
                    unit_cost
                FROM hub_vendor_items
                WHERE inventory_master_item_id IS NOT NULL
                  AND is_active = true
                  AND unit_cost IS NOT NULL
                  AND unit_cost > 0
                ORDER BY inventory_master_item_id, is_preferred DESC, updated_at DESC
            """)
            results = conn.execute(pricing_query).fetchall()
            for row in results:
                hub_pricing[row[0]] = Decimal(str(row[1]))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not fetch pricing from Hub for recipe costing: {e}")

    # Calculate ingredient costs
    # Import MasterItemCountUnit for unit conversion
    from restaurant_inventory.models.master_item_count_unit import MasterItemCountUnit

    ingredient_cost = Decimal('0')
    ingredient_breakdown = []

    for ing in ingredients:
        master_item = db.query(MasterItem).filter(MasterItem.id == ing.master_item_id).first()
        if not master_item:
            continue

        # Get base cost: first try Hub pricing, then fall back to current_cost
        base_cost = hub_pricing.get(master_item.id)
        if base_cost is None and master_item.current_cost:
            base_cost = Decimal(str(master_item.current_cost))

        if base_cost is None or base_cost <= 0:
            # No pricing available for this item
            ingredient_breakdown.append({
                "item_name": master_item.name,
                "quantity": float(ing.quantity),
                "unit": ing.unit,
                "unit_cost": None,
                "total_cost": None,
                "error": "No pricing available"
            })
            continue

        unit_cost = base_cost  # Default: assume ingredient unit matches primary unit

        # Find the ingredient's unit in the item's count units
        count_units = db.query(MasterItemCountUnit).filter(
            MasterItemCountUnit.master_item_id == master_item.id
        ).all()

        # Look for matching unit by name (case-insensitive)
        ing_unit_lower = ing.unit.lower() if ing.unit else ''
        matched_unit = None
        primary_unit = None

        for cu in count_units:
            if cu.is_primary:
                primary_unit = cu
            if cu.uom_name and cu.uom_name.lower() == ing_unit_lower:
                matched_unit = cu
                break
            if cu.uom_abbreviation and cu.uom_abbreviation.lower() == ing_unit_lower:
                matched_unit = cu
                break

        # Apply conversion factor if needed
        # If recipe uses a secondary unit, multiply base cost by conversion factor
        # E.g., if base cost is $2/lb and recipe uses "Case" (40 lb), cost is $2 * 40 = $80/case
        if matched_unit and matched_unit.conversion_to_primary:
            conversion_factor = Decimal(str(matched_unit.conversion_to_primary))
            unit_cost = base_cost * conversion_factor

        ing.unit_cost = unit_cost
        ing.total_cost = unit_cost * ing.quantity
        ingredient_cost += ing.total_cost

        ingredient_breakdown.append({
            "item_name": master_item.name,
            "quantity": float(ing.quantity),
            "unit": ing.unit,
            "unit_cost": float(ing.unit_cost),
            "total_cost": float(ing.total_cost)
        })

    # Calculate labor cost
    labor_cost = Decimal('0')
    if labor_rate and (recipe.prep_time_minutes or recipe.cook_time_minutes):
        total_minutes = (recipe.prep_time_minutes or 0) + (recipe.cook_time_minutes or 0)
        labor_cost = (labor_rate / Decimal('60')) * Decimal(str(total_minutes))
    elif recipe.labor_cost:
        labor_cost = recipe.labor_cost

    # Calculate overhead
    overhead_cost = Decimal('0')
    if overhead_pct:
        overhead_cost = ingredient_cost * (overhead_pct / Decimal('100'))
    elif recipe.overhead_cost:
        overhead_cost = recipe.overhead_cost

    # Total cost
    total_cost = ingredient_cost + labor_cost + overhead_cost

    # Cost per portion - calculate from portion_size and yield_quantity
    cost_per_portion = None
    portions = None
    if recipe.portion_size and recipe.portion_size > 0:
        # Calculate number of portions from yield divided by portion size
        portions = int(recipe.yield_quantity / recipe.portion_size)
        if portions > 0:
            cost_per_portion = total_cost / Decimal(str(portions))
    elif recipe.yield_quantity:
        # If no portion size, assume yield_quantity is the number of portions
        portions = int(recipe.yield_quantity)
        if portions > 0:
            cost_per_portion = total_cost / Decimal(str(portions))

    # Calculate food cost percentage if selling price is set
    food_cost_percentage = None
    if recipe.selling_price and recipe.selling_price > 0 and cost_per_portion:
        food_cost_percentage = (cost_per_portion / recipe.selling_price) * Decimal('100')

    # Update recipe
    recipe.ingredient_cost = ingredient_cost
    recipe.labor_cost = labor_cost
    recipe.overhead_cost = overhead_cost
    recipe.total_cost = total_cost
    recipe.cost_per_portion = cost_per_portion
    recipe.food_cost_percentage = food_cost_percentage

    from datetime import datetime
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    def get_now(): return datetime.now(_ET)
    recipe.last_costed = get_now()

    db.commit()

    return RecipeCostCalculation(
        recipe_id=recipe_id,
        recipe_name=recipe.name,
        ingredient_cost=ingredient_cost,
        labor_cost=labor_cost,
        overhead_cost=overhead_cost,
        total_cost=total_cost,
        cost_per_portion=cost_per_portion,
        portions=portions,
        ingredient_breakdown=ingredient_breakdown
    )


# PDF Export endpoints

@router.get("/{recipe_id}/export/pdf")
async def export_recipe_pdf(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export a single recipe as PDF"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Get recipe data with ingredients
    recipe_response = await get_recipe(recipe_id, db, current_user)

    # Calculate portions for PDF
    portions = None
    if recipe_response.portion_size and recipe_response.portion_size > 0:
        portions = int(recipe_response.yield_quantity / recipe_response.portion_size)
    elif recipe_response.yield_quantity:
        portions = int(recipe_response.yield_quantity)

    # Convert to dict for PDF generator
    recipe_dict = {
        'name': recipe_response.name,
        'category': recipe_response.category,
        'description': recipe_response.description,
        'yield_quantity': float(recipe_response.yield_quantity),
        'yield_unit': recipe_response.yield_unit,
        'portions_per_recipe': portions,
        'prep_time_minutes': recipe_response.prep_time_minutes,
        'cook_time_minutes': recipe_response.cook_time_minutes,
        'instructions': recipe_response.instructions,
        'ingredient_cost': float(recipe_response.ingredient_cost) if recipe_response.ingredient_cost else 0,
        'labor_cost': float(recipe_response.labor_cost) if recipe_response.labor_cost else 0,
        'overhead_cost': float(recipe_response.overhead_cost) if recipe_response.overhead_cost else 0,
        'total_cost': float(recipe_response.total_cost) if recipe_response.total_cost else 0,
        'cost_per_portion': float(recipe_response.cost_per_portion) if recipe_response.cost_per_portion else None,
        'ingredients': [
            {
                'master_item_name': ing.master_item_name,
                'quantity': float(ing.quantity),
                'unit': ing.unit,
                'unit_cost': float(ing.unit_cost) if ing.unit_cost else None,
                'total_cost': float(ing.total_cost) if ing.total_cost else None
            }
            for ing in recipe_response.ingredients
        ]
    }

    # Generate PDF
    pdf_generator = RecipePDFGenerator()
    pdf_buffer = pdf_generator.generate_recipe_pdf(recipe_dict)

    # Return as downloadable file
    filename = f"{recipe.name.replace(' ', '_')}_recipe.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/export/cost-report")
async def export_recipe_cost_report(
    active_only: bool = Query(True, description="Only include active recipes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export recipe cost report as PDF"""
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    query = db.query(Recipe)
    if active_only:
        query = query.filter(Recipe.is_active == True)

    recipes = query.order_by(Recipe.category, Recipe.name).all()

    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#ffffff'),
        backColor=colors.HexColor('#2c3e50'),
        alignment=TA_CENTER,
        spaceAfter=12,
        leftIndent=0,
        rightIndent=0,
        leading=20
    )

    title = Paragraph("Recipe Cost Report", title_style)
    elements.append(title)

    # Subtitle with date
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    subtitle = Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style)
    elements.append(subtitle)

    # Prepare table data
    data = [[
        'Recipe',
        'Category',
        'Portions',
        'Ing. Cost',
        'Labor',
        'Total Cost',
        'Cost/Portion',
        'Selling Price',
        'Food Cost %',
        'Profit'
    ]]

    for recipe in recipes:
        # Calculate portions
        portions = ''
        if recipe.portion_size and recipe.portion_size > 0:
            portions = str(int(recipe.yield_quantity / recipe.portion_size))
        elif recipe.yield_quantity:
            portions = str(int(recipe.yield_quantity))

        # Calculate profit
        profit = ''
        if recipe.selling_price and recipe.cost_per_portion:
            profit_val = float(recipe.selling_price) - float(recipe.cost_per_portion)
            profit = f'${profit_val:.2f}'

        data.append([
            recipe.name[:25],  # Truncate long names
            recipe.category.title(),
            portions,
            f'${float(recipe.ingredient_cost):.2f}' if recipe.ingredient_cost else '-',
            f'${float(recipe.labor_cost):.2f}' if recipe.labor_cost else '-',
            f'${float(recipe.total_cost):.2f}' if recipe.total_cost else '-',
            f'${float(recipe.cost_per_portion):.2f}' if recipe.cost_per_portion else '-',
            f'${float(recipe.selling_price):.2f}' if recipe.selling_price else '-',
            f'{float(recipe.food_cost_percentage):.1f}%' if recipe.food_cost_percentage else '-',
            profit
        ])

    # Create table
    table = Table(data, repeatRows=1)

    # Table styling
    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),  # Align numbers to right
        ('ALIGN', (0, 1), (1, -1), 'LEFT'),    # Align text to left
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),

        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),

        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
    ]))

    elements.append(table)

    # Add summary
    elements.append(Spacer(1, 0.3*inch))
    summary_text = f"Total Recipes: {len(recipes)}"
    summary = Paragraph(summary_text, styles['Normal'])
    elements.append(summary)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    from fastapi.responses import Response
    filename = f"recipe_cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/{recipe_id}/upload-image")
async def upload_recipe_image(
    recipe_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """Upload an image for a recipe"""
    # Check recipe exists
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )

    # Create uploads directory if it doesn't exist
    upload_dir = Path("/app/uploads/recipes")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = upload_dir / unique_filename

    # Save file
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Update recipe with image URL
    old_image_url = recipe.image_url
    recipe.image_url = f"/uploads/recipes/{unique_filename}"
    db.commit()

    # Delete old image if it exists
    if old_image_url:
        try:
            old_path = Path(f"/app{old_image_url}")
            if old_path.exists():
                old_path.unlink()
        except Exception:
            pass  # Ignore errors when deleting old image

    # Audit log
    await log_audit_event(
        db=db,
        user_id=current_user.id,
        action="update",
        resource_type="recipe",
        resource_id=recipe_id,
        description=f"Uploaded image for recipe: {recipe.name}",
        changes={"image_url": {"old": old_image_url, "new": recipe.image_url}}
    )

    return {"image_url": recipe.image_url, "message": "Image uploaded successfully"}


@router.post("/parse-upload")
async def parse_recipe_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Parse an uploaded recipe document using AI"""
    from restaurant_inventory.core.recipe_parser import RecipeParser
    import tempfile
    import os

    # Validate file type
    allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.txt'}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}"
        )

    # Save uploaded file to temporary location
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Parse the recipe
        parser = RecipeParser()
        result = parser.parse_recipe_with_ai(temp_path, file_ext[1:])  # Remove the dot from extension

        # Clean up temp file
        os.unlink(temp_path)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to parse recipe")
            )

        # Return parsed data
        parsed_data = result.get("data", {})

        # Log the action
        log_audit_event(
            db=db,
            user=current_user,
            action="parse_recipe_upload",
            entity_type="recipe",
            entity_id=None,
            changes={"filename": file.filename, "parsed": True}
        )

        return parsed_data

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
