"""Hymn management, editor, search, plan, and PPT download routes."""

import re as _re
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import case, cast, Integer, or_
from sqlalchemy.orm import Session

from database import get_db
from models import HymnModel, HymnSetModel, SlideModel, ServicePlanHymnModel
from services.hymn_set_service import (
    get_active_set, get_set_or_active, set_plan_query, touch_set,
)
from services.pptx_service import PptxConfig, generate_hymn_plan_pptx
from utils import get_slides_by_type

router = APIRouter()

# Natural sort: numeric hymn numbers first (by int value), then non-numeric alphabetically.
# SQLite GLOB '*[^0-9]*' matches strings containing any non-digit character.
_non_numeric = or_(
    HymnModel.number.op('GLOB')('*[^0-9]*'),
    HymnModel.number == '',
    HymnModel.number.is_(None),
)
_hymn_order = (
    case((_non_numeric, 1), else_=0),
    case((_non_numeric, 0), else_=cast(HymnModel.number, Integer)),
    HymnModel.number,
)


# ---------------------------------------------------------------------------
# Hymn manager page
# ---------------------------------------------------------------------------

@router.get("/hymns", response_class=HTMLResponse)
def page_hymns_manager(
    request: Request,
    set: Optional[int] = None,
    created: Optional[int] = None,
    db: Session = Depends(get_db),
):
    current_set = get_set_or_active(db, set)
    # Card stacking order: active set first, then most recently used
    sets = (
        db.query(HymnSetModel)
        .order_by(
            HymnSetModel.is_active.desc(),
            HymnSetModel.last_used.desc(),
            HymnSetModel.id.desc(),
        )
        .all()
    )
    plan = set_plan_query(db, current_set.id).all()
    library = db.query(HymnModel).order_by(*_hymn_order).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "hymn_manager.html",
        {
            "request": request,
            "plan": plan,
            "library": library,
            "sets": sets,
            "current_set": current_set,
            "just_created": bool(created),
        },
    )


# ---------------------------------------------------------------------------
# Service plan
# ---------------------------------------------------------------------------

def _plan_list_response(request: Request, db: Session, set_id: int):
    """Render the plan list partial (with out-of-band count badge update)."""
    plan = set_plan_query(db, set_id).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/plan_list.html",
        {"request": request, "plan": plan, "oob": True},
    )


