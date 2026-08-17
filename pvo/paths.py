"""Rutas de datos del agente.

La config (y el log) se guardan en la carpeta de datos del **sistema operativo**
(`%APPDATA%\\poke-overlay`, `~/.local/share/poke-overlay`…), no dentro de la carpeta
del ejecutable, para que **sobrevivan a las actualizaciones** de la app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "poke-overlay"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _os_data_root() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def data_dir() -> Path:
    """Directorio escribible del usuario (raíz del repo en desarrollo)."""
    if is_frozen():
        d = _os_data_root() / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return data_dir() / "config.yaml"


def log_path() -> Path:
    return data_dir() / "agent.log"
