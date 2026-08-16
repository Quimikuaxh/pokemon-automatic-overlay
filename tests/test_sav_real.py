"""Comprobación contra partidas guardadas REALES.

Las partidas son datos personales del usuario, así que **no se versionan**. Este test
se salta solo salvo que se apunte a una carpeta con saves de verdad:

    PVO_REAL_SAVES=/ruta/con/mis/saves python -m unittest discover -s tests -v

Comprueba lo que se puede afirmar sin conocer el contenido concreto: que cada fichero
reconocido se parsea, que el equipo es coherente (huecos ocupados al principio, dex en
rango) y que releer da exactamente lo mismo.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pvo import sav
from pvo.sav import locate

_ROOT = os.environ.get("PVO_REAL_SAVES", "").strip()


@unittest.skipUnless(_ROOT and Path(_ROOT).is_dir(),
                     "define PVO_REAL_SAVES con una carpeta de partidas reales")
class TestSavesReales(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = locate.find_saves([Path(_ROOT)], max_depth=3)

    def test_encuentra_al_menos_una(self):
        self.assertTrue(self.candidates, f"ninguna partida legible en {_ROOT}")

    def test_equipos_coherentes(self):
        for cand in self.candidates:
            with self.subTest(path=cand.path):
                team = sav.read_team_file(cand.path)
                self.assertEqual(team.parser_key, cand.parser_key)
                self.assertEqual(len(team.slots), 6)

                # Los huecos ocupados van al principio, sin agujeros.
                filled = [s is not None for s in team.slots]
                self.assertEqual(filled, sorted(filled, reverse=True),
                                 "hay un hueco vacío entre Pokémon")
                self.assertGreaterEqual(team.count, 1)

                for slot in team.slots:
                    if slot is None:
                        continue
                    dex, nick = slot
                    self.assertTrue(1 <= dex <= 1025, f"dex fuera de rango: {dex}")
                    if nick is not None:
                        self.assertTrue(nick.strip(), "mote vacío en vez de None")
                        self.assertLessEqual(len(nick), 12)

    def test_lectura_determinista(self):
        for cand in self.candidates:
            with self.subTest(path=cand.path):
                a = sav.read_team_file(cand.path).payload()
                b = sav.read_team_file(cand.path).payload()
                self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
