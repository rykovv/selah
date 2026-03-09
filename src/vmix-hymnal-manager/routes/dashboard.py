"""Main dashboard route."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from database import get_db
from models import ServiceProgramModel, ServicePlanHymnModel
from utils import sort_program_items

router = APIRouter()


_FAVICON_SVG = '''\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#8b5cf6"/>
</linearGradient></defs>
<rect width="32" height="32" rx="8" fill="url(#g)"/>
<g transform="translate(6,5) scale(1.25)" fill="white">
<path d="M6 13c0 1.105-1.12 2-2.5 2S1 14.105 1 13s1.12-2 2.5-2 2.5.896 2.5 2m9-2c0 1.105-1.12 2-2.5 2s-2.5-.895-2.5-2 1.12-2 2.5-2 2.5.895 2.5 2"/>
<path d="M14 11V2h1v9zM6 3v10H5V3z"/>
<path d="M5 2.905a1 1 0 0 1 .9-.995l8-.8a1 1 0 0 1 1.1.995V3L5 4z"/>
</g></svg>'''


@router.get("/favicon.ico")
@router.get("/favicon.svg")
def favicon():
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml")


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
