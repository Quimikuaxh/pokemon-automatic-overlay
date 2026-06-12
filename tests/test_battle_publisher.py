import unittest

from pvo.champions.publisher import BattlePublisher


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TestBattlePublisher(unittest.TestCase):
    def _make(self, min_interval=0.0):
        sent = []
        clock = FakeClock()
        pub = BattlePublisher(
            api_base="https://x.test/",
            token="abcdefgh1234",
            post_fn=lambda url, body: (sent.append((url, body)) or 200),
            min_interval_s=min_interval,
            clock=clock,
        )
        return pub, sent, clock

    def test_posts_to_battle_endpoint(self):
        pub, sent, _ = self._make()
        ok = pub.publish({"phase": 1, "mode": "Doubles", "rivals": [3], "turn": 1})
        self.assertTrue(ok)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "https://x.test/api/stream-team/battle/abcdefgh1234")

    def test_no_resend_when_only_turn_changes(self):
        pub, sent, _ = self._make()
        pub.publish({"phase": 2, "mode": "Doubles", "rivals": [3], "activeAllies": [6],
                     "activeRivals": [3], "turn": 1})
        # mismo contenido, solo turn distinto → no se reenvía
        sent_again = pub.publish({"phase": 2, "mode": "Doubles", "rivals": [3], "activeAllies": [6],
                                  "activeRivals": [3], "turn": 2})
        self.assertFalse(sent_again)
        self.assertEqual(len(sent), 1)

    def test_resend_when_content_changes(self):
        pub, sent, _ = self._make()
        pub.publish({"phase": 2, "mode": "Doubles", "activeAllies": [6], "turn": 1})
        pub.publish({"phase": 2, "mode": "Doubles", "activeAllies": [7], "turn": 2})
        self.assertEqual(len(sent), 2)

    def test_debounce_blocks_rapid_change(self):
        pub, sent, clock = self._make(min_interval=1.0)
        pub.publish({"phase": 1, "rivals": [3], "turn": 1})
        clock.t = 0.5
        blocked = pub.publish({"phase": 1, "rivals": [4], "turn": 2})
        self.assertFalse(blocked)
        clock.t = 1.6
        ok = pub.publish({"phase": 1, "rivals": [4], "turn": 3})
        self.assertTrue(ok)

    def test_404_returns_false(self):
        pub = BattlePublisher("https://x.test", "tok12345", post_fn=lambda u, b: 404)
        self.assertFalse(pub.publish({"phase": 1, "rivals": [3], "turn": 1}))


if __name__ == "__main__":
    unittest.main()
