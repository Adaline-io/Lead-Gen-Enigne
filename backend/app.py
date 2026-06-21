"""FastAPI application entry point.

Wires middleware (sessions, CORS), the consistent ``{error, detail}`` error
shape, and mounts routers. Run with::

    uv run uvicorn backend.app:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.config import settings
from backend.db import create_all, fail_interrupted_jobs, wipe_lead_data
from backend.routers import auth as auth_router
from backend.routers import jobs as jobs_router
from backend.routers import leads as leads_router
from backend.routers import reports as reports_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev/MVP convenience: ensure tables exist on boot. Alembic owns prod.
    create_all()
    if settings.RESET_DATA_ON_START:
        wipe_lead_data()
        print(
            "⚠  RESET_DATA_ON_START is ON — cleared all leads/jobs/activity "
            "(users kept). Set RESET_DATA_ON_START=false in .env to keep data.",
            flush=True,
        )
    # Clear any job left "running" by a previous restart/crash.
    fail_interrupted_jobs()
    yield


app = FastAPI(title="Adaline Lead-Gen Engine", version="0.1.0", lifespan=lifespan)

# Session cookie (HMAC-signed, httpOnly). https_only flips to True on deploy.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    max_age=86400,
    https_only=False,
    same_site="lax",
)

# CORS for the local vanilla frontend. credentials=True is required so the
# session cookie rides along with fetch(..., {credentials: 'include'}).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render errors as ``{"error": ...}`` (CLAUDE.md §5 conventions)."""
    detail = exc.detail
    if isinstance(detail, dict):
        content = detail
    else:
        content = {"error": detail}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "invalid request", "detail": jsonable_encoder(exc.errors())},
    )


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(auth_router.router)
app.include_router(leads_router.router)
app.include_router(jobs_router.router)
app.include_router(reports_router.router)


# Serve the frontend from the backend so a single `uvicorn` process runs the
# whole app at http://localhost:8000/ (no separate static server, same-origin
# cookies). Mounted last so /api/* and /docs match first.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
