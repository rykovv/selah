"""Monitoring page and stats API."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from services.monitoring import get_all_stats, WINDOW_SECONDS

router = APIRouter()


@router.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request):
    """Render the monitoring dashboard page."""
    templates = request.app.state.templates
    return templates.TemplateResponse("monitoring.html", {"request": request})


@router.get("/api/monitoring/stats")
def monitoring_stats(window: int = Query(default=WINDOW_SECONDS, ge=1, le=300)):
    """Return current requests-per-second for monitored endpoints."""
    stats = get_all_stats(window)
    return {
        "vmix_rps": stats.get("/api/vmix", 0.0),
        "program_rps": stats.get("/api/program/current", 0.0),
    }
