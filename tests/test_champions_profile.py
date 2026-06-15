import unittest
from pathlib import Path

from pvo.champions.profile import ChampionsProfile


def _valid() -> dict:
    return {
        "profile": "champions",
        "reference_resolution": [1280, 720],
        "mode": "Doubles",
        "capture": {"window_title_match": "Windowed Projector", "viewport": "auto", "aspect_ratio": 1.7778},
        "species": {"gallery": "../../assets/icons/champions/templates.npz", "min_similarity": 0.45},
        "screens": {
            "selection": {"template": "t/sel.png", "region": [0, 0, 1280, 720]},
            "battle": {"template": "t/bat.png", "region": [0, 0, 1280, 720]},
        },
        "selection": {"rival_slots": [[1, 1, 10, 10]] * 6},
        "battle": {
            "ally_slots": [[1, 1, 10, 10], [2, 2, 10, 10]],
            "rival_slots": [[3, 3, 10, 10], [4, 4, 10, 10]],
        },
    }


class TestChampionsProfile(unittest.TestCase):
    def test_valid_parses(self):
        p = ChampionsProfile.from_dict(_valid(), base_dir=Path("/profiles"))
        self.assertEqual(p.name, "champions")
        self.assertEqual(p.reference_resolution, (1280, 720))
        self.assertEqual(p.mode, "Doubles")
        self.assertEqual(len(p.selection_rival_slots), 6)
        self.assertEqual(len(p.battle_ally_slots), 2)
        self.assertEqual(len(p.battle_rival_slots), 2)
        self.assertIn("selection", p.screens)
        self.assertEqual(p.species.min_similarity, 0.45)

    def test_resolve_relative(self):
        p = ChampionsProfile.from_dict(_valid(), base_dir=Path("/profiles"))
        self.assertEqual(p.resolve("t/sel.png"), Path("/profiles/t/sel.png"))

    def test_duck_types_for_species_matcher(self):
        # SpeciesMatcher solo usa profile.resolve(profile.species.gallery)
        p = ChampionsProfile.from_dict(_valid(), base_dir=Path("/profiles"))
        self.assertTrue(str(p.resolve(p.species.gallery)).endswith("templates.npz"))

    def test_screens_are_optional(self):
        # La clasificación de pantalla es por contenido; 'screens' ya no es obligatorio.
        d = _valid()
        del d["screens"]
        p = ChampionsProfile.from_dict(d)
        self.assertEqual(p.screens, {})

    def test_missing_rival_slots_raises(self):
        d = _valid()
        d["selection"]["rival_slots"] = []
        with self.assertRaises(ValueError):
            ChampionsProfile.from_dict(d)

    def test_missing_active_slots_raises(self):
        d = _valid()
        d["battle"]["ally_slots"] = []
        with self.assertRaises(ValueError):
            ChampionsProfile.from_dict(d)


if __name__ == "__main__":
    unittest.main()
