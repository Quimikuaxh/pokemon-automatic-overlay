"""Registro de parsers de partida guardada.

**Añadir una plataforma nueva = añadir una entrada a `PARSERS`.** Es el punto de
extensión previsto para la fase 2 (Switch, gen 8/9: SWSH, BDSP, PLA, SV), que todavía
NO está soportada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..pkm import GEN45, GEN67
from . import gba, scan

Mon = tuple[int, Optional[str]]
Slots = list[Optional[Mon]]


@dataclass(frozen=True)
class SaveParser:
    key: str
    label: str
    # Tamaños típicos de la memoria de partida; solo se usan para ordenar los intentos.
    sizes: tuple[int, ...]
    parse: Callable[[bytes], Optional[Slots]]


def _parse_nds(payload: bytes) -> Optional[Slots]:
    # Paso 236 en gen 4, 220 en gen 5.
    return scan.find_party(payload, GEN45, strides=(236, 220))


def _parse_3ds(payload: bytes) -> Optional[Slots]:
    return scan.find_party(payload, GEN67, strides=(260,))


PARSERS: list[SaveParser] = [
    SaveParser(
        key="gba_gen3",
        label="GBA — gen 3 (Rubí/Zafiro, Esmeralda, Rojo Fuego/Verde Hoja)",
        sizes=(0x20000, 0x10000, 0x8000),
        parse=gba.read_team,
    ),
    SaveParser(
        key="nds_gen45",
        label="NDS — gen 4/5 (Diamante/Perla, Platino, HG/SS, Negro/Blanco, N2/B2)",
        sizes=(0x80000, 0x100000, 0x40000),
        parse=_parse_nds,
    ),
    SaveParser(
        key="3ds_gen67",
        label="3DS — gen 6/7 (X/Y, RO/ZA, Sol/Luna, US/UL) vía Citra/Azahar",
        sizes=(0x6BE00, 0x6CC00, 0x65600, 0x76000),
        parse=_parse_3ds,
    ),
]


def ordered_for(size: int) -> list[SaveParser]:
    """Parsers ordenados: primero los que encajan con el tamaño del fichero."""
    return sorted(PARSERS, key=lambda p: 0 if size in p.sizes else 1)
