"""Auto-update via GitHub releases.

Flow (matches the Inno Setup installer):
1. Poll the GitHub releases API for the latest release tag.
2. Compare against the running APP_VERSION.
3. On demand, download the release's ``*setup*.exe`` asset to %TEMP% and
   launch it with silent flags; the app exits and the installer relaunches
   the new version via the /RELAUNCH=1 parameter.

Checks run in daemon threads so startup is never blocked; state is kept in
memory and exposed through /api/update/* endpoints.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from config import settings
from paths import is_frozen

logger = logging.getLogger(__name__)

API_LATEST = f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases/latest"
CHECK_INTERVAL = 24 * 3600  # daily
STARTUP_DELAY = 10          # let the server come up first

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | checking | up_to_date | update_available | downloading | installing | error
    "current_version": settings.APP_VERSION,
    "latest_version": None,
    "notes": "",
    "asset_url": None,
    "asset_name": None,
    "error": None,
    "checked_at": None,
    "supported": is_frozen(),  # installing only works for the installed app
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def _set(**kwargs):
    with _lock:
        _state.update(kwargs)


def _version_tuple(v: str):
    """'v1.2.3' / '1.2.3-beta' -> (1, 2, 3). Non-numeric parts are stripped."""
    v = v.strip().lstrip("vV")
    parts = re.split(r"[.\-+]", v)
    nums = []
    for p in parts[:3]:
        m = re.match(r"\d+", p)
        if not m:
            break
        nums.append(int(m.group()))
    return tuple(nums) if nums else (0,)


def _fetch_latest_release() -> dict:
    req = urllib.request.Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"selah/{settings.APP_VERSION}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update() -> dict:
    """Query GitHub and update state. Safe to call from any thread."""
    _set(status="checking", error=None)
    try:
        release = _fetch_latest_release()
    except Exception as exc:
        logger.warning("Update check failed: %s", exc)
        _set(status="error", error=f"Update check failed: {exc}",
             checked_at=time.time())
        return get_state()

    tag = release.get("tag_name") or ""
    latest = _version_tuple(tag)
    current = _version_tuple(settings.APP_VERSION)

    asset_url = None
    asset_name = None
    for asset in release.get("assets", []):
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "setup" in name:
            asset_url = asset.get("browser_download_url")
            asset_name = asset.get("name")
            break

    if latest > current and asset_url:
        _set(
            status="update_available",
            latest_version=tag.lstrip("vV"),
            notes=(release.get("body") or "")[:2000],
            asset_url=asset_url,
            asset_name=asset_name,
            checked_at=time.time(),
        )
        logger.info("Update available: %s -> %s", settings.APP_VERSION, tag)
    elif latest > current:
        _set(status="error", latest_version=tag.lstrip("vV"),
             error="A newer release exists but has no setup .exe asset.",
             checked_at=time.time())
    else:
        _set(status="up_to_date", latest_version=tag.lstrip("vV") or None,
             checked_at=time.time())
    return get_state()


def _download_and_install():
    state = get_state()
    url = state["asset_url"]
    name = state["asset_name"] or "selah-setup.exe"
    target = os.path.join(tempfile.gettempdir(), name)

    _set(status="downloading")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"selah/{settings.APP_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:
        logger.error("Update download failed: %s", exc)
        _set(status="error", error=f"Download failed: {exc}")
        return

    if os.path.getsize(target) < 1024 * 1024:  # sanity: an installer is > 1 MB
        _set(status="error", error="Downloaded installer looks truncated.")
        return

    _set(status="installing")
    logger.info("Launching installer: %s", target)
    try:
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [target, "/VERYSILENT", "/NORESTART", "/SP-",
             "/FORCECLOSEAPPLICATIONS", "/RELAUNCH=1"],
            close_fds=True,
            creationflags=DETACHED_PROCESS,
        )
    except Exception as exc:
        logger.error("Could not launch installer: %s", exc)
        _set(status="error", error=f"Could not launch installer: {exc}")
        return

    # Give the response time to reach the browser, then exit so the
    # installer can replace our files.
    time.sleep(1.5)
    logger.info("Exiting for update to %s", state["latest_version"])
    os._exit(0)


def install_update() -> dict:
    """Start download + silent install in the background. The app will exit."""
    state = get_state()
    if not state["supported"]:
        _set(status="error",
             error="In-app updating only works in the installed application.")
    elif state["status"] != "update_available" or not state["asset_url"]:
        _set(status="error", error="No update is ready to install.")
    else:
        threading.Thread(target=_download_and_install, daemon=True).start()
    return get_state()


def start_background_checks():
    """Periodic update checks (installed app only)."""
    if not is_frozen():
        return

    def _loop():
        time.sleep(STARTUP_DELAY)
        while True:
            try:
                check_for_update()
            except Exception:
                logger.exception("Background update check crashed")
            time.sleep(CHECK_INTERVAL)

    threading.Thread(target=_loop, daemon=True).start()
