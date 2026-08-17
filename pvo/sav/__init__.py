"""Modo SAV: lee el equipo del **fichero de partida guardada** del emulador.

Es la alternativa a la lectura por memoria para las plataformas donde no hay API de
memoria (3DS/Citra-Azahar) o donde el usuario no juega en RetroArch: en vez de leer al
vuelo, se relee el equipo **cada vez que el usuario guarda la partida** (ver
`pvo.sav.watcher`).

Uso:

    from pvo import sav
    team = sav.read_team_file("/ruta/a/Pokemon Esmeralda.srm")
    team.payload()   # {"pokemonIds": [...], "nicknames": [...]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .container import SaveError, UnsupportedSaveError, size_rank, unwrap
from .parsers import PARSERS, Mon, SaveParser, Slots, ordered_for
from .watcher import SaveWatcher

__all__ = [
    "Mon", "SaveError", "SaveParser", "SaveTeam", "SaveWatcher", "Slots",
    "UnsupportedSaveError",
    "read_team_bytes", "read_team_file", "supported_formats",
]


@dataclass(frozen=True)
class SaveTeam:
    """Equipo leído de una partida guardada."""

    parser_key: str
    label: str
    slots: Slots
    notes: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(1 for s in self.slots if s)

    def payload(self) -> dict:
        """Payload para el endpoint de ingesta de claude-test."""
        return {
            "pokemonIds": [s[0] if s else None for s in self.slots],
            "nicknames": [s[1] if s else None for s in self.slots],
        }


def supported_formats() -> list[tuple[str, str]]:
    """(clave, etiqueta) de las plataformas que el modo SAV sabe leer."""
    return [(p.key, p.label) for p in PARSERS]


def read_team_bytes(data: bytes, filename: str = "") -> SaveTeam:
    """Interpreta el contenido de un fichero de partida y devuelve el equipo.

    Lanza `UnsupportedSaveError` con un mensaje explicativo si es un savestate, y
    `SaveError` si ningún parser reconoce el contenido."""
    container = unwrap(data, filename)
    payload = container.payload

    for parser in ordered_for(size_rank(payload)):
        slots = parser.parse(payload)
        if slots and any(slots):
            return SaveTeam(parser.key, parser.label, slots, list(container.notes))

    raise SaveError(
        f"No se reconoció el equipo en '{filename or 'el fichero'}' "
        f"({len(payload)} bytes). Plataformas soportadas: "
        + "; ".join(label for _, label in supported_formats())
        + ". Switch (gen 8/9) todavía no está soportado."
    )


def read_team_file(path: str | Path) -> SaveTeam:
    p = Path(path)
    return read_team_bytes(p.read_bytes(), p.name)
