import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from config import settings
from database import Base, engine
import models  # noqa: F401 — register all tables with Base.metadata
from routes import register_routes
from services.monitoring import record_request

logger = logging.getLogger(__name__)

MONITORED_PATHS = {"/api/vmix", "/api/program/current"}


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if request.url.path in MONITORED_PATHS:
            record_request(request.url.path)
        return await call_next(request)


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI()

    # Create database tables
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
