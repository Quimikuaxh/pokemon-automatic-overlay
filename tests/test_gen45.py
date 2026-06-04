import unittest

from pvo.memory import gen45


def build_mon(species: int, pid: int = 0x12345678) -> bytes:
    """Construye los 136 bytes cifrados de un Pokémon de gen 4/5 con esa especie."""
    # Bloques ABCD (32 bytes c/u), especie al inicio del bloque A.
    blocks = {b: bytearray(32) for b in "ABCD"}
    blocks["A"][0] = species & 0xFF
    blocks["A"][1] = (species >> 8) & 0xFF

    order = gen45._BLOCK_ORDER[((pid >> 13) & 31) % 24]
    stored = b"".join(bytes(blocks[b]) for b in order)   # 128 bytes en orden barajado

    checksum = sum(gen45._u16(stored, i) for i in range(0, 128, 2)) & 0xFFFF
    enc = gen45._decrypt(stored, checksum)                # _decrypt es su propia inversa

    mon = bytearray(gen45.BOXED_SIZE)
    mon[0:4] = pid.to_bytes(4, "little")
    mon[6:8] = checksum.to_bytes(2, "little")
    mon[8:136] = enc
    return bytes(mon)


class TestGen45(unittest.TestCase):
    def test_decode_species(self):
        for nat in (260, 286, 310, 323, 227, 282, 493, 649):
            res = gen45.decode_mon(build_mon(nat))
            self.assertIsNotNone(res, f"falló especie {nat}")
            self.assertEqual(res[0], nat)

    def test_various_pids_shuffle(self):
        # distintos PID → distinto orden de bloques; debe seguir acertando
        for pid in (0, 0x1FFF, 0xABCDEF01, 0xFFFFFFFF):
            res = gen45.decode_mon(build_mon(384, pid=pid or 1))
            self.assertEqual(res[0], 384)

    def test_empty_slot(self):
        self.assertIsNone(gen45.decode_mon(bytes(gen45.BOXED_SIZE)))

    def test_party_mixed(self):
        raw = build_mon(260) + bytes(gen45.PARTY_SIZE - gen45.BOXED_SIZE)
        raw += build_mon(286) + bytes(gen45.PARTY_SIZE - gen45.BOXED_SIZE)
        raw += bytes(gen45.PARTY_SIZE) * 4
        party = gen45.decode_party(raw)
        self.assertEqual(party[0][0], 260)
        self.assertEqual(party[1][0], 286)
        self.assertIsNone(party[2])


if __name__ == "__main__":
    unittest.main()
