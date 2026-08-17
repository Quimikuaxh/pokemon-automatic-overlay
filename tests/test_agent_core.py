import tempfile
import unittest
from pathlib import Path

import savefixtures as fx
from pvo.agent.core import AgentCore
from pvo.publisher import Publisher


class FakePublisher(Publisher):
    """Publisher que no toca la red y recuerda lo publicado."""

    def __init__(self):
        self.sent: list[dict] = []
        super().__init__("http://test", "token", post_fn=self._post, min_interval_s=0.0)

    def _post(self, url, body):
        self.sent.append(body)
        return 200


class Harness:
    def __init__(self, **cfg):
        self.out: list[dict] = []
        self.publisher = FakePublisher()
        base = {"api_base": "http://test", "ingest_token": "token"}
        self.core = AgentCore({**base, **cfg}, send=self.out.append,
                              publisher=self.publisher)

    def types(self):
        return [m["type"] for m in self.out]

    def last(self, kind):
        for m in reversed(self.out):
            if m["type"] == kind:
                return m
        return None


class TestHandshake(unittest.TestCase):
    def test_hello_declara_capacidades(self):
        h = Harness()
        hello = h.core.hello()
        self.assertEqual(hello["type"], "hello")
        self.assertEqual(hello["token"], "token")
        self.assertEqual(hello["capabilities"]["sources"], ["sav", "retroarch"])
        self.assertIn("GBA — Esmeralda", hello["capabilities"]["games"])
        keys = [f["key"] for f in hello["capabilities"]["savFormats"]]
        self.assertEqual(keys, ["gba_gen3", "nds_gen45", "3ds_gen67"])

    def test_get_status_responde_con_request_id(self):
        h = Harness()
        h.core.handle({"type": "get_status", "requestId": "r1"})
        msg = h.last("status")
        self.assertEqual(msg["requestId"], "r1")
        self.assertFalse(msg["running"])

    def test_ping_pong(self):
        h = Harness()
        h.core.handle({"type": "ping", "requestId": "p"})
        self.assertEqual(h.last("pong")["requestId"], "p")

    def test_comando_desconocido_devuelve_error(self):
        h = Harness()
        h.core.handle({"type": "explota"})
        self.assertIn("explota", h.last("error")["message"])

    def test_mensaje_no_dict_se_ignora(self):
        h = Harness()
        h.core.handle("basura")          # type: ignore[arg-type]
        self.assertEqual(h.out, [])


class TestStartStop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.save = Path(self.tmp.name) / "esmeralda.srm"
        self.save.write_bytes(fx.gba_save([282, 310], ["GARDE", "MANEC"]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_arranca_sav_publica_y_avisa(self):
        h = Harness()
        h.core.handle({"type": "start", "source": "sav",
                       "config": {"sav_path": str(self.save),
                                  "sav_poll_interval_s": 0.05,
                                  "sav_stable_for_s": 0.0}})
        self.assertTrue(h.core.running)

        # El watcher es asíncrono: se fuerza una pasada determinista.
        h.core._source._watcher.poll_once()

        team = h.last("team")
        self.assertEqual(team["pokemonIds"], [282, 310, None, None, None, None])
        self.assertEqual(team["source"], "sav")
        self.assertEqual(h.publisher.sent[-1]["pokemonIds"][:2], [282, 310])

        h.core.handle({"type": "stop"})
        self.assertFalse(h.core.running)
        self.assertFalse(h.last("status")["running"])

    def test_start_sin_ruta_da_error_y_no_arranca(self):
        h = Harness()
        h.core.handle({"type": "start", "source": "sav", "config": {}, "requestId": "x"})
        self.assertFalse(h.core.running)
        self.assertIn("sav_path", h.last("error")["message"])
        self.assertEqual(h.last("status")["error"], h.last("error")["message"])

    def test_start_con_ruta_inexistente_da_error(self):
        h = Harness()
        h.core.handle({"type": "start", "source": "sav",
                       "config": {"sav_path": "/no/existe.sav"}})
        self.assertFalse(h.core.running)
        self.assertIn("No existe", h.last("error")["message"])

    def test_fuente_desconocida(self):
        h = Harness()
        h.core.handle({"type": "start", "source": "vision", "config": {}})
        self.assertIn("desconocida", h.last("error")["message"])

    def test_juego_desconocido_en_retroarch(self):
        h = Harness()
        h.core.handle({"type": "start", "source": "retroarch",
                       "config": {"game": "GBA — Inexistente"}})
        self.assertIn("desconocido", h.last("error")["message"])

    def test_start_reemplaza_la_fuente_anterior(self):
        h = Harness()
        cfg = {"sav_path": str(self.save), "sav_poll_interval_s": 0.05,
               "sav_stable_for_s": 0.0}
        h.core.handle({"type": "start", "source": "sav", "config": cfg})
        first = h.core._source
        h.core.handle({"type": "start", "source": "sav", "config": cfg})
        self.assertIsNot(h.core._source, first)
        h.core.close()


class TestDeteccion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_save_ok(self):
        p = self.dir / "platino.sav"
        p.write_bytes(fx.nds_save([487, 483], gen=4))
        h = Harness()
        h.core.handle({"type": "inspect_save", "path": str(p), "requestId": "i"})
        cand = h.last("saves")["candidates"][0]
        self.assertEqual(cand["parserKey"], "nds_gen45")
        self.assertEqual(cand["teamCount"], 2)

    def test_inspect_save_no_reconocido(self):
        p = self.dir / "cosa.sav"
        p.write_bytes(bytes(0x20000))
        h = Harness()
        h.core.handle({"type": "inspect_save", "path": str(p)})
        self.assertIn("no se reconoce", h.last("error")["message"])

    def test_inspect_savestate_avisa(self):
        p = self.dir / "juego.state"
        p.write_bytes(b"RASTATE" + bytes(4096))
        h = Harness()
        h.core.handle({"type": "inspect_save", "path": str(p)})
        self.assertIsNotNone(h.last("error"))


if __name__ == "__main__":
    unittest.main()
