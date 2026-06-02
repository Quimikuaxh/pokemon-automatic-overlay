import unittest

from pvo.state import SlotReading, TeamState


def reading(dex, score=0.95, nick=None):
    return SlotReading(dex_id=dex, species_score=score, nickname=nick)


class TestTeamState(unittest.TestCase):
    def test_valid_reading_updates_and_reports_change(self):
        st = TeamState(min_similarity=0.85)
        readings = [reading(25, nick="Pika")] + [reading(None)] * 5
        self.assertTrue(st.consider(readings))
        self.assertTrue(st.has_team)
        self.assertEqual(st.to_payload(), {
            "pokemonIds": [25, None, None, None, None, None],
            "nicknames": ["Pika", None, None, None, None, None],
        })

    def test_same_team_no_change(self):
        st = TeamState()
        readings = [reading(25)] + [reading(None)] * 5
        self.assertTrue(st.consider(readings))
        self.assertFalse(st.consider(readings))  # idéntico → sin cambio

    def test_low_score_slot_invalidates_reading(self):
        st = TeamState(min_similarity=0.85)
        readings = [reading(25, score=0.40)] + [reading(None)] * 5
        self.assertFalse(st.consider(readings))   # no fiable → se ignora
        self.assertFalse(st.has_team)

    def test_empty_slots_do_not_require_score(self):
        st = TeamState(min_similarity=0.85)
        readings = [reading(6), reading(None, score=0.0)] + [reading(None)] * 4
        self.assertTrue(st.consider(readings))

    def test_all_empty_is_invalid(self):
        st = TeamState()
        self.assertFalse(st.consider([reading(None)] * 6))

    def test_wrong_slot_count_invalid(self):
        st = TeamState()
        self.assertFalse(st.consider([reading(25)] * 5))

    def test_nickname_change_is_a_change(self):
        st = TeamState()
        st.consider([reading(25, nick="A")] + [reading(None)] * 5)
        self.assertTrue(st.consider([reading(25, nick="B")] + [reading(None)] * 5))


if __name__ == "__main__":
    unittest.main()
