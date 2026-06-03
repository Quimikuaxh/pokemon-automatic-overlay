"""Rutas de datos: separa lo EMPAQUETADO (solo lectura) de lo del USUARIO (escribible).

Los datos del usuario (perfiles calibrados, assets, config) se guardan en la carpeta
de datos del SISTEMA OPERATIVO (p. ej. %APPDATA%\\poke-overlay en Windows), NO dentro
de la carpeta del ejecutable. Así **sobreviven a actualizaciones**: aunque sobrescribas
o borres la carpeta de la app, tu config y tus perfiles siguen ahí.

Al primer arranque se "siembran" (copian) las galerías de iconos y los perfiles de
ejemplo empaquetados a esa carpeta del usuario, sin pisar lo que el usuario ya tenga.
"""

from __future__ import annotations

import os
import shutil
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
    """Directorio escribible de datos del usuario, persistente entre actualizaciones.

    - Ejecutable: carpeta de datos del SO (`%APPDATA%/poke-overlay`, `~/.local/share/…`).
    - Desarrollo: raíz del proyecto.
    """
    if is_frozen():
        return _os_data_root() / APP_NAME
    return Path(__file__).resolve().parent.parent


def profiles_dir() -> Path:
    d = data_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir() -> Path:
    d = data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.yaml"


def bundled_profiles_dir() -> Path:
    """Perfiles de ejemplo incluidos en el paquete (solo lectura)."""
    return Path(__file__).resolve().parent / "profiles"


def bundled_assets_dir() -> Path:
    """Assets empaquetados (galerías de iconos, templates) — solo lectura."""
    return Path(__file__).resolve().parent.parent / "assets"


def ensure_seeded() -> None:
    """Copia ejemplos y galerías empaquetadas a la carpeta del usuario si faltan.

    Solo actúa en el ejecutable (en desarrollo los datos ya están en el repo). Nunca
    sobrescribe ficheros existentes del usuario."""
    if not is_frozen():
        return

    dst_p = profiles_dir()
    for f in bundled_profiles_dir().glob("*.yaml"):
        target = dst_p / f.name
        if not target.exists():
            shutil.copy2(f, target)

    src_a = bundled_assets_dir()
    if src_a.exists():
        dst_a = assets_dir()
        for sub in src_a.rglob("*"):
            if sub.is_file():
                target = dst_a / sub.relative_to(src_a)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sub, target)