@router.post("/plan/add")
def add_to_plan(
    request: Request,
    hymn_id: int = Form(...),
    set_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if not hymn:
        return Response("Hymn not found", status_code=404)
    target_set = get_set_or_active(db, set_id)
    last_item = (
        set_plan_query(db, target_set.id)
        .order_by(None)
        .order_by(ServicePlanHymnModel.sequence.desc())
        .first()
    )
    new_seq = (last_item.sequence + 1) if last_item else 1
    db.add(ServicePlanHymnModel(
        set_id=target_set.id, sequence=new_seq, hymn_id=hymn_id
    ))
    touch_set(db, target_set.id)
    db.commit()
    if request.headers.get("HX-Request"):
        return _plan_list_response(request, db, target_set.id)
    return RedirectResponse(url=f"/hymns?set={target_set.id}", status_code=303)


@router.delete("/plan/{item_id}")
def remove_from_plan(
    item_id: int, request: Request, db: Session = Depends(get_db)
):
    item = (
        db.query(ServicePlanHymnModel)
        .filter(ServicePlanHymnModel.id == item_id)
        .first()
    )
    set_id = item.set_id if item else get_active_set(db).id
    if item:
        db.delete(item)
        touch_set(db, set_id)
        db.commit()
        _renumber_plan(db, set_id)
    return _plan_list_response(request, db, set_id)


@router.put("/plan/reorder")
def reorder_plan(order: List[int] = Body(...), db: Session = Depends(get_db)):
    """Accept a list of ServicePlanHymn IDs in their new order."""
    items = (
        db.query(ServicePlanHymnModel)
        .filter(ServicePlanHymnModel.id.in_(order))
        .all()
    )
    lookup = {item.id: item for item in items}

    # Clear to negative temporaries to avoid UNIQUE constraint violations
    for i, item_id in enumerate(order):
        if item_id in lookup:
            lookup[item_id].sequence = -(i + 1)
    db.flush()

    # Assign final positive sequences
    for i, item_id in enumerate(order):
        if item_id in lookup:
            lookup[item_id].sequence = i + 1
    if items:
        touch_set(db, items[0].set_id)
    db.commit()
    return JSONResponse({"ok": True})


def _renumber_plan(db: Session, set_id: int):
    """Renumber one set's sequences to be contiguous (1, 2, 3, ...)."""
    items = set_plan_query(db, set_id).all()
    # Clear to negative temporaries first: updates are emitted in primary-key
    # order, so direct reassignment can collide with the UNIQUE(set, sequence)
    # constraint when row ids are not aligned with sequence order.
    for i, item in enumerate(items, start=1):
        item.sequence = -i
    db.flush()

    for i, item in enumerate(items, start=1):
        item.sequence = i
    db.commit()


# ---------------------------------------------------------------------------
# Hymn sets
# ---------------------------------------------------------------------------

@router.post("/hymn-sets/new")
def new_hymn_set(db: Session = Depends(get_db)):
    new_set = HymnSetModel(name="New Hymn Set", is_active=False)
    db.add(new_set)
    db.commit()
    db.refresh(new_set)
    return RedirectResponse(
        f"/hymns?set={new_set.id}&created=1", status_code=303
    )


@router.post("/hymn-sets/{set_id}/activate")
def activate_hymn_set(set_id: int, db: Session = Depends(get_db)):
    target = db.query(HymnSetModel).filter(HymnSetModel.id == set_id).first()
    if not target:
        return RedirectResponse("/hymns", status_code=303)
    db.query(HymnSetModel).update({HymnSetModel.is_active: False})
    target.is_active = True
    from datetime import datetime, timezone
    target.last_used = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(f"/hymns?set={set_id}", status_code=303)


@router.post("/hymn-sets/{set_id}/rename")
def rename_hymn_set(
    set_id: int, name: str = Form(""), db: Session = Depends(get_db)
):
    target = db.query(HymnSetModel).filter(HymnSetModel.id == set_id).first()
    if not target:
        return Response("Set not found", status_code=404)
    name = name.strip()
    if not name:
        return Response("Set name cannot be empty.", status_code=400)
    target.name = name
    touch_set(db, set_id)
    db.commit()
    return Response(status_code=200)


@router.post("/hymn-sets/{set_id}/clone")
def clone_hymn_set(set_id: int, db: Session = Depends(get_db)):
    source = db.query(HymnSetModel).filter(HymnSetModel.id == set_id).first()
    if not source:
        return RedirectResponse("/hymns", status_code=303)
    copy = HymnSetModel(name=f"{source.name} (Copy)", is_active=False)
    db.add(copy)
    db.flush()
    for item in set_plan_query(db, source.id).all():
        db.add(ServicePlanHymnModel(
            set_id=copy.id, sequence=item.sequence, hymn_id=item.hymn_id
        ))
    db.commit()
    return RedirectResponse(f"/hymns?set={copy.id}", status_code=303)


@router.post("/hymn-sets/{set_id}/delete")
def delete_hymn_set(set_id: int, db: Session = Depends(get_db)):
    target = db.query(HymnSetModel).filter(HymnSetModel.id == set_id).first()
    if target:
        db.delete(target)  # cascades to its plan rows
        db.commit()
        get_active_set(db)  # self-heal: ensure some set exists and is active
    return RedirectResponse("/hymns", status_code=303)


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

@router.get("/editor", response_class=HTMLResponse)
def editor_dashboard(request: Request, db: Session = Depends(get_db)):
    hymns = db.query(HymnModel).order_by(*_hymn_order).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "editor.html", {"request": request, "hymns": hymns}
    )


@router.get("/hymns/form", response_class=HTMLResponse)
def get_empty_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/hymn_form.html", {"request": request, "hymn": None}
    )


@router.get("/hymns/{hymn_id}/form", response_class=HTMLResponse)
def get_edit_form(hymn_id: int, request: Request, db: Session = Depends(get_db)):
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if hymn:
        hymn.slides.sort(key=lambda x: x.order)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/hymn_form.html", {"request": request, "hymn": hymn}
    )


