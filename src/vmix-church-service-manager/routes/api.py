"""JSON API endpoints for vMix and external consumers."""

from typing import Dict, List

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AppSettingModel, DataTableModel, HymnModel, ServicePlanHymnModel,
    ServiceProgramModel, VmixRow,
)
import json

from services.hymn_set_service import get_active_set, set_plan_query
from services.program_service import serialize_program_items
from utils import get_slides_by_type, resolve_table_references

router = APIRouter()


@router.get("/api/hymns/service", response_model=List[VmixRow])
def get_vmix_feed(db: Session = Depends(get_db)):
    """Flatten the active hymn set into the row format vMix expects."""
    active_set = get_active_set(db)
    service_items = set_plan_query(db, active_set.id).all()

    vmix_output = []
    for item in service_items:
        hymn = item.hymn
        if not hymn:
            continue

        sorted_slides = get_slides_by_type(hymn, preferred_type="VMIX")
        for slide in sorted_slides:
            vmix_output.append(
                VmixRow(
                    HymnNumber=hymn.number,
                    Title=hymn.title,
                    Label=slide.label,
                    SlideText=slide.content,
                )
            )

        # Spacer after each hymn
        vmix_output.append(
            VmixRow(HymnNumber="", Title="", Label="", SlideText="")
        )

    return vmix_output


@router.get("/api/program/{id}/json")
def get_program_json(id: int, db: Session = Depends(get_db)):
    """Return JSON for a specific program."""
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if not prog:
        return JSONResponse({"detail": "Program not found"}, status_code=404)
    return serialize_program_items(prog)


@router.get("/api/program/current")
def get_current_program_json(db: Session = Depends(get_db)):
    """Return JSON for the currently active program."""
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.is_active == True)
        .first()
    )
    if not prog:
        return [{"title": "No Active Program", "subtitle": "Select one in Dashboard"}]
    return serialize_program_items(prog)


# ---------------------------------------------------------------------------
# Data table feeds
# ---------------------------------------------------------------------------

@router.get("/api/feed/{slug}")
def get_data_table_feed(slug: str, db: Session = Depends(get_db)):
    """Return JSON array of row objects for a data table."""
    table = db.query(DataTableModel).filter(DataTableModel.slug == slug).first()
    if not table:
        return JSONResponse({"detail": "Feed not found"}, status_code=404)
    rows = sorted(
        table.rows,
        key=lambda r: (r.sequence if r.sequence is not None else 9999, r.id),
    )
    return resolve_table_references([json.loads(r.data_json) for r in rows])


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

@router.get("/api/version")
def get_version():
    """Return the application version."""
    from config import settings
    return {"version": settings.APP_VERSION}


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

@router.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    """Return all app settings as a dict."""
    rows = db.query(AppSettingModel).all()
    return {r.key: r.value for r in rows}


@router.put("/api/settings")
def put_settings(data: Dict[str, str] = Body(...), db: Session = Depends(get_db)):
    """Upsert one or more settings."""
    for key, value in data.items():
        row = db.query(AppSettingModel).filter(AppSettingModel.key == key).first()
        if row:
            row.value = value
        else:
            db.add(AppSettingModel(key=key, value=value))
    db.commit()
    return JSONResponse({"ok": True})
