"""FastAPI application entry point for the RFP Response Assistant."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, get_db_connection
from app.schemas import HealthResponse
from app.api.settings import router as settings_router
from app.api.services import router as services_router
from app.api.rfps import router as rfps_router
from app.api.kb import router as kb_router
from app.api.pricing import router as pricing_router

APP_VERSION = "1.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database (tables + seed defaults) on startup."""
    init_db()
    yield


app = FastAPI(
    title="RFP Response Assistant API",
    description="Backend API supporting AI-assisted first-draft RFP response generation.",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def _allowed_origins() -> list:
    """Dev origins for the Vite server and common alternates; extend via CORS_ORIGINS env (comma-separated)."""
    ports = ("3010", "4010", "5173", "3000")
    origins = [f"http://{host}:{port}" for port in ports for host in ("localhost", "127.0.0.1")]
    extra = os.environ.get("CORS_ORIGINS", "")
    origins += [o.strip() for o in extra.split(",") if o.strip()]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-LLM-Engine", "X-LLM-Model", "X-LLM-Fallback-From"],
)

app.include_router(settings_router, prefix="/api")
app.include_router(services_router, prefix="/api")
app.include_router(rfps_router, prefix="/api")
app.include_router(kb_router, prefix="/api")
app.include_router(pricing_router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Verify backend status and SQLite database connectivity."""
    db_status = "connected"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1;").fetchone()
        conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        db_status = f"error: {exc}"

    return {"status": "ok", "version": APP_VERSION, "database": db_status}
