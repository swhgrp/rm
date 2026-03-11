"""Recipe Creator service — generates original recipes using Claude + cookbook context."""

import json
import logging
from typing import Optional, List

import anthropic

from restaurant_cookbook.core.config import settings

logger = logging.getLogger(__name__)

CREATOR_SYSTEM_PROMPT = """You are a professional recipe developer and cookbook author. Using the provided cookbook excerpts as your technical and stylistic reference, create an original recipe based on the user's specifications. Synthesize techniques authentically, write in a polished cookbook style, and note which techniques were inspired by which source books. Do not copy recipes verbatim — create something new.

You MUST respond with valid JSON in exactly this format:
{
    "title": "Recipe Name",
    "category": "entree",
    "description": "A brief headnote describing the dish",
    "yield_quantity": "6",
    "yield_unit": "servings",
    "prep_time_minutes": 20,
    "cook_time_minutes": 45,
    "ingredients": [
        {"quantity": "2", "unit": "lbs", "item": "beef flap steak", "preparation": "trimmed, cut into 4 portions"},
        {"quantity": "3", "unit": "tbsp", "item": "olive oil"},
        {"quantity": "1", "unit": "cup", "item": "chicken stock"}
    ],
    "instructions": "1. Season the steak generously with salt and pepper.\\n2. Heat olive oil in a cast iron skillet over high heat.\\n3. Sear steaks 3 minutes per side.\\n...",
    "technique_notes": "The braising technique is inspired by [Book Title], p. XX...",
    "wine_pairing": "A medium-bodied red such as..."
}

Rules:
- "category" must be one of: appetizer, entree, side, dessert, beverage, sauce, prep, other
- "yield_quantity" is a string number, "yield_unit" is the unit (servings, portions, quarts, etc.)
- "prep_time_minutes" and "cook_time_minutes" are integers (minutes)
- Each ingredient must have "quantity", "unit", "item", and optionally "preparation"
- Instructions should be numbered steps separated by newlines
- Keep ingredient units consistent (lbs, oz, cups, tbsp, tsp, each, etc.)"""


def create_recipe(
    primary_ingredients: str,
    cuisine_style: str,
    cooking_method: str,
    context_chunks: List[dict],
    dietary_notes: str = "",
) -> dict:
    """Generate an original recipe using Claude with cookbook context."""
    if not settings.ANTHROPIC_API_KEY:
        return {
            "error": "Anthropic API key not configured. Please set ANTHROPIC_API_KEY.",
            "tokens_used": 0,
        }

    # Build context
    context_parts = []
    books_referenced = set()
    for chunk in context_chunks:
        title = chunk.get("book_title", "Unknown")
        page = chunk.get("page_number", "?")
        content = chunk.get("content", "")
        context_parts.append(f'[Source: "{title}", Page {page}]\n{content}')
        books_referenced.add(title)

    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "No specific cookbook references provided."

    dietary_line = f"\nAdditional instructions: {dietary_notes}" if dietary_notes else ""

    user_message = f"""Here are relevant technique and flavor excerpts from cookbooks:

{context_text}

---

Please create an original recipe with these specifications:
- Primary ingredients: {primary_ingredients}
- Cuisine style: {cuisine_style}
- Cooking method: {cooking_method}{dietary_line}

Respond with the JSON format specified in your instructions."""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=CREATOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = response.content[0].text
        tokens_used = (response.usage.input_tokens or 0) + (
            response.usage.output_tokens or 0
        )

        # Parse JSON from response
        try:
            clean = response_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                clean = clean.rsplit("```", 1)[0]
            recipe_data = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("Failed to parse recipe JSON, returning raw text")
            recipe_data = {
                "title": "Generated Recipe",
                "category": "other",
                "description": response_text[:200],
                "yield_quantity": "",
                "yield_unit": "",
                "prep_time_minutes": None,
                "cook_time_minutes": None,
                "ingredients": [],
                "instructions": response_text,
                "technique_notes": "",
                "wine_pairing": "",
            }

        recipe_data["tokens_used"] = tokens_used
        recipe_data["books_referenced"] = list(books_referenced)
        return recipe_data

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return {"error": f"AI service error: {str(e)}", "tokens_used": 0}
    except Exception as e:
        logger.error(f"Unexpected error in recipe creator: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}", "tokens_used": 0}
