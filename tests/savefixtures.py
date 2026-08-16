"""Constructores de ficheros de partida SINTÉTICOS para los tests del modo SAV.

No hacen falta partidas reales: se generan estructuras válidas (checksums incluidos)
con las mismas reglas que aplican los parsers, lo que verifica el camino completo
contenedor → detección → localización del equipo → payload.
"""

from __future__ import annotations

from pvo.memory.gen3 import _CHARMAP, _SUBSTRUCT_ORDER, _u16, _u32
from pvo.memory.gen3_species import NATIONAL_TO_INTERNAL
from pvo.pkm import GEN45, GEN67, PkmFormat, encode_mon
from pvo.sav.container import DESMUME_MAGIC, DESMUME_FOOTER_LEN
from pvo.sav.gba import SECTOR_DATA, SECTOR_SIZE, SIGNATURE

# --------------------------------------------------------------------------- GBA


def _enc_name(s: str) -> bytes:
    rev = {v: k for k, v in _CHARMAP.items()}
    out = bytes(rev.get(c, 0x00) for c in s)
    return (out + bytes([0xFF]) + bytes(10))[:10]


def gba_mon(national: int, nickname: str = "", pv: int = 0x12345678,
            otid: int = 0x9ABCDEF0) -> bytes:
    """100 bytes cifrados de un Pokémon de gen 3."""
    internal = national if national <= 251 else NATIONAL_TO_INTERNAL[national]
    key = pv ^ otid

    data = bytearray(48)
    g = _SUBSTRUCT_ORDER[pv % 24].index("G") * 12
    data[g] = internal & 0xFF
    data[g + 1] = (internal >> 8) & 0xFF
    checksum = sum(_u16(data, i) for i in range(0, 48, 2)) & 0xFFFF

    enc = bytearray(data)
    for i in range(0, 48, 4):
        w = _u32(enc, i) ^ key
        enc[i] = w & 0xFF
        enc[i + 1] = (w >> 8) & 0xFF
        enc[i + 2] = (w >> 16) & 0xFF
        enc[i + 3] = (w >> 24) & 0xFF

    mon = bytearray(100)
    mon[0:4] = pv.to_bytes(4, "little")
    mon[4:8] = otid.to_bytes(4, "little")
    mon[8:18] = _enc_name(nickname)
    mon[28:30] = checksum.to_bytes(2, "little")
    mon[32:80] = enc
    return bytes(mon)


def gba_save(species: list[int], nicknames: list[str] | None = None,
             party_offset: int = 0x0238, counter: int = 7,
             size: int = 0x20000, stale_counter: int = 3,
             stale_species: list[int] | None = None) -> bytes:
    """Partida de GBA completa: dos bloques de 14 sectores, el segundo más reciente.

    `stale_species` puebla el bloque ANTIGUO, para comprobar que se elige el bloque
    con el contador de guardado más alto."""
    nicknames = nicknames or [""] * len(species)

    def block(sp: list[int], nick: list[str], count: int) -> bytes:
        sb1 = bytearray(SECTOR_DATA * 4)
        sb1[party_offset - 4:party_offset] = len(sp).to_bytes(4, "little")
        for i, (s, n) in enumerate(zip(sp, nick)):
            off = party_offset + i * 100
            sb1[off:off + 100] = gba_mon(s, n, pv=0x1000 + i * 0x2468)
        out = bytearray()
        for sec_id in range(14):
            sec = bytearray(SECTOR_SIZE)
            if 1 <= sec_id <= 4:
                chunk = sb1[(sec_id - 1) * SECTOR_DATA:sec_id * SECTOR_DATA]
                sec[:SECTOR_DATA] = chunk
            sec[0x0FF4:0x0FF6] = sec_id.to_bytes(2, "little")
            sec[0x0FF8:0x0FFC] = SIGNATURE.to_bytes(4, "little")
            sec[0x0FFC:0x1000] = count.to_bytes(4, "little")
            out += sec
        return bytes(out)

    old = stale_species or [1]
    data = bytearray(size)
    blk_a = block(old, [""] * len(old), stale_counter)
    blk_b = block(species, nicknames, counter)
    data[0:len(blk_a)] = blk_a
    data[0xE000:0xE000 + len(blk_b)] = blk_b
    return bytes(data)


# --------------------------------------------------------------------------- NDS / 3DS


def _shuffled_save(species: list[int], fmt: PkmFormat, stride: int, offset: int,
                   size: int, nicknames: list[str] | None = None,
                   box_species: list[int] | None = None,
                   box_offset: int = 0x1000) -> bytes:
    nicknames = nicknames or [None] * len(species)
    data = bytearray(size)
    for i, (s, n) in enumerate(zip(species, nicknames)):
        mon = encode_mon(s, ec=0x2000 + i * 0x13579, fmt=fmt, nickname=n)
        at = offset + i * stride
        data[at:at + len(mon)] = mon
    # Una caja con Pokémon seguidos a paso "de caja": el escaneo NO debe confundirla.
    for i, s in enumerate(box_species or []):
        mon = encode_mon(s, ec=0x900000 + i * 0x2468A, fmt=fmt)
        at = box_offset + i * fmt.boxed_size
        data[at:at + len(mon)] = mon
    return bytes(data)


def nds_save(species: list[int], gen: int = 4, offset: int = 0x00A0,
             size: int = 0x80000, nicknames: list[str] | None = None,
             box_species: list[int] | None = None) -> bytes:
    stride = 236 if gen == 4 else 220
    return _shuffled_save(species, GEN45, stride, offset, size, nicknames,
                          box_species, box_offset=0x30000)


def nds_dsv(species: list[int], **kw) -> bytes:
    """Partida NDS con el footer que añade DeSmuME a sus `.dsv`."""
    body = nds_save(species, **kw)
    footer = bytearray(DESMUME_FOOTER_LEN)
    footer[-len(DESMUME_MAGIC):] = DESMUME_MAGIC
    return body + bytes(footer)


def n3ds_save(species: list[int], offset: int = 0x14200, size: int = 0x6BE00,
              nicknames: list[str] | None = None,
              box_species: list[int] | None = None) -> bytes:
    return _shuffled_save(species, GEN67, 260, offset, size, nicknames,
                          box_species, box_offset=0x33000)
