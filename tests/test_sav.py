import unittest

from pvo import sav
from pvo.sav.container import SaveError, UnsupportedSaveError, unwrap

import savefixtures as fx


class TestContainer(unittest.TestCase):
    def test_desmume_footer_recortado(self):
        data = fx.nds_dsv([25, 6])
        c = unwrap(data, "partida.dsv")
        self.assertEqual(len(c.payload), 0x80000)
        self.assertTrue(any("DeSmuME" in n for n in c.notes))

    def test_duc_header_recortado(self):
        body = fx.nds_save([25])
        c = unwrap(b"ARDS" + bytes(496) + body, "partida.duc")
        self.assertEqual(len(c.payload), len(body))

    def test_savestate_por_firma_avisa(self):
        with self.assertRaises(UnsupportedSaveError) as ctx:
            unwrap(b"RASTATE" + bytes(1000), "juego.state")
        self.assertIn("savestate", str(ctx.exception).lower())

    def test_savestate_por_extension_avisa(self):
        with self.assertRaises(UnsupportedSaveError):
            unwrap(bytes(4096), "juego.ss0")

    def test_fichero_vacio(self):
        with self.assertRaises(SaveError):
            unwrap(b"", "vacio.sav")


class TestGbaGen3(unittest.TestCase):
    def test_equipo_emerald(self):
        team = sav.read_team_bytes(fx.gba_save([282, 310, 260], ["GARDE", "MANEC", ""]),
                                   "esmeralda.srm")
        self.assertEqual(team.parser_key, "gba_gen3")
        self.assertEqual(team.payload()["pokemonIds"], [282, 310, 260, None, None, None])
        self.assertEqual(team.payload()["nicknames"][:2], ["GARDE", "MANEC"])
        self.assertEqual(team.count, 3)

    def test_offset_frlg(self):
        team = sav.read_team_bytes(fx.gba_save([6, 9], party_offset=0x0038), "rojofuego.sav")
        self.assertEqual(team.payload()["pokemonIds"][:2], [6, 9])

    def test_elige_el_bloque_mas_reciente(self):
        data = fx.gba_save([282], counter=99, stale_counter=98, stale_species=[25, 26])
        team = sav.read_team_bytes(data, "esmeralda.sav")
        self.assertEqual(team.payload()["pokemonIds"][0], 282)

    def test_flash_64k(self):
        data = fx.gba_save([25], size=0x10000, counter=1, stale_counter=0,
                           stale_species=[1])[:0x10000]
        team = sav.read_team_bytes(data, "rubi.fla")
        self.assertEqual(team.payload()["pokemonIds"][0], 25)


class TestNdsGen45(unittest.TestCase):
    def test_equipo_gen4(self):
        team = sav.read_team_bytes(fx.nds_save([487, 483, 448], gen=4), "platino.sav")
        self.assertEqual(team.parser_key, "nds_gen45")
        self.assertEqual(team.payload()["pokemonIds"], [487, 483, 448, None, None, None])

    def test_equipo_gen5_paso_220(self):
        team = sav.read_team_bytes(fx.nds_save([643, 644, 646, 570], gen=5), "negro2.sav")
        self.assertEqual(team.payload()["pokemonIds"][:4], [643, 644, 646, 570])

    def test_no_confunde_la_caja_con_el_equipo(self):
        data = fx.nds_save([445, 448], gen=4, box_species=list(range(1, 31)))
        team = sav.read_team_bytes(data, "diamante.sav")
        self.assertEqual(team.payload()["pokemonIds"][:2], [445, 448])

    def test_dsv_completo(self):
        team = sav.read_team_bytes(fx.nds_dsv([494, 495], gen=5), "blanco.dsv")
        self.assertEqual(team.payload()["pokemonIds"][:2], [494, 495])

    def test_motes_utf16(self):
        team = sav.read_team_bytes(fx.nds_save([643], gen=5, nicknames=["Zekrom"]), "b.sav")
        self.assertEqual(team.payload()["nicknames"][0], "Zekrom")

    def test_offset_arbitrario(self):
        """El equipo se localiza por contenido, no por un offset memorizado."""
        team = sav.read_team_bytes(fx.nds_save([151], gen=4, offset=0x2BEEC), "raro.sav")
        self.assertEqual(team.payload()["pokemonIds"][0], 151)


class Test3dsGen67(unittest.TestCase):
    def test_equipo_gen6(self):
        team = sav.read_team_bytes(fx.n3ds_save([658, 700, 448]), "main")
        self.assertEqual(team.parser_key, "3ds_gen67")
        self.assertEqual(team.payload()["pokemonIds"], [658, 700, 448, None, None, None])

    def test_motes_y_caja(self):
        data = fx.n3ds_save([778, 785], nicknames=["Mimikyu", None],
                            box_species=list(range(1, 31)))
        team = sav.read_team_bytes(data, "main")
        self.assertEqual(team.payload()["pokemonIds"][:2], [778, 785])
        self.assertEqual(team.payload()["nicknames"][0], "Mimikyu")


class TestErrores(unittest.TestCase):
    def test_contenido_irreconocible(self):
        with self.assertRaises(SaveError) as ctx:
            sav.read_team_bytes(bytes(0x20000), "vacia.sav")
        self.assertIn("Switch", str(ctx.exception))

    def test_formatos_soportados(self):
        keys = [k for k, _ in sav.supported_formats()]
        self.assertEqual(keys, ["gba_gen3", "nds_gen45", "3ds_gen67"])


if __name__ == "__main__":
    unittest.main()
