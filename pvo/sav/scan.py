"""Localización del equipo dentro de un fichero de partida, **por contenido**.

En vez de memorizar el offset del equipo para cada juego, idioma y revisión (que es
donde estas herramientas se rompen), se escanea el fichero buscando estructuras de
Pokémon que **validen su propio checksum**, y se elige la cadena de huecos consecutivos
que se comporta como un equipo.

Discriminación equipo vs. caja: los Pokémon de caja van seguidos con paso `boxed_size`
y los del equipo con paso `party_size` (distinto y no múltiplo del anterior), así que
una cadena larga a paso "de equipo" no puede ser una caja.
"""

from __future__ import annotations

from typing import Optional

from ..pkm import PkmFormat, decode_mon, looks_like_pkm

Mon = tuple[int, Optional[str]]
SLOTS = 6
_ALIGN = 4
_BOX_CHAIN_MIN = 3      # ≥3 seguidos a paso "de caja" ⇒ es una caja, no el equipo


def find_valid_mons(buf: bytes, fmt: PkmFormat) -> dict[int, Mon]:
    """Offsets (alineados a 4) donde hay un Pokémon que valida su checksum."""
    found: dict[int, Mon] = {}
    limit = len(buf) - fmt.boxed_size
    for off in range(0, limit + 1, _ALIGN):
        if not looks_like_pkm(buf, off):
            continue
        mon = decode_mon(buf[off:off + fmt.boxed_size], fmt)
        if mon is not None:
            found[off] = mon
    return found


def _chain_len(offsets: set[int], start: int, stride: int, cap: int = SLOTS) -> int:
    n = 0
    while n < cap and (start + n * stride) in offsets:
        n += 1
    return n


def _box_offsets(offsets: set[int], boxed_size: int) -> set[int]:
    """Offsets que forman parte de una tirada larga a paso 'de caja'."""
    inside: set[int] = set()
    for off in offsets:
        if (off - boxed_size) in offsets:
            continue    # no es el principio de la tirada
        n = _chain_len(offsets, off, boxed_size, cap=64)
        if n >= _BOX_CHAIN_MIN:
            inside.update(off + i * boxed_size for i in range(n))
    return inside


def find_party(buf: bytes, fmt: PkmFormat, strides: tuple[int, ...]) -> Optional[list[Optional[Mon]]]:
    """Devuelve los 6 huecos del equipo, o None si no se encuentra ninguno."""
    found = find_valid_mons(buf, fmt)
    if not found:
        return None
    offsets = set(found)
    boxed = _box_offsets(offsets, fmt.boxed_size)

    best: Optional[tuple[int, int, int]] = None      # (longitud, -offset, stride)
    for stride in strides:
        for off in sorted(offsets - boxed):
            if (off - stride) in offsets:
                continue                              # no es el primer hueco
            n = _chain_len(offsets, off, stride)
            if n == 0:
                continue
            key = (n, -off, stride)
            if best is None or key > best:
                best = key
    if best is None:
        return None

    n, neg_off, stride = best
    start = -neg_off
    return [found.get(start + i * stride) for i in range(SLOTS)]
