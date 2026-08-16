"""Descifrado genérico de estructuras Pokémon con bloques barajados (gen 4 a 7).

Desde gen 4 todas las generaciones comparten el mismo esquema:

    0x00  u32  PID (gen 4/5) / Encryption Constant (gen 6/7)
    0x04  u16  "sanity": SIEMPRE 0 en un Pokémon de caja/equipo
    0x06  u16  checksum de la zona de datos descifrada
    0x08  ...  4 bloques (A/B/C/D) de `block_size` bytes, BARAJADOS y CIFRADOS

- El **orden** de los bloques sale de `((u32[0x00] >> 13) & 31) % 24`.
- El **cifrado** es un LCG de 16 bits sembrado con el *checksum* (gen 4/5) o con el
  *encryption constant* (gen 6/7).
- El checksum (suma de u16 sobre los datos descifrados) valida la lectura: es lo que
  permite localizar el equipo **escaneando el fichero de partida** sin depender de
  offsets memorizados por versión/idioma.

Gen 3 va aparte (`pvo/memory/gen3.py`): usa XOR simple y otro orden de subestructuras.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_LCG_MULT = 0x41C64E6D
_LCG_ADD = 0x6073

# Orden de los 4 bloques según ((u32[0] >> 13) & 31) % 24.
BLOCK_ORDER = [
    "ABCD", "ABDC", "ACBD", "ACDB", "ADBC", "ADCB",
    "BACD", "BADC", "BCAD", "BCDA", "BDAC", "BDCA",
    "CABD", "CADB", "CBAD", "CBDA", "CDAB", "CDBA",
    "DABC", "DACB", "DBAC", "DBCA", "DCAB", "DCBA",
]


def u16(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8)


def u32(b: bytes, i: int) -> int:
    return b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)


def crypt(data: bytes, seed: int) -> bytes:
    """Cifra/descifra (la operación es su propia inversa) con el LCG de 16 bits."""
    out = bytearray(data)
    state = seed & 0xFFFFFFFF
    for i in range(0, len(out) - 1, 2):
        state = (state * _LCG_MULT + _LCG_ADD) & 0xFFFFFFFF
        key = (state >> 16) & 0xFFFF
        word = (out[i] | (out[i + 1] << 8)) ^ key
        out[i] = word & 0xFF
        out[i + 1] = (word >> 8) & 0xFF
    return bytes(out)


def checksum(decrypted: bytes) -> int:
    return sum(u16(decrypted, i) for i in range(0, len(decrypted) - 1, 2)) & 0xFFFF


@dataclass(frozen=True)
class PkmFormat:
    """Parámetros del formato de una generación."""

    key: str
    gen: int
    block_size: int          # 32 (gen 4/5) | 56 (gen 6/7)
    boxed_size: int          # bytes de la parte "de caja" (136 | 232)
    party_size: int          # bytes por hueco del equipo (236 / 220 | 260)
    seed_from_ec: bool       # False = semilla del checksum (gen 4/5); True = EC (gen 6/7)
    nickname_block: int      # índice del bloque lógico (0=A) donde empieza el mote
    nickname_len: int        # nº de caracteres UTF-16
    utf16_nickname: bool     # gen 4 usa su propia tabla de caracteres → no se decodifica
    max_species: int

    @property
    def data_len(self) -> int:
        return self.block_size * 4


# Registro de formatos. Añadir gen 8/9 = añadir una entrada aquí (y su parser de save).
GEN45 = PkmFormat(
    key="gen45", gen=5, block_size=32, boxed_size=136, party_size=236,
    seed_from_ec=False, nickname_block=2, nickname_len=11, utf16_nickname=True,
    max_species=649,
)
GEN67 = PkmFormat(
    key="gen67", gen=7, block_size=56, boxed_size=232, party_size=260,
    seed_from_ec=True, nickname_block=1, nickname_len=12, utf16_nickname=True,
    max_species=809,
)


def _decode_nickname(dec: bytes, fmt: PkmFormat, order: str) -> Optional[str]:
    if not fmt.utf16_nickname:
        return None
    start = order.index("ABCD"[fmt.nickname_block]) * fmt.block_size
    raw = dec[start:start + fmt.nickname_len * 2]
    chars = []
    for i in range(0, len(raw) - 1, 2):
        code = u16(raw, i)
        if code in (0x0000, 0xFFFF):
            break
        chars.append(chr(code))
    name = "".join(chars).strip()
    if not name or any(ord(c) < 0x20 for c in name):
        return None
    return name


def looks_like_pkm(buf: bytes, off: int) -> bool:
    """Pre-filtro barato: descarta la inmensa mayoría de offsets sin descifrar nada.

    Un Pokémon real tiene PID/EC != 0 y el campo "sanity" (u16 @ 0x04) a cero."""
    if off + 8 > len(buf):
        return False
    return u32(buf, off) != 0 and u16(buf, off + 4) == 0 and u16(buf, off + 6) != 0


def decode_mon(mon: bytes, fmt: PkmFormat) -> Optional[tuple[int, Optional[str]]]:
    """Descifra un Pokémon → (nº de Pokédex nacional, mote) o None si vacío/no válido."""
    if len(mon) < 8 + fmt.data_len:
        return None
    ec = u32(mon, 0)
    if ec == 0 or u16(mon, 4) != 0:
        return None
    chk = u16(mon, 6)

    seed = ec if fmt.seed_from_ec else chk
    dec = crypt(mon[8:8 + fmt.data_len], seed)
    if checksum(dec) != chk:
        return None

    order = BLOCK_ORDER[((ec >> 13) & 31) % 24]
    species = u16(dec, order.index("A") * fmt.block_size)
    if species < 1 or species > fmt.max_species:
        return None
    return species, _decode_nickname(dec, fmt, order)


def encode_mon(species: int, ec: int, fmt: PkmFormat,
               nickname: Optional[str] = None) -> bytes:
    """Construye un Pokémon válido (inverso de `decode_mon`). Solo para tests/fixtures."""
    dec = bytearray(fmt.data_len)
    order = BLOCK_ORDER[((ec >> 13) & 31) % 24]
    a = order.index("A") * fmt.block_size
    dec[a] = species & 0xFF
    dec[a + 1] = (species >> 8) & 0xFF
    if nickname and fmt.utf16_nickname:
        n = order.index("ABCD"[fmt.nickname_block]) * fmt.block_size
        for i, ch in enumerate(nickname[: fmt.nickname_len]):
            dec[n + i * 2] = ord(ch) & 0xFF
            dec[n + i * 2 + 1] = (ord(ch) >> 8) & 0xFF
        end = n + len(nickname[: fmt.nickname_len]) * 2
        if end + 1 < len(dec):
            dec[end] = 0xFF
            dec[end + 1] = 0xFF

    chk = checksum(bytes(dec))
    seed = ec if fmt.seed_from_ec else chk
    head = bytearray(8)
    head[0:4] = ec.to_bytes(4, "little")
    head[6:8] = chk.to_bytes(2, "little")
    body = crypt(bytes(dec), seed)
    return bytes(head) + body + bytes(fmt.boxed_size - 8 - fmt.data_len)
