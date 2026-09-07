"""Bible verse sets: manager page, entries, translations, feed, and PPT."""

import json
import re as _re
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse,
)
from sqlalchemy.orm import Session

from database import get_db
from models import BibleEntryModel, BibleRow, BibleSetModel
from services import bible_service
from services.bible_service import RefParseError, Translation
from services.bible_set_service import (
    get_active_set, get_set_or_active, set_entries_query, touch_set,
)
from services.pptx_service import PptxConfig, generate_bible_set_pptx

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_set_translation(current_set: BibleSetModel) -> Optional[Translation]:
    try:
        return bible_service.load_translation(current_set.translation)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


def _entry_views(db: Session, current_set: BibleSetModel,
                 translation: Optional[Translation]) -> List[dict]:
    """Resolve a set's entries for display (reference + verse text)."""
    views = []
    for e in set_entries_query(db, current_set.id).all():
        refs = bible_service.refs_from_json(e.refs_json)
        views.append({
            "id": e.id,
            "reference": bible_service.format_refs(refs, translation),
            "text": (
                bible_service.resolve_refs_text(refs, translation)
                if translation else ""
            ),
        })
    return views


def _entry_list_response(request: Request, db: Session,
                         current_set: BibleSetModel):
    """Render the entry list partial (with out-of-band count badge)."""
    translation = _load_set_translation(current_set)
    entries = _entry_views(db, current_set, translation)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/bible_entry_list.html",
        {"request": request, "entries": entries, "oob": True},
    )


def _renumber_entries(db: Session, set_id: int):
    """Renumber one set's sequences to be contiguous (1, 2, 3, ...)."""
    items = set_entries_query(db, set_id).all()
    # Negative temporaries first — see routes/hymns.py _renumber_plan
    for i, item in enumerate(items, start=1):
        item.sequence = -i
    db.flush()
    for i, item in enumerate(items, start=1):
        item.sequence = i
    db.commit()


# ---------------------------------------------------------------------------
# Bible manager page
# ---------------------------------------------------------------------------

@router.get("/bible", response_class=HTMLResponse)
def page_bible_manager(
    request: Request,
    set: Optional[int] = None,
    created: Optional[int] = None,
    db: Session = Depends(get_db),
):
    current_set = get_set_or_active(db, set)
    sets = (
        db.query(BibleSetModel)
        .order_by(
            BibleSetModel.is_active.desc(),
            BibleSetModel.last_used.desc(),
            BibleSetModel.id.desc(),
        )
        .all()
    )
    translation = _load_set_translation(current_set)
    entries = _entry_views(db, current_set, translation)
    installed = bible_service.installed_translations()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "bible_manager.html",
        {
            "request": request,
            "sets": sets,
            "current_set": current_set,
            "entries": entries,
            "translation": translation,
            "installed": installed,
            "structure_json": json.dumps(
                translation.structure() if translation else {"books": []}
            ),
            "just_created": bool(created),
        },
    )


# ---------------------------------------------------------------------------
# Verse sets
# ---------------------------------------------------------------------------

@router.post("/bible-sets/new")
def new_bible_set(db: Session = Depends(get_db)):
    # New sets start on the translation the user works with most recently
    active = get_active_set(db)
    new_set = BibleSetModel(
        name="New Verse Set",
        translation=active.translation or bible_service.DEFAULT_TRANSLATION_ID,
        is_active=False,
    )
    db.add(new_set)
    db.commit()
    db.refresh(new_set)
    return RedirectResponse(
        f"/bible?set={new_set.id}&created=1", status_code=303
    )


@router.post("/bible-sets/{set_id}/activate")
def activate_bible_set(set_id: int, db: Session = Depends(get_db)):
    target = db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
    if not target:
        return RedirectResponse("/bible", status_code=303)
    db.query(BibleSetModel).update({BibleSetModel.is_active: False})
    target.is_active = True
    touch_set(db, set_id)
    db.commit()
    return RedirectResponse(f"/bible?set={set_id}", status_code=303)


@router.post("/bible-sets/{set_id}/rename")
def rename_bible_set(
    set_id: int, name: str = Form(""), db: Session = Depends(get_db)
):
    target = db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
    if not target:
        return Response("Set not found", status_code=404)
    name = name.strip()
    if not name:
        return Response("Set name cannot be empty.", status_code=400)
    target.name = name
    touch_set(db, set_id)
    db.commit()
    return Response(status_code=200)


@router.post("/bible-sets/{set_id}/translation")
def set_bible_translation(
    set_id: int, translation: str = Form(...), db: Session = Depends(get_db)
):
    target = db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
    if not target:
        return RedirectResponse("/bible", status_code=303)
    if not bible_service.is_installed(translation):
        return Response("Translation is not installed.", status_code=400)
    target.translation = translation
    touch_set(db, set_id)
    db.commit()
    return RedirectResponse(f"/bible?set={set_id}", status_code=303)


