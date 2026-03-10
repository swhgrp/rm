"""Query API — Recipe Lookup and Recipe Creator endpoints."""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from restaurant_cookbook.core.deps import get_db, get_current_user
from restaurant_cookbook.core.config import settings
from restaurant_cookbook.models.query import Query
from restaurant_cookbook.models.recipe import Recipe
from restaurant_cookbook.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class LookupRequest(BaseModel):
    question: str
    book_ids: Optional[List[int]] = None


class CreateRequest(BaseModel):
    primary_ingredients: str
    cuisine_style: str
    cooking_method: str
    book_ids: Optional[List[int]] = None
    dietary_notes: Optional[str] = ""


@router.post("/query")
def recipe_lookup(
    req: LookupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recipe Lookup — ask a question about cookbooks."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Retrieve relevant chunks from ChromaDB
    from restaurant_cookbook.services.embeddings import get_embedding_service
    from restaurant_cookbook.services.chroma_client import get_chroma_service
    from restaurant_cookbook.services.ai_query import query_cookbook

    embed_svc = get_embedding_service()
    chroma_svc = get_chroma_service()

    query_embedding = embed_svc.embed_query(req.question)
    results = chroma_svc.query(
        query_embedding=query_embedding,
        n_results=settings.TOP_K_RESULTS,
        book_ids=req.book_ids,
    )

    # Build context from results
    context_chunks = []
    if results and results.get("documents") and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            context_chunks.append(
                {
                    "content": doc,
                    "book_title": meta.get("book_title", "Unknown"),
                    "page_number": meta.get("page_number", 0),
                }
            )

    # Query Claude
    ai_result = query_cookbook(req.question, context_chunks)

    # Save query to DB
    query_record = Query(
        user_id=current_user.id,
        query_text=req.question,
        mode="lookup",
        books_referenced=ai_result.get("books_referenced", []),
        response_text=ai_result["response"],
        tokens_used=ai_result.get("tokens_used", 0),
    )
    db.add(query_record)
    db.commit()

    return {
        "response": ai_result["response"],
        "books_referenced": ai_result.get("books_referenced", []),
        "tokens_used": ai_result.get("tokens_used", 0),
        "chunks_used": len(context_chunks),
        "query_id": query_record.id,
    }


@router.post("/create")
def create_recipe(
    req: CreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recipe Creator — generate an original recipe."""
    if not req.primary_ingredients.strip():
        raise HTTPException(status_code=400, detail="Primary ingredients required")

    # Retrieve relevant technique chunks
    from restaurant_cookbook.services.embeddings import get_embedding_service
    from restaurant_cookbook.services.chroma_client import get_chroma_service
    from restaurant_cookbook.services.recipe_creator import create_recipe as ai_create

    embed_svc = get_embedding_service()
    chroma_svc = get_chroma_service()

    # Search for relevant techniques
    search_text = f"{req.cooking_method} {req.cuisine_style} {req.primary_ingredients}"
    query_embedding = embed_svc.embed_query(search_text)
    results = chroma_svc.query(
        query_embedding=query_embedding,
        n_results=settings.TOP_K_RESULTS,
        book_ids=req.book_ids,
    )

    context_chunks = []
    if results and results.get("documents") and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            context_chunks.append(
                {
                    "content": doc,
                    "book_title": meta.get("book_title", "Unknown"),
                    "page_number": meta.get("page_number", 0),
                }
            )

    # Generate recipe
    recipe_data = ai_create(
        primary_ingredients=req.primary_ingredients,
        cuisine_style=req.cuisine_style,
        cooking_method=req.cooking_method,
        context_chunks=context_chunks,
        dietary_notes=req.dietary_notes or "",
    )

    if "error" in recipe_data:
        raise HTTPException(status_code=500, detail=recipe_data["error"])

    # Save to DB
    recipe = Recipe(
        title=recipe_data.get("title", "Untitled Recipe"),
        description=recipe_data.get("description", ""),
        ingredients=recipe_data.get("ingredients", ""),
        instructions=recipe_data.get("instructions", ""),
        technique_notes=recipe_data.get("technique_notes", ""),
        wine_pairing=recipe_data.get("wine_pairing", ""),
        cuisine_style=req.cuisine_style,
        cooking_method=req.cooking_method,
        primary_ingredients=req.primary_ingredients,
        books_referenced=recipe_data.get("books_referenced", []),
        created_by=current_user.id,
    )
    db.add(recipe)

    # Save query record too
    query_record = Query(
        user_id=current_user.id,
        query_text=f"Create: {req.primary_ingredients} ({req.cuisine_style}, {req.cooking_method})",
        mode="create",
        books_referenced=recipe_data.get("books_referenced", []),
        response_text=recipe_data.get("title", ""),
        tokens_used=recipe_data.get("tokens_used", 0),
    )
    db.add(query_record)
    db.commit()
    db.refresh(recipe)

    return {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "ingredients": recipe.ingredients,
        "instructions": recipe.instructions,
        "technique_notes": recipe.technique_notes,
        "wine_pairing": recipe.wine_pairing,
        "books_referenced": recipe_data.get("books_referenced", []),
        "tokens_used": recipe_data.get("tokens_used", 0),
    }
