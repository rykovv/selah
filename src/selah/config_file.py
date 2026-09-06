"""Persistent config file for the application.

Stores database and template paths so the app can find them on any machine,
even before the bootstrap database exists.

Location: %APPDATA%\\Selah (frozen — survives updates
that replace the install directory) or the source directory (dev).
"""

import json
import logging
import os

from paths import data_dir

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "config.json"


def config_path() -> str:
    """Full path to the config JSON file."""
    return os.path.join(data_dir(), _CONFIG_FILENAME)


def read_config() -> dict:
    """Read the config file. Returns empty dict if missing or invalid."""
    fp = config_path()
    if not os.path.exists(fp):
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        logger.warning("Could not read config file %s", fp)
        return {}


def write_config(data: dict):
    """Write the full config dict to disk."""
    fp = config_path()
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Config saved to %s", fp)
    except Exception:
        logger.error("Failed to write config file %s", fp)


def get_config(key: str, default=None):
    """Read a single key from the config file."""
    return read_config().get(key, default)


def set_config(key: str, value: str):
    """Set a single key in the config file (merge with existing)."""
    data = read_config()
    data[key] = value
    write_config(data)
