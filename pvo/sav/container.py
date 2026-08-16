"""Normalización del *contenedor* del fichero de partida guardada.

Cada emulador guarda la misma memoria con envoltorios distintos (y con extensiones
distintas: `.sav`, `.srm`, `.fla`, `.dsv`, `.duc`…). Aquí se quita el envoltorio y se
deja la **memoria cruda** que entienden los parsers. La detección es por **contenido**,
nunca por extensión: la extensión solo sirve para mensajes de aviso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Footer que DeSmuME añade al final de sus `.dsv` (los últimos 122 bytes).
DESMUME_MAGIC = b"|-DESMUME SAVE-|"
DESMUME_FOOTER_LEN = 122

# Cabecera de los `.duc` (Datel / Action Replay DS).
DUC_MAGIC = b"ARDS"
DUC_HEADER_LEN = 500

# Firmas de *savestates* (no son partidas guardadas: son volcados del emulador).
SAVESTATE_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"RASTATE", "savestate de RetroArch"),
    (b"DeSmuME SState", "savestate de DeSmuME"),
    (b"\x89PNG\r\n", "savestate de mGBA (captura PNG incrustada)"),
    (b"SNAPSHOT", "savestate"),
    (b"BZh", "savestate comprimido"),
    (b"\x1f\x8b\x08", "savestate comprimido (gzip)"),
)

SAVESTATE_SUFFIXES = {
    ".state", ".st0", ".st1", ".st2", ".st3", ".st4",
    ".ss0", ".ss1", ".ss2", ".ss3", ".ss4", ".ss5", ".ss6", ".ss7", ".ss8", ".ss9",
    ".dst", ".sgs", ".gqs", ".dsv0", ".sn0",
}

# Tamaños de memoria de partida plausibles (GBA / NDS / 3DS).
PLAUSIBLE_SIZES = (
    0x8000, 0x10000, 0x20000, 0x40000,          # GBA: 32K / 64K / 128K / 256K
    0x80000, 0x100000,                          # NDS: 512K / 1M
)


class SaveError(Exception):
    """El fichero no se puede interpretar como partida guardada."""


class UnsupportedSaveError(SaveError):
    """El fichero es de un tipo conocido pero NO soportado (p. ej. un savestate)."""


@dataclass(frozen=True)
class Container:
    payload: bytes
    notes: list[str] = field(default_factory=list)


def _is_savestate(data: bytes, suffix: str) -> str | None:
    for magic, label in SAVESTATE_MAGICS:
        if data.startswith(magic):
            return label
    if suffix.lower() in SAVESTATE_SUFFIXES:
        return f"savestate ({suffix})"
    return None


def unwrap(data: bytes, filename: str = "") -> Container:
    """Devuelve la memoria cruda de la partida, quitando cabeceras/footers conocidos.

    Lanza `UnsupportedSaveError` si el fichero es un savestate (así el usuario recibe
    un aviso claro en vez de un fallo silencioso)."""
    suffix = Path(filename).suffix if filename else ""
    kind = _is_savestate(data, suffix)
    if kind is not None:
        raise UnsupportedSaveError(
            f"'{filename or 'el fichero'}' parece un {kind}. Los savestates no están "
            "soportados: guarda la partida DENTRO del juego para que el emulador "
            "escriba el fichero de partida (.sav/.srm/.dsv…)."
        )

    notes: list[str] = []
    payload = data

    if payload.startswith(DUC_MAGIC) and len(payload) > DUC_HEADER_LEN:
        payload = payload[DUC_HEADER_LEN:]
        notes.append("cabecera .duc (Action Replay) descartada")

    if payload.endswith(DESMUME_MAGIC) and len(payload) > DESMUME_FOOTER_LEN:
        payload = payload[:-DESMUME_FOOTER_LEN]
        notes.append("footer DeSmuME (.dsv) recortado")

    if not payload:
        raise SaveError("El fichero de partida está vacío.")
    return Container(payload=payload, notes=notes)


def size_rank(payload: bytes) -> int:
    """Tamaño 'canónico' más cercano por abajo; 0 si no encaja en ninguno conocido."""
    best = 0
    for s in PLAUSIBLE_SIZES:
        if len(payload) >= s:
            best = s
    return best
