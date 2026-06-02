"""Rutas de datos: separa lo EMPAQUETADO (solo lectura) de lo del USUARIO (escribible).

En el ejecutable de PyInstaller, el código y los perfiles de ejemplo viven dentro de
`_internal/` (se sobrescribe al actualizar y no es donde el usuario guarda cosas). Los
datos que el usuario crea —perfiles calibrados, assets (iconos/embeddings/templates) y
config— deben vivir FUERA del bundle, junto al `.exe`. Aquí se centralizan esas rutas.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def data_dir() -> Path:
    """Directorio escribible de datos del usuario.

    - Ejecutable: la carpeta donde está el `.exe` (junto a `_internal/`).
    - Desarrollo: la raíz del proyecto.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
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
