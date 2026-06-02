import tempfile
import unittest
from pathlib import Path

from pvo.appconfig import DEFAULT_CONFIG, list_profiles, normalize_config


class TestNormalizeConfig(unittest.TestCase):
    def test_none_gives_defaults(self):
        self.assertEqual(normalize_config(None), DEFAULT_CONFIG)

    def test_overrides_applied(self):
        cfg = normalize_config({"api_base": "http://x", "ingest_token": "t", "profile": "p"})
        self.assertEqual(cfg["api_base"], "http://x")
        self.assertEqual(cfg["profile"], "p")

    def test_missing_keys_filled(self):
        cfg = normalize_config({"api_base": "http://x"})
        self.assertEqual(cfg["ingest_token"], "")
        self.assertEqual(cfg["profile"], "")

    def test_interval_coerced_to_float(self):
        cfg = normalize_config({"publish_min_interval_s": "2"})
        self.assertEqual(cfg["publish_min_interval_s"], 2.0)

    def test_bad_interval_falls_back(self):
        cfg = normalize_config({"publish_min_interval_s": "xx"})
        self.assertEqual(cfg["publish_min_interval_s"], DEFAULT_CONFIG["publish_min_interval_s"])

    def test_none_value_does_not_override(self):
        cfg = normalize_config({"profile": None})
        self.assertEqual(cfg["profile"], "")


class TestListProfiles(unittest.TestCase):
    def test_lists_yaml_stems_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "gba_emerald.yaml").write_text("x")
            (base / "nds_platinum.yaml").write_text("x")
            (base / "notes.txt").write_text("x")
            self.assertEqual(list_profiles(base), ["gba_emerald", "nds_platinum"])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(list_profiles("/no/such/dir/really"), [])


if __name__ == "__main__":
    unittest.main()
