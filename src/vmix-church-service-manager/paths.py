"""Windows-conventional file locations.

Installed (frozen) layout follows platform standards:
  static  : the install directory (managed by the installer, treated read-only)
  data    : %APPDATA%\\vMix Church Service Manager  -> config.json, hymns.db, templates/
  logs    : %LOCALAPPDATA%\\vMix Church Service Manager\\logs

Development keeps everything in the source directory, as before.
"""

import os
import shutil
import sys

APP_DIR_NAME = "vMix Church Service Manager"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> str:
    """Directory holding the executable (frozen) or the source tree (dev)."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Directory for dynamic user data (database, uploads, config)."""
    if is_frozen():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_DIR_NAME)
    else:
        path = install_dir()
    os.makedirs(path, exist_ok=True)
    return path


def log_dir() -> str:
    """Directory for log files (machine-local, not worth roaming)."""
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_DIR_NAME, "logs")
    else:
        path = os.path.join(install_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def migrate_legacy_layout():
    """Copy data from the old portable layout (files next to the exe) into
    the appdata directory, once. Runs only when frozen and only if the new
    location has no config/database yet."""
    if not is_frozen():
        return

    src = install_dir()
    dst = data_dir()
    if src == dst:
        return

    markers = ("config.json", "hymns.db")
    if any(os.path.exists(os.path.join(dst, m)) for m in markers):
        return  # already populated

    for name in markers:
        old = os.path.join(src, name)
        if os.path.exists(old):
            try:
                shutil.copy2(old, os.path.join(dst, name))
            except OSError:
                pass

    old_templates = os.path.join(src, "templates")
    new_templates = os.path.join(dst, "templates")
    # The frozen app's Jinja templates live in _internal/templates; a root-level
    # templates dir next to the exe is the old uploads folder.
    if os.path.isdir(old_templates) and not os.path.isdir(new_templates):
        try:
            shutil.copytree(old_templates, new_templates)
        except OSError:
            pass