@router.post("/bible-sets/{set_id}/clone")
def clone_bible_set(set_id: int, db: Session = Depends(get_db)):
    source = db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
    if not source:
        return RedirectResponse("/bible", status_code=303)
    copy = BibleSetModel(
        name=f"{source.name} (Copy)",
        translation=source.translation,
        is_active=False,
    )
    db.add(copy)
    db.flush()
    for item in set_entries_query(db, source.id).all():
        db.add(BibleEntryModel(
            set_id=copy.id, sequence=item.sequence, refs_json=item.refs_json
        ))
    db.commit()
    return RedirectResponse(f"/bible?set={copy.id}", status_code=303)


@router.post("/bible-sets/{set_id}/delete")
def delete_bible_set(set_id: int, db: Session = Depends(get_db)):
    target = db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
    if target:
        db.delete(target)  # cascades to its entries
        db.commit()
        get_active_set(db)  # self-heal: ensure some set exists and is active
    return RedirectResponse("/bible", status_code=303)


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------

@router.post("/bible/entries/save")
def save_bible_entry(
    request: Request,
    set_id: int = Form(...),
    refs: str = Form(""),
    entry_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Add or update entries from reference text.

    "!"-separated groups each become their own entry. When editing, the
    edited entry takes the first group and any further groups are inserted
    right after it (splitting an entry in place).
    """
    current_set = get_set_or_active(db, set_id)
    translation = _load_set_translation(current_set)
    if not translation:
        return Response(
            "The set's translation is not installed.", status_code=400
        )
    try:
        groups = bible_service.parse_entry_groups(refs, translation)
    except RefParseError as exc:
        return Response(str(exc), status_code=400)

    last = (
        set_entries_query(db, current_set.id)
        .order_by(None)
        .order_by(BibleEntryModel.sequence.desc())
        .first()
    )
    next_seq = (last.sequence + 1) if last else 1

    if entry_id:
        entry = (
            db.query(BibleEntryModel)
            .filter(
                BibleEntryModel.id == entry_id,
                BibleEntryModel.set_id == current_set.id,
            )
            .first()
        )
        if not entry:
            return Response("Entry not found", status_code=404)
        entry.refs_json = bible_service.refs_to_json(groups[0])
        extras = []
        for g in groups[1:]:
            extra = BibleEntryModel(
                set_id=current_set.id,
                sequence=next_seq,
                refs_json=bible_service.refs_to_json(g),
            )
            next_seq += 1
            extras.append(extra)
            db.add(extra)
        if extras:
            db.flush()
            # Move the new entries from the end to right after the edited one
            ordered = []
            for item in set_entries_query(db, current_set.id).all():
                if item in extras:
                    continue
                ordered.append(item)
                if item.id == entry.id:
                    ordered.extend(extras)
            for i, item in enumerate(ordered, start=1):
                item.sequence = -i
            db.flush()
            for i, item in enumerate(ordered, start=1):
                item.sequence = i
    else:
        for g in groups:
            db.add(BibleEntryModel(
                set_id=current_set.id,
                sequence=next_seq,
                refs_json=bible_service.refs_to_json(g),
            ))
            next_seq += 1
    touch_set(db, current_set.id)
    db.commit()
    return _entry_list_response(request, db, current_set)


@router.delete("/bible/entries/{entry_id}")
def delete_bible_entry(
    entry_id: int, request: Request, db: Session = Depends(get_db)
):
    entry = (
        db.query(BibleEntryModel)
        .filter(BibleEntryModel.id == entry_id)
        .first()
    )
    if entry:
        set_id = entry.set_id
        db.delete(entry)
        touch_set(db, set_id)
        db.commit()
        _renumber_entries(db, set_id)
        current_set = get_set_or_active(db, set_id)
    else:
        current_set = get_active_set(db)
    return _entry_list_response(request, db, current_set)


@router.put("/bible/entries/reorder")
def reorder_bible_entries(
    order: List[int] = Body(...), db: Session = Depends(get_db)
):
    """Accept a list of entry IDs in their new order."""
    items = (
        db.query(BibleEntryModel)
        .filter(BibleEntryModel.id.in_(order))
        .all()
    )
    lookup = {item.id: item for item in items}

    # Negative temporaries to avoid UNIQUE(set, sequence) collisions
    for i, item_id in enumerate(order):
        if item_id in lookup:
            lookup[item_id].sequence = -(i + 1)
    db.flush()
    for i, item_id in enumerate(order):
        if item_id in lookup:
            lookup[item_id].sequence = i + 1
    if items:
        touch_set(db, items[0].set_id)
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/bible/entries/{entry_id}/refs")
def get_entry_refs(entry_id: int, db: Session = Depends(get_db)):
    """Raw reference text of one entry, for loading into the builder."""
    entry = (
        db.query(BibleEntryModel)
        .filter(BibleEntryModel.id == entry_id)
        .first()
    )
    if not entry:
        return JSONResponse({"detail": "Entry not found"}, status_code=404)
    current_set = get_set_or_active(db, entry.set_id)
    translation = _load_set_translation(current_set)
    refs = bible_service.refs_from_json(entry.refs_json)
    return {"id": entry.id, "refs": bible_service.format_refs(refs, translation)}


@router.get("/bible/preview")
def preview_refs(
    set_id: Optional[int] = None, refs: str = "", db: Session = Depends(get_db)
):
    """Live resolution of reference text while the user types.

    Returns one preview entry per "!"-separated group, mirroring exactly
    what saving would create.
    """
    current_set = get_set_or_active(db, set_id)
    translation = _load_set_translation(current_set)
    if not translation:
        return {"ok": False, "error": "The set's translation is not installed."}
    try:
        groups = bible_service.parse_entry_groups(refs, translation)
    except RefParseError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "entries": [
            {
                "reference": bible_service.format_refs(g, translation),
                "text": bible_service.resolve_refs_text(g, translation),
            }
            for g in groups
        ],
    }


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

def _translations_partial(request: Request):
    installed_ids = {t["id"]: t for t in bible_service.installed_translations()}
    languages = []
    for locale, versions in bible_service.catalog().items():
        entries = []
        for name in sorted(versions):
            tid = f"{locale}/{name}"
            local = installed_ids.get(tid)
            entries.append({
                "locale": locale,
                "name": name,
                "abbr": versions[name],
                "installed": local is not None,
                "bundled": bool(local and local["bundled"]),
            })
        languages.append({
            "locale": locale,
            "language": bible_service.LOCALE_NAMES.get(locale, locale),
            "translations": entries,
        })
    # English first, then alphabetical by language name
    languages.sort(key=lambda l: (l["locale"] != "en", l["language"]))
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/bible_translations.html",
        {"request": request, "languages": languages},
    )


@router.get("/bible/translations", response_class=HTMLResponse)
def list_translations(request: Request):
    return _translations_partial(request)


@router.post("/bible/translations/download", response_class=HTMLResponse)
def download_translation(
    request: Request, locale: str = Form(...), name: str = Form(...)
):
    try:
        bible_service.download_translation(locale, name)
    except Exception as exc:
        return Response(
            f"Download failed: {exc}", status_code=502
        )
    return _translations_partial(request)


@router.post("/bible/translations/remove", response_class=HTMLResponse)
def remove_translation(
    request: Request, locale: str = Form(...), name: str = Form(...)
):
    bible_service.delete_translation(f"{locale}/{name}")
    return _translations_partial(request)


# ---------------------------------------------------------------------------
# vMix feed
# ---------------------------------------------------------------------------

@router.get("/api/bible/service", response_model=List[BibleRow])
def get_bible_feed(db: Session = Depends(get_db)):
    """Flatten the active verse set into rows for vMix (one per entry)."""
    active_set = get_active_set(db)
    translation = _load_set_translation(active_set)
    label = ""
    if translation:
        label = translation.abbr or translation.name.title()
    rows = []
    for e in set_entries_query(db, active_set.id).all():
        refs = bible_service.refs_from_json(e.refs_json)
        rows.append(BibleRow(
            Reference=bible_service.format_refs(refs, translation),
            VerseText=(
                bible_service.resolve_refs_text(refs, translation)
                if translation else ""
            ),
            Translation=label,
        ))
    return rows


# ---------------------------------------------------------------------------
# PPT download
# ---------------------------------------------------------------------------

@router.get("/bible/download/ppt")
def download_bible_ppt(
    aspect: str = "4:3",
    font_select: str = "Arial",
    font_manual: str = "",
    verse_size: int = 54,
    ref_size: int = 32,
    bg_color: str = "#000000",
    text_color: str = "#FFFFFF",
    set_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    target_set = get_set_or_active(db, set_id)
    translation = _load_set_translation(target_set)
    if not translation:
        return Response(
            "The set's translation is not installed.", status_code=400
        )
    entries_blocks = []
    for e in set_entries_query(db, target_set.id).all():
        refs = bible_service.refs_from_json(e.refs_json)
        blocks = bible_service.resolve_refs_blocks(refs, translation)
        if blocks:
            entries_blocks.append(blocks)
    if not entries_blocks:
        return Response("This verse set is empty", status_code=400)

    cfg = PptxConfig(
        font_select=font_select,
        font_manual=font_manual,
        title_size=ref_size,     # reference lines/headers
        lyrics_size=verse_size,  # verse text
        bg_color=bg_color,
        text_color=text_color,
    )
    try:
        output = generate_bible_set_pptx(
            entries_blocks, aspect=aspect, config=cfg
        )
    except Exception as exc:
        return Response(f"Failed to generate PowerPoint: {exc}", status_code=500)

    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _re.sub(r"[^A-Za-z0-9_-]+", "_", target_set.name or "").strip("_")
    filename = f"{safe_name or 'Verses'}_{aspect.replace(':', '')}_{ts}.pptx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
