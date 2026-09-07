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
from config_file import get_config, set_config
from database import Base, engine, reconnect, init_db_at, apply_migrations
import models  # noqa: F401 — register all tables with Base.metadata
from routes import register_routes
from services.monitoring import record_request

logger = logging.getLogger(__name__)

MONITORED_PATHS = {
    "/api/hymns/service", "/api/program/current", "/api/bible/service",
}


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if path in MONITORED_PATHS or path.startswith("/api/feed/"):
            record_request(path)
        return await call_next(request)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent heuristic browser caching of pages and API responses.

    Without explicit Cache-Control, browsers may serve stale HTML for
    previously visited URLs — after an app update that mixes old cached
    pages with new fragments and JS. Static assets keep normal caching.
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/static"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


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


def _apply_custom_paths() -> str:
    """Read custom paths from config file (or fallback to bootstrap DB). Returns resolved DB path."""
    db_path = settings.DEFAULT_DB_PATH

    # 1. Try config file first (solves chicken-and-egg problem)
    cfg_db = get_config("db_path")
    cfg_upload = get_config("upload_dir")

    custom_db = cfg_db
    custom_upload = cfg_upload

    # 2. Fallback: read from bootstrap DB if config file had nothing
    if not custom_db and os.path.exists(db_path):
        custom_db = _read_setting(db_path, "db_path")
    if not custom_upload and os.path.exists(db_path):
        custom_upload = _read_setting(db_path, "upload_dir")

    # 3. Migrate legacy settings into config file for next time
    if custom_db and not cfg_db:
        set_config("db_path", custom_db)
    if custom_upload and not cfg_upload:
        set_config("upload_dir", custom_upload)

    # 4. Apply custom database path
    if custom_db and os.path.abspath(custom_db) != os.path.abspath(db_path):
        if os.path.exists(custom_db):
            reconnect(f"sqlite:///{custom_db}")
            logger.info("Connected to custom database: %s", custom_db)
            db_path = custom_db
        else:
            logger.warning("Custom DB path not found: %s — using default", custom_db)

    # 5. Apply custom upload dir
    if custom_upload:
        settings.UPLOAD_DIR = custom_upload

    # 6. Ensure default DB exists (for bootstrap settings)
    if not os.path.exists(settings.DEFAULT_DB_PATH):
        init_db_at(settings.DEFAULT_DB_PATH)

    # 7. If no database at resolved path, create it and show setup
    if not os.path.exists(db_path):
        init_db_at(db_path)
        settings.needs_setup = True

    return db_path


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI()

    # Apply custom paths, run migrations, then let ORM fill any gaps
    actual_db = _apply_custom_paths()
    apply_migrations(actual_db)
    Base.metadata.create_all(bind=engine)

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Vendored static assets (Bootstrap, htmx, Sortable, Chart.js, Coloris)
    # served locally: no CDN round-trips blocking render, works offline.
    from fastapi.staticfiles import StaticFiles
    app.mount(
        "/static", StaticFiles(directory=settings.resolve_static_dir()),
        name="static",
    )

    # Setup Jinja2 templates on app state (accessible via request.app.state.templates)
    template_dir = settings.resolve_template_dir()
    templates = Jinja2Templates(directory=template_dir)
    templates.env.globals["app_version"] = settings.APP_VERSION
    app.state.templates = templates

    # Register all route modules
    register_routes(app)

    # Track request rates for monitored API endpoints
    app.add_middleware(MonitoringMiddleware)
    app.add_middleware(NoCacheMiddleware)

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
