"""Main dashboard route."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from models import ServiceProgramModel, ServicePlanHymnModel
from utils import sort_program_items

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard showing the active program and hymn service plan."""
    active_prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.is_active == True)
        .first()
    )
    if active_prog:
        active_prog.items = sort_program_items(active_prog.items)

    plan = (
        db.query(ServicePlanHymnModel)
        .order_by(ServicePlanHymnModel.sequence)
        .all()
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "program": active_prog, "service_plan": plan},
    )
