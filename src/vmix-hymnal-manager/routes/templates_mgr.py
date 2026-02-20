"""Presentation template management routes."""

import os
import shutil

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import PresentationTemplateModel
from utils import sanitize_filename

router = APIRouter()


@router.get("/templates_manager", response_class=HTMLResponse)
def page_templates(request: Request, db: Session = Depends(get_db)):
    tmpls = db.query(PresentationTemplateModel).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "templates_manager.html", {"request": request, "templates": tmpls}
    )


@router.post("/templates/upload")
def upload_template(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    safe_name = sanitize_filename(file.filename)
    file_location = os.path.join(settings.UPLOAD_DIR, safe_name)

    with open(file_location, "wb+") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_tmpl = PresentationTemplateModel(name=name, filename=safe_name)
    db.add(new_tmpl)
    db.commit()

    return RedirectResponse("/templates_manager", status_code=303)


@router.delete("/templates/{id}")
def delete_template(id: int, db: Session = Depends(get_db)):
    tmpl = (
        db.query(PresentationTemplateModel)
        .filter(PresentationTemplateModel.id == id)
        .first()
    )
    if tmpl:
        try:
            os.remove(os.path.join(settings.UPLOAD_DIR, tmpl.filename))
        except FileNotFoundError:
            pass
        db.delete(tmpl)
        db.commit()
    return Response(status_code=200)
