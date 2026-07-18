"""Start-on-boot management via the per-user Windows Run registry key.

The installer offers the same option as a setup task; this module lets the
user flip it at runtime from the Settings page. Both write the identical
HKCU value, so they stay in sync.
"""

import logging
import os
import sys

from paths import is_frozen

logger = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "vMixChurchServiceManager"


def is_supported() -> bool:
    """Autostart only makes sense for the installed exe on Windows."""
    return sys.platform == "win32" and is_frozen()


def _command() -> str:
    return f'"{sys.executable}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Enable/disable autostart. Returns the resulting state."""
    if not is_supported():
        raise RuntimeError(
            "Autostart is only available in the installed Windows application."
        )
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            logger.info("Autostart enabled: %s", _command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
                logger.info("Autostart disabled")
            except FileNotFoundError:
                pass
    return is_enabled()
