import unittest

from pvo.publisher import Publisher


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestPublisher(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.clock = FakeClock()

        def post(url, body):
            self.calls.append((url, body))
            return 200

        self.post = post

    def make(self, min_interval=1.0):
        return Publisher(
            api_base="https://api.test/",
            ingest_token="tok-123",
            post_fn=self.post,
            min_interval_s=min_interval,
            clock=self.clock,
        )

    def test_url_built_correctly(self):
        pub = self.make()
        pub.publish({"pokemonIds": [1]})
        self.assertEqual(self.calls[0][0], "https://api.test/api/stream-team/ingest/tok-123")

    def test_publishes_only_on_change(self):
        pub = self.make(min_interval=0.0)
        payload = {"pokemonIds": [25], "nicknames": [None]}
        self.assertTrue(pub.publish(payload))
        self.assertFalse(pub.publish(payload))  # mismo payload → no repite
        self.assertEqual(len(self.calls), 1)

    def test_change_triggers_new_post(self):
        pub = self.make(min_interval=0.0)
        self.assertTrue(pub.publish({"pokemonIds": [25]}))
        self.assertTrue(pub.publish({"pokemonIds": [26]}))
        self.assertEqual(len(self.calls), 2)

    def test_debounce_blocks_rapid_changes(self):
        pub = self.make(min_interval=5.0)
        self.assertTrue(pub.publish({"pokemonIds": [1]}))
        self.clock.t += 1.0  # < intervalo
        self.assertFalse(pub.publish({"pokemonIds": [2]}))
        self.clock.t += 5.0  # supera intervalo
        self.assertTrue(pub.publish({"pokemonIds": [2]}))

    def test_force_ignores_debounce_and_signature(self):
        pub = self.make(min_interval=99.0)
        pub.publish({"pokemonIds": [1]})
        self.assertTrue(pub.publish({"pokemonIds": [1]}, force=True))

    def test_network_exception_is_caught(self):
        def post(url, body):
            raise ConnectionError("sin red")

        pub = Publisher("https://api.test", "tok", post_fn=post, min_interval_s=0.0, clock=self.clock)
        self.assertFalse(pub.publish({"pokemonIds": [1]}))  # no debe lanzar
        self.assertFalse(pub.publish({"pokemonIds": [1]}))  # tampoco cachea → reintenta

    def test_non_2xx_does_not_cache_signature(self):
        calls = []

        def post(url, body):
            calls.append(body)
            return 500

        pub = Publisher("https://api.test", "tok", post_fn=post, min_interval_s=0.0, clock=self.clock)
        self.assertFalse(pub.publish({"pokemonIds": [1]}))
        self.assertFalse(pub.publish({"pokemonIds": [1]}))  # reintenta porque no se cacheó
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
