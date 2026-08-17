import tempfile
import unittest
from pathlib import Path

import savefixtures as fx
from pvo.sav import SaveWatcher, UnsupportedSaveError, read_team_file


class TestSaveWatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "partida.srm"
        self.seen: list[Path] = []
        self.errors: list[Exception] = []
        self.w = SaveWatcher(self.path, on_change=self.seen.append,
                             on_error=self.errors.append, poll_interval_s=0.05,
                             stable_for_s=0.0)

    def tearDown(self):
        self.w.stop()
        self.tmp.cleanup()

    def test_no_emite_si_no_existe(self):
        self.assertFalse(self.w.poll_once())
        self.assertEqual(self.seen, [])

    def test_emite_al_aparecer_y_al_cambiar(self):
        self.path.write_bytes(fx.gba_save([282]))
        self.assertTrue(self.w.poll_once())
        self.assertEqual(len(self.seen), 1)

        # Mismo contenido → no se reemite (evita republicar en cada poll).
        self.assertFalse(self.w.poll_once())
        self.assertEqual(len(self.seen), 1)

        # El usuario guarda otra vez con otro equipo.
        self.path.write_bytes(fx.gba_save([310, 260], counter=9))
        self.assertTrue(self.w.poll_once())
        self.assertEqual(len(self.seen), 2)

    def test_escritura_parcial_no_rompe(self):
        """Un save a medio escribir no se puede parsear: se reporta, no se cuelga."""
        errors = []
        w = SaveWatcher(self.path, on_change=lambda p: read_team_file(p),
                        on_error=errors.append, poll_interval_s=0.05, stable_for_s=0.0)
        self.path.write_bytes(bytes(1024))          # fichero incompleto
        w.poll_once()
        self.assertEqual(len(errors), 1)

        self.path.write_bytes(fx.gba_save([282]))   # ya completo
        errors.clear()
        w.poll_once()
        self.assertEqual(errors, [])

    def test_savestate_reporta_error_explicativo(self):
        errors = []
        w = SaveWatcher(self.path, on_change=lambda p: read_team_file(p),
                        on_error=errors.append, poll_interval_s=0.05, stable_for_s=0.0)
        self.path.write_bytes(b"RASTATE" + bytes(2048))
        w.poll_once()
        self.assertIsInstance(errors[0], UnsupportedSaveError)
        self.assertIn("savestate", str(errors[0]).lower())

    def test_hilo_arranca_y_para(self):
        self.path.write_bytes(fx.gba_save([282]))
        self.w.start()
        import time
        for _ in range(40):
            if self.seen:
                break
            time.sleep(0.05)
        self.w.stop()
        self.assertEqual(len(self.seen), 1)


if __name__ == "__main__":
    unittest.main()
