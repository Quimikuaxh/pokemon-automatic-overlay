"""Lectura del equipo en una partida guardada de GBA (gen 3: RSE / FRLG).

La flash de GBA se organiza en **sectores de 4096 bytes**: 3968 de datos y un pie con
`id`, `checksum`, una firma fija y un **contador de guardado**. El juego alterna entre
dos bloques de 14 sectores, así que el bloque bueno es el del contador más alto.

`SaveBlock1` (sectores 1-4 concatenados) contiene el equipo. El offset depende del
juego (RSE 0x0238, FRLG 0x0038), así que se prueban ambos y, si fallan, se escanea.
"""

from __future__ import annotations

from typing import Optional

from ..memory.gen3 import decode_mon
from ..pkm import u16, u32

SECTOR_SIZE = 4096
SECTOR_DATA = 3968
SIGNATURE = 0x08012025
MON_SIZE = 100
SLOTS = 6

# Offsets del equipo dentro de SaveBlock1 (el contador de miembros va 4 bytes antes).
PARTY_OFFSETS = (0x0238, 0x0038)

Mon = tuple[int, Optional[str]]


def _sectors(payload: bytes) -> dict[int, tuple[int, bytes]]:
    """{id de sección: (contador, datos)} quedándose con el bloque más reciente."""
    best: dict[int, tuple[int, bytes]] = {}
    for base in range(0, len(payload) - SECTOR_SIZE + 1, SECTOR_SIZE):
        sec = payload[base:base + SECTOR_SIZE]
        if u32(sec, 0x0FF8) != SIGNATURE:
            continue
        sec_id = u16(sec, 0x0FF4)
        if sec_id > 13:
            continue
        counter = u32(sec, 0x0FFC)
        prev = best.get(sec_id)
        if prev is None or counter > prev[0]:
            best[sec_id] = (counter, sec[:SECTOR_DATA])
    return best


def save_block_1(payload: bytes) -> Optional[bytes]:
    """Reconstruye SaveBlock1 (secciones 1-4) del bloque de guardado más reciente."""
    secs = _sectors(payload)
    if 1 not in secs:
        return None
    newest = max(c for c, _ in secs.values())
    parts = []
    for sec_id in (1, 2, 3, 4):
        entry = secs.get(sec_id)
        if entry is None or entry[0] != newest:
            break
        parts.append(entry[1])
    if not parts:
        return None
    return b"".join(parts)


def _read_party_at(block: bytes, off: int) -> Optional[list[Optional[Mon]]]:
    if off + SLOTS * MON_SIZE > len(block):
        return None
    slots = [decode_mon(block[off + i * MON_SIZE:off + (i + 1) * MON_SIZE]) for i in range(SLOTS)]
    filled = sum(1 for s in slots if s)
    if filled == 0:
        return None
    # Coherencia: los huecos ocupados van al principio, sin agujeros.
    if any(s is None for s in slots[:filled]):
        return None
    count = u32(block, off - 4) if off >= 4 else -1
    if count != filled:
        return None
    return slots


def find_party(block: bytes) -> Optional[list[Optional[Mon]]]:
    for off in PARTY_OFFSETS:
        slots = _read_party_at(block, off)
        if slots is not None:
            return slots
    # Respaldo: escaneo del bloque (versiones/hacks con otro offset).
    for off in range(4, len(block) - SLOTS * MON_SIZE, 4):
        slots = _read_party_at(block, off)
        if slots is not None:
            return slots
    return None


def read_team(payload: bytes) -> Optional[list[Optional[Mon]]]:
    block = save_block_1(payload)
    if block is None:
        return None
    return find_party(block)
