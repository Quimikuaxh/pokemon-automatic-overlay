import unittest

from pvo.profiles.schema import GameProfile


def valid_dict():
    return {
        "profile": "test",
        "reference_resolution": [240, 160],
        "capture": {"window_title_match": "mGBA", "fps": 3},
        "menu_detector": {"template": "t.png", "region": [0, 0, 240, 160]},
        "slots": [{"icon_region": [0, 0, 32, 32], "text_region": [40, 0, 64, 16]}] * 6,
        "species": {"embeddings": "e.npz", "min_similarity": 0.85},
        "ocr": {"engine": "easyocr", "lang": "es"},
    }


class TestSchema(unittest.TestCase):
    def test_valid(self):
        p = GameProfile.from_dict(valid_dict())
        self.assertEqual(p.name, "test")
        self.assertEqual(p.reference_resolution, (240, 160))
        self.assertEqual(len(p.slots), 6)
        self.assertEqual(p.slots[0].icon_region, (0, 0, 32, 32))

    def test_requires_six_slots(self):
        d = valid_dict()
        d["slots"] = d["slots"][:5]
        with self.assertRaises(ValueError):
            GameProfile.from_dict(d)

    def test_capture_needs_window_or_region(self):
        d = valid_dict()
        d["capture"] = {"fps": 3}
        with self.assertRaises(ValueError):
            GameProfile.from_dict(d)

    def test_bad_region_rejected(self):
        d = valid_dict()
        d["menu_detector"]["region"] = [0, 0, 0, 160]  # ancho 0
        with self.assertRaises(ValueError):
            GameProfile.from_dict(d)

    def test_missing_species_embeddings(self):
        d = valid_dict()
        d["species"] = {"min_similarity": 0.9}
        with self.assertRaises(ValueError):
            GameProfile.from_dict(d)

    def test_viewport_auto_default(self):
        p = GameProfile.from_dict(valid_dict())
        self.assertEqual(p.capture.viewport, "auto")

    def test_viewport_fractional(self):
        d = valid_dict()
        d["capture"]["viewport"] = [0, 0.5, 1, 0.5]  # mitad inferior (NDS)
        p = GameProfile.from_dict(d)
        self.assertEqual(p.capture.viewport, (0.0, 0.5, 1.0, 0.5))

    def test_text_region_optional(self):
        d = valid_dict()
        d["slots"] = [{"icon_region": [0, 0, 32, 32]}] * 6
        p = GameProfile.from_dict(d)
        self.assertIsNone(p.slots[0].text_region)

    def test_resolve_relative_path(self):
        from pathlib import Path
        p = GameProfile.from_dict(valid_dict(), base_dir=Path("/profiles"))
        self.assertEqual(p.resolve("e.npz"), Path("/profiles/e.npz"))


if __name__ == "__main__":
    unittest.main()