@router.post("/hymns/save")
def save_hymn(
    request: Request,
    hymn_id: int = Form(None),
    number: str = Form(...),
    title: str = Form(...),
    vmix_labels: list[str] = Form(default=[]),
    vmix_contents: list[str] = Form(default=[]),
    ppt_labels: list[str] = Form(default=[]),
    ppt_contents: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    is_new = hymn_id is None
    if hymn_id:
        hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
        if not hymn:
            return JSONResponse({"detail": "Hymn not found"}, status_code=404)
        hymn.number = number
        hymn.title = title
        db.query(SlideModel).filter(SlideModel.hymn_id == hymn_id).delete()
    else:
        hymn = HymnModel(number=number, title=title)
        db.add(hymn)
        db.commit()
        db.refresh(hymn)

    for i, (lbl, content) in enumerate(zip(vmix_labels, vmix_contents)):
        db.add(
            SlideModel(
                hymn_id=hymn.id, label=lbl, content=content, order=i, type="VMIX"
            )
        )
    for i, (lbl, content) in enumerate(zip(ppt_labels, ppt_contents)):
        db.add(
            SlideModel(
                hymn_id=hymn.id, label=lbl, content=content, order=i, type="PPT"
            )
        )

    db.commit()

    # AJAX request — stay on the editor, return JSON
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse(
            {"ok": True, "hymn_id": hymn.id, "is_new": is_new}
        )

    return RedirectResponse(url="/editor", status_code=303)


@router.delete("/hymns/{hymn_id}")
def delete_hymn(hymn_id: int, request: Request, db: Session = Depends(get_db)):
    db.query(ServicePlanHymnModel).filter(
        ServicePlanHymnModel.hymn_id == hymn_id
    ).delete()

    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if hymn:
        db.delete(hymn)
        db.commit()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/hymn_deleted.html",
        {"request": request},
        headers={"HX-Trigger": "refreshLibrary"},
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _search_hymns(db: Session, q: str):
    """Shared search query for both library and editor contexts."""
    query = db.query(HymnModel).outerjoin(SlideModel)
    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                HymnModel.number.ilike(search),
                HymnModel.title.ilike(search),
                SlideModel.content.ilike(search),
            )
        )
    return query.distinct().order_by(*_hymn_order).all()


@router.get("/library/search", response_class=HTMLResponse)
def search_library(
    request: Request,
    q: str = "",
    set: Optional[int] = None,
    db: Session = Depends(get_db),
):
    hymns = _search_hymns(db, q)
    current_set = get_set_or_active(db, set)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/library_list.html",
        {"request": request, "library": hymns, "current_set": current_set},
    )


@router.get("/editor/search", response_class=HTMLResponse)
def search_editor_library(
    request: Request, q: str = "", db: Session = Depends(get_db)
):
    hymns = _search_hymns(db, q)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/editor_list.html", {"request": request, "hymns": hymns}
    )


# ---------------------------------------------------------------------------
# Hymn preview
# ---------------------------------------------------------------------------

@router.get("/hymns/{hymn_id}/preview", response_class=HTMLResponse)
def preview_hymn(hymn_id: int, request: Request, db: Session = Depends(get_db)):
    hymn = db.query(HymnModel).filter(HymnModel.id == hymn_id).first()
    if not hymn:
        return HTMLResponse("<div>Hymn not found</div>")

    vmix_slides = get_slides_by_type(hymn, preferred_type="VMIX")
    ppt_slides = get_slides_by_type(hymn, preferred_type="PPT")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/hymn_preview.html",
        {
            "request": request,
            "hymn": hymn,
            "vmix_slides": vmix_slides,
            "ppt_slides": ppt_slides,
        },
    )


# ---------------------------------------------------------------------------
# PPT download (hymn service plan)
# ---------------------------------------------------------------------------

@router.get("/download/ppt")
def download_ppt(
    aspect: str = "4:3",
    font_select: str = "Arial",
    font_manual: str = "",
    title_size: int = 80,
    lyrics_size: int = 60,
    bg_color: str = "#000000",
    text_color: str = "#FFFFFF",
    set_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    target_set = get_set_or_active(db, set_id)
    plan = set_plan_query(db, target_set.id).all()
    if not plan:
        return Response("This hymn set is empty", status_code=400)

    cfg = PptxConfig(
        font_select=font_select,
        font_manual=font_manual,
        title_size=title_size,
        lyrics_size=lyrics_size,
        bg_color=bg_color,
        text_color=text_color,
    )
    try:
        output = generate_hymn_plan_pptx(plan, aspect=aspect, config=cfg)
    except Exception as exc:
        return Response(f"Failed to generate PowerPoint: {exc}", status_code=500)

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _re.sub(r"[^A-Za-z0-9_-]+", "_", target_set.name or "").strip("_")
    filename = f"{safe_name or 'Hymns'}_{aspect.replace(':', '')}_{ts}.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
