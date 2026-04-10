"""Monitoring page and stats API."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from models import DataTableModel
from services.monitoring import get_all_stats, WINDOW_SECONDS

router = APIRouter()


@router.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request, db: Session = Depends(get_db)):
    """Render the monitoring dashboard page."""
    feed_tables = db.query(DataTableModel).order_by(DataTableModel.name).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "monitoring.html",
        {"request": request, "feed_tables": feed_tables},
    )


@router.get("/api/monitoring/stats")
def monitoring_stats(window: int = Query(default=WINDOW_SECONDS, ge=1, le=300)):
    """Return current requests-per-second for monitored endpoints."""
    stats = get_all_stats(window)
    result = {
        "hymns_rps": stats.get("/api/hymns/service", 0.0),
        "program_rps": stats.get("/api/program/current", 0.0),
        "feeds": {},
    }
    for path, rps in stats.items():
        if path.startswith("/api/feed/"):
            slug = path[len("/api/feed/"):]
            result["feeds"][slug] = rps
    return result
