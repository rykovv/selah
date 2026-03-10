"""Service program CRUD, items, reorder, activate, and PPT download."""

import os
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    PresentationTemplateModel,
    ServiceProgramItemModel,
    ServiceProgramModel,
)
from services.pptx_service import PptxConfig, generate_program_pptx
from utils import sort_program_items

router = APIRouter()


# ---------------------------------------------------------------------------
# Program CRUD
# ---------------------------------------------------------------------------

@router.get("/programs", response_class=HTMLResponse)
def page_programs(request: Request, db: Session = Depends(get_db)):
    programs = (
        db.query(ServiceProgramModel)
        .order_by(ServiceProgramModel.last_used.desc(), ServiceProgramModel.id.desc())
        .all()
    )
    for prog in programs:
        prog.items = sort_program_items(prog.items)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "programs.html", {"request": request, "programs": programs}
    )


@router.post("/programs/new")
def new_program(db: Session = Depends(get_db)):
    new_prog = ServiceProgramModel(
        name="New Service Program",
        is_active=False,
        last_used=datetime.now(timezone.utc),
    )
    db.add(new_prog)
    db.commit()
    db.refresh(new_prog)
    return RedirectResponse(f"/programs/{new_prog.id}", status_code=303)


@router.get("/programs/{id}", response_class=HTMLResponse)
def program_editor_page(id: int, request: Request, db: Session = Depends(get_db)):
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if not prog:
        return RedirectResponse("/programs")

    prog.items = sort_program_items(prog.items)
    all_templates = db.query(PresentationTemplateModel).all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "program_editor.html",
        {"request": request, "program": prog, "templates": all_templates},
    )


@router.delete("/programs/{id}")
def delete_program(id: int, db: Session = Depends(get_db)):
    db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).delete()
    db.commit()
    return RedirectResponse("/programs", status_code=303)


@router.get("/programs/{id}/edit", response_class=HTMLResponse)
def edit_program(id: int, request: Request, db: Session = Depends(get_db)):
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if not prog:
        return Response("Program not found", status_code=404)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/program_editor.html", {"request": request, "program": prog}
    )


@router.post("/programs/{id}/update_meta")
def update_program_meta(
    id: int,
    name: str = Form(...),
    template_id: int = Form(None),
    db: Session = Depends(get_db),
):
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if not prog:
        return Response("Program not found", status_code=404)
    prog.name = name
    prog.template_id = template_id
    db.commit()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Program items
# ---------------------------------------------------------------------------

@router.post("/programs/{id}/add_item")
def add_program_item(id: int, request: Request, db: Session = Depends(get_db)):
    prog = db.query(ServiceProgramModel).filter(ServiceProgramModel.id == id).first()
    if not prog:
        return Response("Program not found", status_code=404)
    new_item = ServiceProgramItemModel(
        program_id=id, title="", subtitle="", sequence=999
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/program_row.html", {"request": request, "item": new_item}
    )


@router.post("/programs/item/{item_id}/update")
def update_item(
    item_id: int,
    title: str = Form(""),
    subtitle: str = Form(""),
    tag: str = Form(""),
    db: Session = Depends(get_db),
):
    item = (
        db.query(ServiceProgramItemModel)
        .filter(ServiceProgramItemModel.id == item_id)
        .first()
    )
    if not item:
        return Response("Item not found", status_code=404)
    item.title = title
    item.subtitle = subtitle
    item.tag = tag
    db.commit()
    return Response(status_code=200)


@router.delete("/programs/item/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db.query(ServiceProgramItemModel).filter(
        ServiceProgramItemModel.id == item_id
    ).delete()
    db.commit()
    return Response(status_code=200)


@router.post("/programs/item/{item_id}/toggle_mute")
def toggle_item_mute(
    item_id: int, request: Request, db: Session = Depends(get_db)
):
    item = (
        db.query(ServiceProgramItemModel)
        .filter(ServiceProgramItemModel.id == item_id)
        .first()
    )
    if item:
        item.is_muted = not item.is_muted
        db.commit()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/program_row.html", {"request": request, "item": item}
    )


# ---------------------------------------------------------------------------
# Activate & reorder
# ---------------------------------------------------------------------------

@router.post("/programs/{id}/activate")
def activate_program(id: int, request: Request, db: Session = Depends(get_db)):
    db.query(ServiceProgramModel).update({ServiceProgramModel.is_active: False})
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if prog:
        prog.is_active = True
        prog.last_used = datetime.now(timezone.utc)
        db.commit()

    programs = (
        db.query(ServiceProgramModel)
        .order_by(ServiceProgramModel.id.desc())
        .all()
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/program_list.html", {"request": request, "programs": programs}
    )


@router.post("/programs/{id}/reorder")
def reorder_program_items(
    id: int,
    item_ids: List[int] = Form(...),
    db: Session = Depends(get_db),
):
    for index, item_id in enumerate(item_ids):
        item = (
            db.query(ServiceProgramItemModel)
            .filter(ServiceProgramItemModel.id == item_id)
            .first()
        )
        if item:
            item.sequence = index
    db.commit()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# PPT download
# ---------------------------------------------------------------------------

@router.get("/programs/{id}/download_ppt")
def download_program_ppt(
    id: int,
    font_select: str = "Arial",
    font_manual: str = None,
    title_size: int = 80,
    lyrics_size: int = 60,
    db: Session = Depends(get_db),
):
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    if not prog or not prog.template_id:
        return Response("No template assigned.", status_code=400)

    if not prog.items:
        return Response("Service program is empty — add items first.", status_code=400)

    template = (
        db.query(PresentationTemplateModel)
        .filter(PresentationTemplateModel.id == prog.template_id)
        .first()
    )
    if not template:
        return Response("Template file not found.", status_code=404)

    input_path = os.path.join(settings.UPLOAD_DIR, template.filename)
    if not os.path.exists(input_path):
        return Response("Template file missing on disk.", status_code=404)

    cfg = PptxConfig(
        font_select=font_select,
        font_manual=font_manual or "",
        title_size=title_size,
        lyrics_size=lyrics_size,
    )
    try:
        output = generate_program_pptx(prog, db, input_path, config=cfg)
    except Exception as exc:
        return Response(f"Failed to generate PowerPoint: {exc}", status_code=500)

    filename = f"{prog.name.replace(' ', '_')}.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
