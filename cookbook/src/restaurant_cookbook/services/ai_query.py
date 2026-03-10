"""AI query service — Recipe Lookup mode using Anthropic Claude."""

import logging
from typing import Optional, List

import anthropic

from restaurant_cookbook.core.config import settings

logger = logging.getLogger(__name__)

LOOKUP_SYSTEM_PROMPT = """You are an expert culinary assistant with deep knowledge of classical and contemporary cooking. You have been provided with excerpts from cookbooks. Answer the user's question using only the provided excerpts as your source. Always cite the book title and page number when referencing specific techniques or recipes. If the answer cannot be found in the provided excerpts, say so clearly.

Format your response with clear sections when appropriate. Use markdown formatting."""


def query_cookbook(
    question: str,
    context_chunks: List[dict],
    book_ids: Optional[List[int]] = None,
) -> dict:
    """Send a lookup query to Claude with retrieved cookbook context.

    Args:
        question: The user's question
        context_chunks: List of dicts with 'content', 'book_title', 'page_number'

    Returns:
        dict with 'response', 'tokens_used', 'books_referenced'
    """
    if not settings.ANTHROPIC_API_KEY:
        return {
            "response": "Anthropic API key not configured. Please set ANTHROPIC_API_KEY.",
            "tokens_used": 0,
            "books_referenced": [],
        }

    # Build context from retrieved chunks
    context_parts = []
    books_referenced = set()
    for chunk in context_chunks:
        title = chunk.get("book_title", "Unknown")
        page = chunk.get("page_number", "?")
        content = chunk.get("content", "")
        context_parts.append(f'[Source: "{title}", Page {page}]\n{content}')
        books_referenced.add(title)

    context_text = "\n\n---\n\n".join(context_parts)

    user_message = f"""Here are relevant excerpts from cookbooks:

{context_text}

---

Question: {question}"""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=LOOKUP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = response.content[0].text
        tokens_used = (response.usage.input_tokens or 0) + (
            response.usage.output_tokens or 0
        )

        return {
            "response": response_text,
            "tokens_used": tokens_used,
            "books_referenced": list(books_referenced),
        }

    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return {
            "response": f"AI service error: {str(e)}",
            "tokens_used": 0,
            "books_referenced": [],
        }
    except Exception as e:
        logger.error(f"Unexpected error in AI query: {e}")
        return {
            "response": f"An unexpected error occurred: {str(e)}",
            "tokens_used": 0,
            "books_referenced": [],
        }
