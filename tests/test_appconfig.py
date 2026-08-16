import unittest

from pvo.appconfig import DEFAULT_CONFIG, bridge_url_for, normalize_config


class TestNormalizeConfig(unittest.TestCase):
    def test_none_gives_defaults(self):
        cfg = normalize_config(None)
        for k, v in DEFAULT_CONFIG.items():
            if k == "bridge_url":
                continue                      # derivado de api_base
            self.assertEqual(cfg[k], v, k)

    def test_overrides_applied(self):
        cfg = normalize_config({"api_base": "http://x", "ingest_token": "t",
                                "source": "retroarch"})
        self.assertEqual(cfg["api_base"], "http://x")
        self.assertEqual(cfg["source"], "retroarch")

    def test_missing_keys_filled(self):
        cfg = normalize_config({"api_base": "http://x"})
        self.assertEqual(cfg["ingest_token"], "")
        self.assertEqual(cfg["sav_path"], "")

    def test_api_base_sin_barra_final(self):
        self.assertEqual(normalize_config({"api_base": "https://x/"})["api_base"], "https://x")

    def test_interval_coerced_to_float(self):
        self.assertEqual(normalize_config({"publish_min_interval_s": "2"})["publish_min_interval_s"], 2.0)

    def test_bad_interval_falls_back(self):
        cfg = normalize_config({"publish_min_interval_s": "xx"})
        self.assertEqual(cfg["publish_min_interval_s"],
                         DEFAULT_CONFIG["publish_min_interval_s"])

    def test_puerto_coercionado(self):
        self.assertEqual(normalize_config({"retroarch_port": "55355"})["retroarch_port"], 55355)

    def test_fuente_desconocida_queda_vacia(self):
        """Vacío = "todavía no se ha elegido nada en la web"."""
        self.assertEqual(normalize_config({"source": "vision"})["source"], "")
        self.assertEqual(normalize_config(None)["source"], "")

    def test_no_queda_rastro_del_modo_sin_web(self):
        self.assertNotIn("bridge_enabled", normalize_config(None))

    def test_none_value_does_not_override(self):
        self.assertEqual(normalize_config({"sav_path": None})["sav_path"], "")


class TestBridgeUrl(unittest.TestCase):
    def test_https_da_wss(self):
        self.assertEqual(
            bridge_url_for("https://api.example.com", "tok"),
            "wss://api.example.com/api/stream-team/agent/tok",
        )

    def test_http_da_ws(self):
        self.assertEqual(
            bridge_url_for("http://localhost:3000", "tok"),
            "ws://localhost:3000/api/stream-team/agent/tok",
        )

    def test_derivada_en_normalize(self):
        cfg = normalize_config({"api_base": "https://a.b", "ingest_token": "xyz"})
        self.assertEqual(cfg["bridge_url"], "wss://a.b/api/stream-team/agent/xyz")

    def test_url_explicita_gana(self):
        cfg = normalize_config({"api_base": "https://a.b", "bridge_url": "wss://otro/x"})
        self.assertEqual(cfg["bridge_url"], "wss://otro/x")

    def test_sin_api_base_queda_vacia(self):
        self.assertEqual(bridge_url_for("", "tok"), "")


if __name__ == "__main__":
    unittest.main()
