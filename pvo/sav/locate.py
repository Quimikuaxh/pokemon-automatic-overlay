"""Búsqueda automática de ficheros de partida guardada en las rutas habituales.

La interfaz vive en la web, así que el usuario no puede abrir un diálogo de ficheros
del sistema: es el agente quien propone los candidatos que encuentra en el equipo y la
web los lista para que elija uno.

Un candidato solo se propone si el contenido **se parsea de verdad** (no basta la
extensión), de modo que la lista que ve el usuario ya está verificada.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .container import SaveError, size_rank, unwrap
from .parsers import ordered_for

# Extensiones que usan los emuladores para la partida guardada. Sirven para acotar el
# rastreo; la validación final SIEMPRE es por contenido.
SAVE_SUFFIXES = {
    ".sav", ".srm", ".fla", ".flash", ".sa1", ".sa2", ".sgm",   # GBA
    ".dsv", ".duc",                                             # NDS
    "",                                                         # 3DS: fichero "main"
}

MAX_SIZE = 4 * 1024 * 1024
MAX_DEPTH = 6


def _home() -> Path:
    return Path.home()


def default_roots() -> list[Path]:
    """Carpetas donde los emuladores más usados guardan las partidas."""
    h = _home()
    roots: list[Path] = []
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA") or (h / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA") or (h / "AppData" / "Local"))
        roots += [
            appdata / "RetroArch" / "saves",
            appdata / "mGBA",
            appdata / "DeSmuME",
            appdata / "melonDS",
            appdata / "Citra" / "sdmc",
            appdata / "Azahar" / "sdmc",
            local / "Citra" / "sdmc",
            h / "Documents" / "Citra" / "sdmc",
            h / "Documents" / "Azahar" / "sdmc",
            h / "Documents" / "melonDS",
        ]
    elif sys.platform == "darwin":
        sup = h / "Library" / "Application Support"
        roots += [sup / "RetroArch" / "saves", sup / "mGBA", sup / "Citra" / "sdmc",
                  sup / "Azahar" / "sdmc", sup / "DeSmuME", sup / "melonDS"]
    else:
        share = Path(os.environ.get("XDG_DATA_HOME") or (h / ".local" / "share"))
        cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (h / ".config"))
        roots += [
            share / "retroarch" / "saves",
            cfg / "retroarch" / "saves",
            share / "mgba", cfg / "mgba",
            share / "desmume", cfg / "desmume",
            share / "melonDS", cfg / "melonDS",
            share / "citra-emu" / "sdmc",
            share / "azahar-emu" / "sdmc",
            h / ".var" / "app" / "org.libretro.RetroArch" / "config" / "retroarch" / "saves",
        ]
    roots += [h / "roms", h / "ROMs", h / "Games", h / "Emuladores"]
    return [r for r in roots if r.is_dir()]


@dataclass(frozen=True)
class Candidate:
    path: str
    size: int
    parser_key: str
    label: str
    team_count: int

    def as_dict(self) -> dict:
        return {
            "path": self.path, "size": self.size, "parserKey": self.parser_key,
            "label": self.label, "teamCount": self.team_count,
        }


def _iter_files(root: Path, max_depth: int) -> Iterable[Path]:
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).resolve().relative_to(root).parts)
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in SAVE_SUFFIXES or name == "main":
                yield p


def inspect(path: str | Path) -> Optional[Candidate]:
    """Devuelve el candidato si el fichero es una partida que sabemos leer."""
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size > MAX_SIZE:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    try:
        payload = unwrap(data, p.name).payload
    except SaveError:
        return None
    for parser in ordered_for(size_rank(payload)):
        slots = parser.parse(payload)
        if slots and any(slots):
            return Candidate(str(p), len(data), parser.key, parser.label,
                             sum(1 for s in slots if s))
    return None


def find_saves(roots: Optional[list[Path]] = None, limit: int = 50,
               max_depth: int = MAX_DEPTH) -> list[Candidate]:
    """Rastrea las rutas habituales y devuelve las partidas que se leen de verdad."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for root in (roots if roots is not None else default_roots()):
        for f in _iter_files(root, max_depth):
            key = str(f.resolve())
            if key in seen:
                continue
            seen.add(key)
            cand = inspect(f)
            if cand is not None:
                out.append(cand)
                if len(out) >= limit:
                    return out
    return out
