"""El agente persiste lo que se elige en la web y lo reanuda al reiniciar.

Como la fuente, la ruta del save y el juego ya solo se eligen desde el panel web, el
agente los guarda en `config.yaml` cada vez que cambian. Así el usuario abre el .exe y
sigue publicando sin volver a tocar el navegador.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import savefixtures as fx
from pvo.agent.core import AgentCore
from pvo.appconfig import (
    can_resume,
    load_app_config,
    merge_state,
    normalize_config,
    persist_state,
)
from pvo.publisher import Publisher


class FakePublisher(Publisher):
    def __init__(self):
        self.sent: list[dict] = []
        super().__init__("http://test", "token", post_fn=self._post, min_interval_s=0.0)

    def _post(self, url, body):
        self.sent.append(body)
        return 200


class TestMergeState(unittest.TestCase):
    def test_solo_toca_claves_de_estado(self):
        cfg = normalize_config({"api_base": "http://a", "ingest_token": "t"})
        merged = merge_state(cfg, {"source": "sav", "sav_path": "/x.srm",
                                   "api_base": "http://MALO"})
        self.assertEqual(merged["source"], "sav")
        self.assertEqual(merged["sav_path"], "/x.srm")
        self.assertEqual(merged["api_base"], "http://a", "no debe pisar lo del usuario")

    def test_ignora_valores_nulos(self):
        cfg = normalize_config({"sav_path": "/previo.srm"})
        self.assertEqual(merge_state(cfg, {"sav_path": None})["sav_path"], "/previo.srm")


class TestCanResume(unittest.TestCase):
    def test_sin_nada_persistido(self):
        self.assertFalse(can_resume(normalize_config(None)))

    def test_sav_necesita_ruta(self):
        self.assertFalse(can_resume(normalize_config({"source": "sav", "autostart": True})))
        self.assertTrue(can_resume(normalize_config(
            {"source": "sav", "autostart": True, "sav_path": "/x.srm"})))

    def test_retroarch_necesita_juego(self):
        self.assertFalse(can_resume(normalize_config(
            {"source": "retroarch", "autostart": True})))
        self.assertTrue(can_resume(normalize_config(
            {"source": "retroarch", "autostart": True, "game": "GBA — Esmeralda"})))

    def test_parado_no_reanuda_aunque_haya_ruta(self):
        self.assertFalse(can_resume(normalize_config(
            {"source": "sav", "autostart": False, "sav_path": "/x.srm"})))


class TestPersistenciaEnDisco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg_path = self.dir / "config.yaml"
        self.save = self.dir / "esmeralda.srm"
        self.save.write_bytes(fx.gba_save([282, 310], ["GARDE", "MANEC"]))
        self.cfg = normalize_config({"api_base": "http://test", "ingest_token": "tok"})

    def tearDown(self):
        self.tmp.cleanup()

    def _core(self):
        self.out: list[dict] = []
        return AgentCore(
            self.cfg, send=self.out.append, publisher=FakePublisher(),
            save_state=lambda updates: persist_state(self.cfg_path, self.cfg, updates),
        )

    def test_arrancar_desde_la_web_se_guarda_y_reanuda_al_reiniciar(self):
        core = self._core()
        core.handle({"type": "start", "source": "sav",
                     "config": {"sav_path": str(self.save),
                                "sav_poll_interval_s": 0.05,
                                "sav_stable_for_s": 0.0}})
        self.assertTrue(core.running)
        core.close()

        # --- se cierra el .exe y se vuelve a abrir ---
        reloaded = load_app_config(self.cfg_path)
        self.assertEqual(reloaded["source"], "sav")
        self.assertEqual(reloaded["sav_path"], str(self.save))
        self.assertEqual(reloaded["sav_poll_interval_s"], 0.05)
        self.assertTrue(can_resume(reloaded), "debería reanudar sin tocar la web")

        # Y al reanudar publica el equipo de verdad.
        pub = FakePublisher()
        core2 = AgentCore(reloaded, send=[].append, publisher=pub)
        core2.start(reloaded["source"], reloaded)
        core2._source._watcher.poll_once()
        self.assertEqual(pub.sent[-1]["pokemonIds"][:2], [282, 310])
        core2.close()

    def test_retroarch_guarda_el_juego(self):
        core = self._core()
        core.handle({"type": "start", "source": "retroarch",
                     "config": {"game": "GBA — Esmeralda"}})
        core.close()
        reloaded = load_app_config(self.cfg_path)
        self.assertEqual(reloaded["source"], "retroarch")
        self.assertEqual(reloaded["game"], "GBA — Esmeralda")
        self.assertTrue(can_resume(reloaded))

    def test_parar_desde_la_web_se_recuerda(self):
        core = self._core()
        core.handle({"type": "start", "source": "sav",
                     "config": {"sav_path": str(self.save), "sav_stable_for_s": 0.0}})
        core.handle({"type": "stop"})

        reloaded = load_app_config(self.cfg_path)
        self.assertFalse(reloaded["autostart"])
        self.assertFalse(can_resume(reloaded), "no debe arrancar solo si lo paraste")
        # Pero la ruta se conserva, para que la web la muestre preseleccionada.
        self.assertEqual(reloaded["sav_path"], str(self.save))

    def test_un_arranque_fallido_no_se_persiste(self):
        core = self._core()
        core.handle({"type": "start", "source": "sav", "config": {"sav_path": "/no/existe.sav"}})
        self.assertFalse(core.running)
        self.assertFalse(self.cfg_path.exists(),
                         "no debe guardar una configuración que no funciona")

    def test_cambiar_de_fuente_sobrescribe_la_anterior(self):
        core = self._core()
        core.handle({"type": "start", "source": "retroarch",
                     "config": {"game": "GBA — Esmeralda"}})
        core.handle({"type": "start", "source": "sav",
                     "config": {"sav_path": str(self.save), "sav_stable_for_s": 0.0}})
        core.close()
        reloaded = load_app_config(self.cfg_path)
        self.assertEqual(reloaded["source"], "sav")
        self.assertEqual(reloaded["game"], "GBA — Esmeralda", "el juego previo se conserva")

    def test_config_no_escribible_no_tumba_el_agente(self):
        """Si no se puede guardar, se avisa pero se sigue leyendo el equipo."""
        def explota(_updates):
            raise OSError("disco lleno")

        out: list[dict] = []
        core = AgentCore(self.cfg, send=out.append, publisher=FakePublisher(),
                         save_state=explota)
        with self.assertLogs("pvo.agent", level="WARNING") as logs:
            core.handle({"type": "start", "source": "sav",
                         "config": {"sav_path": str(self.save), "sav_stable_for_s": 0.0}})
        self.assertTrue(core.running)
        self.assertIn("disco lleno", "\n".join(logs.output))
        core.close()

    def test_sin_save_state_no_revienta(self):
        """El agente funciona igual aunque nadie le pase persistencia (tests, embebido)."""
        core = AgentCore(self.cfg, send=[].append, publisher=FakePublisher())
        core.handle({"type": "start", "source": "sav",
                     "config": {"sav_path": str(self.save), "sav_stable_for_s": 0.0}})
        self.assertTrue(core.running)
        core.close()


class TestConfigDeUsuario(unittest.TestCase):
    def test_el_fichero_guardado_se_relee_igual(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.yaml"
            cfg = normalize_config({"api_base": "https://a.b", "ingest_token": "xyz"})
            saved = persist_state(p, cfg, {"source": "sav", "sav_path": "/x.srm",
                                           "autostart": True})
            self.assertEqual(load_app_config(p), saved)

    def test_bridge_url_se_deriva_y_sobrevive(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.yaml"
            cfg = normalize_config({"api_base": "https://a.b", "ingest_token": "xyz"})
            persist_state(p, cfg, {"source": "sav", "sav_path": "/x.srm"})
            self.assertEqual(load_app_config(p)["bridge_url"],
                             "wss://a.b/api/stream-team/agent/xyz")


if __name__ == "__main__":
    unittest.main()
