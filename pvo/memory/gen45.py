"""Descifrado de la estructura de datos de Pokémon de Generación IV y V (NDS).

El esquema (4 bloques barajados + LCG sembrado por el checksum) es común a gen 4-7, así
que vive en `pvo/pkm.py`; aquí solo queda la fachada que usa la lectura por memoria.

Referencia: Project Pokémon, "Pokémon NDS Structure".
"""

from __future__ import annotations

from typing import Optional

from ..pkm import BLOCK_ORDER, GEN45, crypt, u16, u32
from ..pkm import decode_mon as _decode

# Alias internos históricos (los usan los tests y el resto del paquete).
_BLOCK_ORDER = BLOCK_ORDER
_u16 = u16
_u32 = u32
_decrypt = crypt

BOXED_SIZE = GEN45.boxed_size      # 136
PARTY_SIZE = GEN45.party_size      # 236 (gen 4); gen 5 usa 220


def decode_mon(mon: bytes) -> Optional[tuple[int, Optional[str]]]:
    """Descifra los 136 bytes 'boxed' → (dex nacional, mote) o None si vacío/corrupto."""
    return _decode(mon, GEN45)


def decode_party(raw: bytes, mon_size: int = PARTY_SIZE) -> list[Optional[tuple[int, Optional[str]]]]:
    return [decode_mon(raw[i * mon_size:i * mon_size + BOXED_SIZE]) for i in range(6)]
