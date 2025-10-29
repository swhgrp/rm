"""Files Management Service - Main Application"""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from files.core.config import settings
from files.core.deps import get_current_user
from files.api import auth, filemanager, shares
from files.models.user import User

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="src/files/templates")

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(filemanager.router)
app.include_router(shares.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user)):
    """File manager page"""
    return templates.TemplateResponse(
        "filemanager.html",
        {
            "request": request,
            "user": user
        }
    )


@app.get("/share/{share_token}", response_class=HTMLResponse)
async def public_share(request: Request, share_token: str):
    """Public share access page"""
    return templates.TemplateResponse(
        "public_share.html",
        {
            "request": request,
            "share_token": share_token
        }
    )


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "files", "version": settings.APP_VERSION}
