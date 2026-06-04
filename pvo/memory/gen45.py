"""Descifrado de la estructura de datos de Pokémon de Generación IV y V (NDS).

Cada Pokémon (parte "boxed") ocupa 136 bytes; en el equipo van 236 (136 + datos de
combate). Los 128 bytes de datos (offset 0x08) van en 4 bloques de 32 bytes barajados
según el PID y cifrados con un PRNG (LCG) sembrado por el checksum. La especie está al
inicio del bloque A y **ya es el nº de Pokédex nacional** (sin remapear como en gen 3).

Referencia: Project Pokémon, "Pokémon NDS Structure".
"""

from __future__ import annotations

from typing import Optional

_LCG_MULT = 0x41C64E6D
_LCG_ADD = 0x6073

# Orden de los 4 bloques según ((pid >> 13) & 31) % 24.
_BLOCK_ORDER = [
    "ABCD", "ABDC", "ACBD", "ACDB", "ADBC", "ADCB",
    "BACD", "BADC", "BCAD", "BCDA", "BDAC", "BDCA",
    "CABD", "CADB", "CBAD", "CBDA", "CDAB", "CDBA",
    "DABC", "DACB", "DBAC", "DBCA", "DCAB", "DCBA",
]

BOXED_SIZE = 136
PARTY_SIZE = 236


def _u16(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8)


def _u32(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)


def _decrypt(data: bytes, seed: int) -> bytes:
    out = bytearray(data)
    state = seed & 0xFFFFFFFF
    for i in range(0, len(data), 2):
        state = (state * _LCG_MULT + _LCG_ADD) & 0xFFFFFFFF
        key = (state >> 16) & 0xFFFF
        word = (out[i] | (out[i + 1] << 8)) ^ key
        out[i] = word & 0xFF
        out[i + 1] = (word >> 8) & 0xFF
    return bytes(out)


def decode_mon(mon: bytes) -> Optional[tuple[int, Optional[str]]]:
    """Decodifica los 136 bytes 'boxed' → (dex_nacional, mote) o None si vacío/corrupto."""
    if len(mon) < BOXED_SIZE:
        return None
    pid = _u32(mon, 0)
    if pid == 0:
        return None
    checksum = _u16(mon, 6)

    dec = _decrypt(mon[8:136], checksum)            # 128 bytes descifrados
    calc = sum(_u16(dec, i) for i in range(0, 128, 2)) & 0xFFFF
    if calc != checksum:
        return None                                 # hueco vacío o datos no válidos

    order = _BLOCK_ORDER[((pid >> 13) & 31) % 24]
    block_a = dec[order.index("A") * 32:order.index("A") * 32 + 32]
    species = _u16(block_a, 0)
    if species < 1 or species > 1025:
        return None
    return species, None                            # mote (gen4/5) pendiente


def decode_party(raw: bytes, mon_size: int = PARTY_SIZE) -> list[Optional[tuple[int, Optional[str]]]]:
    out = []
    for i in range(6):
        chunk = raw[i * mon_size:i * mon_size + BOXED_SIZE]
        out.append(decode_mon(chunk))
    return out
