from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.repositories import router as repositories_router
from app.core.config import settings
from app.db.session import init_db


import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        init_db()
    except Exception as exc:
        logger.warning("Database initialization skipped or deferred: %s", exc)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "CodeLens AI — AI Codebase Intelligence Platform (Phase 1: Repository Analyzer). "
        "Discovers codebase files and performs deep Python AST code analysis."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS with configured origins (avoids illegal wildcard origin + credentials combination)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(repositories_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Health check endpoint to verify service liveness."""
    return {"status": "ok", "service": "CodeLens AI Repository Analyzer"}


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    """Root endpoint providing service metadata."""
    return {
        "project": settings.PROJECT_NAME,
        "phase": "Phase 1 - Repository Analyzer",
        "docs": "/docs",
    }
