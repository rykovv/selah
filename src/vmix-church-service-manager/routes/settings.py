"""Application settings — storage paths, autostart, and updates."""

import os
import sqlite3
import threading

from fastapi import APIRouter, Body, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from config import settings
from config_file import config_path, set_config
from database import get_schema_version, init_db_at
from services import autostart, updater

router = APIRouter()


def _upsert_default_db(key: str, value: str):
    """Write a setting to the default (bootstrap) database using raw SQLite."""
    conn = sqlite3.connect(settings.DEFAULT_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def _read_default_db(key: str):
    """Read a setting from the default database using raw SQLite."""
    try:
        conn = sqlite3.connect(settings.DEFAULT_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _pick_path(mode: str, title: str, filetypes=None):
    """Open a native OS file/folder dialog in a dedicated Tk thread."""
    result = {}

    def _run():
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        if mode == "file":
            path = filedialog.askopenfilename(
                title=title,
                filetypes=filetypes or [("SQLite Database", "*.db"), ("All Files", "*.*")],
            )
        else:
            path = filedialog.askdirectory(title=title)

        root.destroy()
        result["path"] = path or ""

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=120)
    return result.get("path", "")


@router.get("/settings/pick_db")
def pick_db_path():
    """Open native file dialog to pick database file location."""
    path = _pick_path("file", "Choose Database Location")
    return JSONResponse({"path": path})


@router.get("/settings/pick_upload")
def pick_upload_dir():
    """Open native folder dialog to pick templates folder."""
    path = _pick_path("folder", "Choose Templates Folder")
    return JSONResponse({"path": path})


# ---------------------------------------------------------------------------
# Autostart (start on Windows boot)
# ---------------------------------------------------------------------------

@router.get("/api/autostart")
def get_autostart():
    return JSONResponse({
        "supported": autostart.is_supported(),
        "enabled": autostart.is_enabled(),
    })


@router.post("/api/autostart")
def set_autostart(data: dict = Body(...)):
    try:
        enabled = autostart.set_enabled(bool(data.get("enabled")))
    except RuntimeError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return JSONResponse({"supported": True, "enabled": enabled})


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------

@router.get("/api/update/status")
def update_status():
    return JSONResponse(updater.get_state())


@router.post("/api/update/check")
def update_check():
    return JSONResponse(updater.check_for_update())


@router.post("/api/update/install")
def update_install():
    state = updater.install_update()
    code = 400 if state["status"] == "error" else 200
    return JSONResponse(state, status_code=code)


# /docs is taken by FastAPI's built-in Swagger UI
@router.get("/documentation", response_class=HTMLResponse)
def page_documentation(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("documentation.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
def page_settings(request: Request):
    current_db = _read_default_db("db_path") or settings.DEFAULT_DB_PATH
    current_upload = _read_default_db("upload_dir") or settings.UPLOAD_DIR

    # Resolve actual DB path for schema version display
    actual_db = current_db
    schema_ver = get_schema_version(os.path.abspath(actual_db))

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "db_path": os.path.abspath(current_db),
            "upload_dir": os.path.abspath(current_upload),
            "needs_setup": settings.needs_setup,
            "schema_version": schema_ver,
            "config_file": config_path(),
        },
    )


@router.post("/settings/paths", response_class=HTMLResponse)
def save_paths(
    request: Request,
    db_path: str = Form(...),
    upload_dir: str = Form(...),
):
    db_path = db_path.strip()
    upload_dir = upload_dir.strip()
    messages = []
    restart_needed = False

    # --- Validate paths ---
    if not db_path:
        return Response("Database path cannot be empty.", status_code=400)
    if not upload_dir:
        return Response("Templates folder path cannot be empty.", status_code=400)

    # Ensure parent directory of DB path exists
    db_parent = os.path.dirname(os.path.abspath(db_path))
    if not os.path.isdir(db_parent):
        return Response(
            f"Directory does not exist: {db_parent}", status_code=400
        )

    # --- Handle templates path ---
    old_upload = _read_default_db("upload_dir") or settings.UPLOAD_DIR
    if os.path.abspath(upload_dir) != os.path.abspath(old_upload):
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except OSError as exc:
            return Response(
                f"Cannot create templates folder: {exc}", status_code=400
            )
        settings.UPLOAD_DIR = upload_dir
        messages.append("Templates folder updated.")

    _upsert_default_db("upload_dir", upload_dir)
    set_config("upload_dir", upload_dir)

    # --- Handle database path ---
    old_db = _read_default_db("db_path") or settings.DEFAULT_DB_PATH
    if os.path.abspath(db_path) != os.path.abspath(old_db):
        if not os.path.exists(db_path):
            init_db_at(db_path)
            messages.append("New database created.")
        restart_needed = True
        messages.append("Restart the app to use the new database.")

    _upsert_default_db("db_path", db_path)
    set_config("db_path", db_path)

    # Clear needs_setup flag so redirect middleware stops
    settings.needs_setup = False

    if restart_needed:
        return Response(
            " ".join(messages) + " Please restart the application.",
            status_code=200,
        )
    return Response(" ".join(messages) or "Settings saved.", status_code=200)
