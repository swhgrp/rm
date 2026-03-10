"""
Cookbook AI System — RAG-based cookbook reference and recipe creation tool
SW Hospitality Group
"""

import logging
from urllib.parse import quote

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from restaurant_cookbook.core.config import settings
from restaurant_cookbook.core.deps import get_db, get_current_user
from restaurant_cookbook.models.user import User
from restaurant_cookbook.api import books, query, recipes, health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="RAG-based cookbook reference and recipe creation tool",
    root_path="/cookbook",
)


# Custom 401 handler — redirect HTML requests to Portal login
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        accept = request.headers.get("accept", "")
        path = str(request.url.path)
        is_api = "/api/" in path

        if not is_api and "text/html" in accept:
            redirect_path = f"/cookbook{path}" if not path.startswith("/cookbook") else path
            return RedirectResponse(
                url=f"/portal/login?redirect={quote(redirect_path)}",
                status_code=302,
            )

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSO login endpoint — Portal redirects here with a token
@app.get("/api/auth/sso-login")
async def sso_login(token: str):
    """Handle SSO login from Portal — validate token and set cookie, redirect to portal cookbook page."""
    from jose import jwt, JWTError

    try:
        payload = jwt.decode(token, settings.PORTAL_SECRET_KEY, algorithms=["HS256"])
        # Redirect to the portal-served cookbook dashboard
        response = RedirectResponse(url="/portal/cookbook/", status_code=303)
        # Set cookie so subsequent API calls from the cookbook pages are authenticated
        response.set_cookie(
            key="portal_session",
            value=token,
            httponly=True,
            max_age=1800,
            path="/",
            samesite="lax",
            secure=True,
        )
        return response
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# API routes
app.include_router(health.router, tags=["health"])
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])


# Query history endpoint
@app.get("/api/queries")
def list_queries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent query history."""
    from restaurant_cookbook.models.query import Query

    queries = (
        db.query(Query)
        .filter(Query.user_id == current_user.id)
        .order_by(Query.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": q.id,
            "query_text": q.query_text,
            "mode": q.mode,
            "books_referenced": q.books_referenced,
            "response_text": q.response_text[:200] if q.response_text else None,
            "tokens_used": q.tokens_used,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in queries
    ]
