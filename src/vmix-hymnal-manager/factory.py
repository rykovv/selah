import logging
import os
import sqlite3
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from config import settings
from database import Base, engine, reconnect, init_db_at
import models  # noqa: F401 — register all tables with Base.metadata
from routes import register_routes
from services.monitoring import record_request

logger = logging.getLogger(__name__)

MONITORED_PATHS = {"/api/vmix", "/api/program/current"}


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if path in MONITORED_PATHS or path.startswith("/api/feed/"):
            record_request(path)
        return await call_next(request)


class SetupRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect all pages to /settings until initial setup is complete."""

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if path.startswith("/settings") or path.startswith("/api/settings"):
            return await call_next(request)
        if request.method == "GET" and not path.startswith(("/favicon",)):
            return RedirectResponse("/settings", status_code=302)
        return await call_next(request)


def _read_setting(db_path: str, key: str):
    """Read a single setting from app_settings using raw SQLite."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _apply_custom_paths():
    """Read custom paths from default DB and apply them."""
    db_path = settings.DEFAULT_DB_PATH

    if not os.path.exists(db_path):
        # First run — create default DB with all tables
        init_db_at(db_path)
        settings.needs_setup = True
        return

    # Read custom paths from app_settings in the default DB
    custom_db = _read_setting(db_path, "db_path")
    custom_upload = _read_setting(db_path, "upload_dir")

    if custom_db and custom_db != db_path:
        if os.path.exists(custom_db):
            reconnect(f"sqlite:///{custom_db}")
            logger.info("Connected to custom database: %s", custom_db)
        else:
            logger.warning("Custom DB path not found: %s — using default", custom_db)

    if custom_upload:
        settings.UPLOAD_DIR = custom_upload


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI()

    # Apply custom paths before creating tables
    _apply_custom_paths()

    # Create database tables (on whichever engine is active)
    Base.metadata.create_all(bind=engine)

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Setup Jinja2 templates on app state (accessible via request.app.state.templates)
    template_dir = settings.resolve_template_dir()
    app.state.templates = Jinja2Templates(directory=template_dir)

    # Register all route modules
    register_routes(app)

    # Track request rates for monitored API endpoints
    app.add_middleware(MonitoringMiddleware)

    # Redirect to settings page until setup is complete
    if settings.needs_setup:
        app.add_middleware(SetupRedirectMiddleware)

    # Global exception handler — return useful error messages
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
        msg = str(exc) or "An unexpected error occurred"

        # HTMX request — plain text (picked up by our htmx:afterRequest listener)
        if request.headers.get("HX-Request"):
            return PlainTextResponse(msg, status_code=500)

        # AJAX / fetch request — JSON
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JSONResponse({"detail": msg}, status_code=500)

        # Regular browser request — minimal HTML page
        return HTMLResponse(
            f"<h2>Error</h2><p>{msg}</p><a href='/'>Back to Dashboard</a>",
            status_code=500,
        )

    return app
