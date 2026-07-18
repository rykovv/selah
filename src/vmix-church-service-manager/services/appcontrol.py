"""Restart and shutdown of the running application, triggered from the UI.

Restart works by spawning a detached helper (cmd) that waits ~2 seconds for
this process to exit and release the port, then launches a fresh instance.
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
import time

from paths import is_frozen

logger = logging.getLogger(__name__)

_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def _exit_soon(delay: float = 1.0):
    """Exit after the HTTP response has had time to reach the browser."""

    def _die():
        time.sleep(delay)
        logger.info("Exiting on user request")
        os._exit(0)

    threading.Thread(target=_die, daemon=True).start()


def shutdown():
    logger.info("Shutdown requested from UI")
    _exit_soon()


def _relaunch_command() -> str:
    """Command line that starts a new instance of the current process."""
    if is_frozen():
        return f'start "" "{sys.executable}"'
    argv = list(sys.argv)
    if argv and os.path.basename(argv[0]) == "__main__.py":
        # `python -m pkg` sets argv[0] to pkg/__main__.py; running that file
        # by path would shadow stdlib modules with the package's own — rebuild
        # the -m invocation instead.
        pkg = os.path.basename(os.path.dirname(argv[0]))
        argv = ["-m", pkg] + argv[1:]
    args = " ".join(f'"{a}"' for a in [sys.executable] + argv)
    return f'start "" {args}'


def restart():
    logger.info("Restart requested from UI")
    # A .bat helper sidesteps cmd /c nested-quoting problems. It waits ~2s
    # (ping needs no console input, unlike `timeout`) for this process to
    # exit and free the port, relaunches, then deletes itself.
    fd, bat = tempfile.mkstemp(prefix="vmix-csm-restart-", suffix=".bat")
    with os.fdopen(fd, "w", encoding="ascii", errors="replace") as f:
        f.write(
            "@echo off\r\n"
            "ping -n 3 127.0.0.1 >nul\r\n"
            f"cd /d \"{os.getcwd()}\"\r\n"
            f"{_relaunch_command()}\r\n"
            "del \"%~f0\"\r\n"
        )
    subprocess.Popen(
        ["cmd", "/c", bat],
        close_fds=True,
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW,
    )
    _exit_soon()
