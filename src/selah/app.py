"""Selah — church service management. Application entry point."""

import logging
import logging.handlers
import os
import sys

from paths import is_frozen, log_dir


def _setup_logging():
    """Console logging in dev; rotating file logging in the installed app
    (which runs windowed, with no console attached)."""
    if not is_frozen():
        logging.basicConfig(level=logging.INFO)
        return

    # Windowed PyInstaller apps may have no usable std streams
    devnull = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = devnull
    if sys.stderr is None:
        sys.stderr = devnull

    handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir(), "app.log"),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


_setup_logging()

from services import logbuffer
logbuffer.install()

import uvicorn

from config import settings
from factory import create_app
from services import updater

app = create_app()

if __name__ == "__main__":
    updater.start_background_checks()
    # log_config=None keeps uvicorn from installing stream handlers that break
    # in the windowed build; its loggers propagate to our root handler instead.
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_config=None if is_frozen() else uvicorn.config.LOGGING_CONFIG,
    )
