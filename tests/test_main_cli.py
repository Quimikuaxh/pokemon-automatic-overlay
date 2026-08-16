"""Comprobaciones de la CLI del agente (el punto de entrada del .exe)."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import savefixtures as fx
from pvo import main as cli


class TestRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, path) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.cmd_read(str(path))
        return code, out.getvalue() + err.getvalue()

    def test_muestra_el_equipo(self):
        p = self.dir / "esmeralda.srm"
        p.write_bytes(fx.gba_save([282, 310], ["GARDE", "MANEC"]))
        code, text = self._read(p)
        self.assertEqual(code, 0)
        self.assertIn("#282", text)
        self.assertIn("GARDE", text)
        self.assertIn("6. —", text)          # los huecos vacíos se muestran

    def test_savestate_avisa_y_falla(self):
        p = self.dir / "juego.state"
        p.write_bytes(b"RASTATE" + bytes(2048))
        code, text = self._read(p)
        self.assertEqual(code, 2)
        self.assertIn("savestate", text.lower())

    def test_fichero_inexistente_no_revienta(self):
        code, text = self._read(self.dir / "no_existe.sav")
        self.assertEqual(code, 2)


class TestArranque(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "config.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def test_crea_la_config_si_falta_y_señala_esa_ruta(self):
        """El error debe apuntar a la config EN USO, no a la de por defecto."""
        with self.assertLogs("pvo", level="ERROR") as logs:
            code = cli.main(["-c", str(self.cfg)])
        self.assertEqual(code, 2)
        self.assertTrue(self.cfg.exists(), "debería haber creado la config")
        mensaje = "\n".join(logs.output)
        self.assertIn(str(self.cfg), mensaje)
        self.assertIn("api_base", mensaje)

    def test_config_completa_arranca_el_agente(self):
        self.cfg.write_text(
            "api_base: http://localhost:1\n"
            "ingest_token: 00000000-0000-0000-0000-000000000000\n"
        )
        with mock.patch.object(cli, "run_agent", return_value=0) as run:
            self.assertEqual(cli.main(["-c", str(self.cfg)]), 0)
        cfg, path = run.call_args.args
        self.assertEqual(cfg["api_base"], "http://localhost:1")
        self.assertEqual(path, self.cfg)

    def test_ya_no_existe_el_modo_sin_web(self):
        """El canal de control es obligatorio: --no-bridge/--run no existen."""
        for flag in ("--no-bridge", "--run"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                cli.main(["-c", str(self.cfg), flag])


class TestDetectSaves(unittest.TestCase):
    def test_sin_resultados_devuelve_1_y_lista_las_rutas(self):
        out = io.StringIO()
        with mock.patch("pvo.sav.locate.find_saves", return_value=[]), \
             mock.patch("pvo.sav.locate.default_roots", return_value=[Path("/tmp")]), \
             redirect_stdout(out):
            code = cli.cmd_detect_saves()
        self.assertEqual(code, 1)
        self.assertIn("/tmp", out.getvalue())


if __name__ == "__main__":
    unittest.main()
