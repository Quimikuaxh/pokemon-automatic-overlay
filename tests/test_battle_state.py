import unittest

from pvo.champions.state import BattleState


class TestBattleState(unittest.TestCase):
    def test_selection_publishes_phase1_on_change(self):
        st = BattleState(mode="Doubles")
        p = st.consider_selection([3, 884, 561])
        self.assertIsNotNone(p)
        self.assertEqual(p["phase"], 1)
        self.assertEqual(p["mode"], "Doubles")
        self.assertEqual(p["rivals"], [3, 884, 561])
        self.assertEqual(p["activeAllies"], [])
        self.assertEqual(p["activeRivals"], [])
        self.assertEqual(p["turn"], 1)

    def test_selection_no_change_returns_none(self):
        st = BattleState()
        st.consider_selection([3, 884])
        self.assertIsNone(st.consider_selection([3, 884]))

    def test_battle_publishes_phase2_and_carries_rivals(self):
        st = BattleState(mode="Doubles")
        st.consider_selection([3, 884, 561, 700])
        p = st.consider_battle([6, 547], [884, 561])
        self.assertIsNotNone(p)
        self.assertEqual(p["phase"], 2)
        self.assertEqual(p["activeAllies"], [6, 547])
        self.assertEqual(p["activeRivals"], [884, 561])
        # los rivales de selección se mantienen en el payload de fase 2
        self.assertEqual(p["rivals"], [3, 884, 561, 700])

    def test_battle_no_change_returns_none(self):
        st = BattleState()
        st.consider_battle([6], [884])
        self.assertIsNone(st.consider_battle([6], [884]))

    def test_turn_increments_on_each_change(self):
        st = BattleState()
        self.assertEqual(st.consider_selection([1])["turn"], 1)
        self.assertEqual(st.consider_battle([1], [2])["turn"], 2)
        self.assertEqual(st.consider_battle([1], [3])["turn"], 3)

    def test_active_change_detected(self):
        st = BattleState()
        st.consider_battle([6, 547], [884, 561])
        p = st.consider_battle([6, 547], [884, 700])  # cambió un rival activo
        self.assertIsNotNone(p)
        self.assertEqual(p["activeRivals"], [884, 700])


if __name__ == "__main__":
    unittest.main()
