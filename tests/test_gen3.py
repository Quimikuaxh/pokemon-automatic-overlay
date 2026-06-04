import unittest

from pvo.memory import gen3
from pvo.memory.gen3_species import NATIONAL_TO_INTERNAL


def _enc_name(s: str) -> bytes:
    rev = {v: k for k, v in gen3._CHARMAP.items()}
    out = bytes(rev.get(c, 0x00) for c in s)
    return (out + bytes([0xFF]) + bytes(10))[:10]


def build_mon(national: int, nickname: str = "", pv: int = 0x12345678, otid: int = 0x9ABCDEF0) -> bytes:
    """Construye los 100 bytes cifrados de un Pokémon de gen 3."""
    internal = national if national <= 251 else NATIONAL_TO_INTERNAL[national]
    key = pv ^ otid

    data = bytearray(48)
    order = gen3._SUBSTRUCT_ORDER[pv % 24]
    g = order.index("G") * 12
    data[g] = internal & 0xFF
    data[g + 1] = (internal >> 8) & 0xFF

    checksum = sum(gen3._u16(data, i) for i in range(0, 48, 2)) & 0xFFFF

    enc = bytearray(data)
    for i in range(0, 48, 4):
        w = gen3._u32(enc, i) ^ key
        enc[i] = w & 0xFF; enc[i + 1] = (w >> 8) & 0xFF
        enc[i + 2] = (w >> 16) & 0xFF; enc[i + 3] = (w >> 24) & 0xFF

    mon = bytearray(100)
    mon[0:4] = pv.to_bytes(4, "little")
    mon[4:8] = otid.to_bytes(4, "little")
    mon[8:18] = _enc_name(nickname)
    mon[28:30] = checksum.to_bytes(2, "little")
    mon[32:80] = enc
    return bytes(mon)


class TestGen3(unittest.TestCase):
    def test_internal_to_national(self):
        self.assertEqual(gen3.internal_to_national(25), 25)     # Pikachu
        self.assertEqual(gen3.internal_to_national(338), 310)   # Manectric (Hoenn)
        self.assertEqual(gen3.internal_to_national(394), 282)   # Gardevoir (Hoenn)
        self.assertEqual(gen3.internal_to_national(277), 252)   # Treecko
        self.assertIsNone(gen3.internal_to_national(0))
        self.assertIsNone(gen3.internal_to_national(260))       # no usado (interno)

    def test_decode_known_team(self):
        team = {1: 310, 2: 286, 3: 260, 4: 323, 5: 227, 6: 282}  # slot→dex
        for nat in team.values():
            mon = build_mon(nat, "TEST")
            res = gen3.decode_mon(mon)
            self.assertIsNotNone(res)
            self.assertEqual(res[0], nat)

    def test_nickname_decoded(self):
        mon = build_mon(310, "MANECTRIC")
        dex, nick = gen3.decode_mon(mon)
        self.assertEqual(dex, 310)
        self.assertEqual(nick, "MANECTRIC")

    def test_empty_slot_is_none(self):
        self.assertIsNone(gen3.decode_mon(bytes(100)))   # todo ceros

    def test_decode_party(self):
        raw = build_mon(310, "A") + build_mon(286, "B") + bytes(100) * 4
        party = gen3.decode_party(raw)
        self.assertEqual(party[0][0], 310)
        self.assertEqual(party[1][0], 286)
        self.assertIsNone(party[2])


if __name__ == "__main__":
    unittest.main()
