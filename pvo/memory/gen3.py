"""Descifrado de la estructura de datos de Pokémon de Generación III.

Cada Pokémon ocupa 100 bytes. Los 48 bytes de datos (offset 0x20) están cifrados
(XOR con personality^OTID) y sus 4 subestructuras (Growth/Attacks/EVs/Misc) van en un
orden dado por personality % 24. La especie va en la subestructura Growth.

Referencia: Bulbapedia, "Pokémon data structure in Generation III".
"""

from __future__ import annotations

from typing import Optional

# Orden de las 4 subestructuras según personality % 24.
_SUBSTRUCT_ORDER = [
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
]

# Charmap occidental (Western) de gen 3 para nombres/motes.
_CHARMAP: dict[int, str] = {0x00: " ", 0xAE: "-", 0xBA: "."}
for _i in range(10):
    _CHARMAP[0xA1 + _i] = "0123456789"[_i]
for _i in range(26):
    _CHARMAP[0xBB + _i] = chr(ord("A") + _i)
    _CHARMAP[0xD5 + _i] = chr(ord("a") + _i)
_TERMINATOR = 0xFF


def _u16(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8)


def _u32(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)


def internal_to_national(idx: int) -> Optional[int]:
    """Índice interno de especie (gen 3) → nº de Pokédex nacional."""
    if 1 <= idx <= 251:
        return idx
    if 277 <= idx <= 411:          # Hoenn: desplazamiento fijo de 25
        return idx - 25
    return None                    # 0 = hueco; 252-276 = no usados


def decode_nickname(raw: bytes) -> Optional[str]:
    out = []
    for byte in raw:
        if byte == _TERMINATOR:
            break
        out.append(_CHARMAP.get(byte, ""))
    name = "".join(out).strip()
    return name or None


def decode_mon(mon: bytes) -> Optional[tuple[int, Optional[str]]]:
    """Decodifica 100 bytes → (dex_nacional, mote) o None si el slot está vacío/corrupto."""
    if len(mon) < 80:
        return None
    pv = _u32(mon, 0)
    otid = _u32(mon, 4)
    key = pv ^ otid

    enc = bytearray(mon[32:80])     # 48 bytes de datos cifrados
    for i in range(0, 48, 4):
        word = _u32(enc, i) ^ key
        enc[i] = word & 0xFF
        enc[i + 1] = (word >> 8) & 0xFF
        enc[i + 2] = (word >> 16) & 0xFF
        enc[i + 3] = (word >> 24) & 0xFF

    checksum = _u16(mon, 28)
    calc = sum(_u16(enc, i) for i in range(0, 48, 2)) & 0xFFFF
    if calc != checksum:
        return None                # hueco vacío (todo ceros) o datos no válidos

    order = _SUBSTRUCT_ORDER[pv % 24]
    growth = order.index("G") * 12
    species_internal = _u16(enc, growth)
    national = internal_to_national(species_internal)
    if national is None:
        return None
    return national, decode_nickname(mon[8:18])


def decode_party(raw: bytes) -> list[Optional[tuple[int, Optional[str]]]]:
    """Decodifica los 6 slots (600 bytes) → lista de (dex, mote) o None."""
    return [decode_mon(raw[i * 100:(i + 1) * 100]) for i in range(6)]
