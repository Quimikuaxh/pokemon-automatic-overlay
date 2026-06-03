import unittest

from pvo.learn import name_to_dex

NAMES = {"manectric": 310, "mr-mime": 122, "gardevoir": 282, "swampert": 260}


class TestNameToDex(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(name_to_dex("manectric", NAMES), 310)

    def test_case_insensitive(self):
        self.assertEqual(name_to_dex("MANECTRIC", NAMES), 310)

    def test_spaces_and_punctuation(self):
        self.assertEqual(name_to_dex("Mr. Mime", NAMES), 122)
        self.assertEqual(name_to_dex("mr mime", NAMES), 122)

    def test_dex_number_input(self):
        self.assertEqual(name_to_dex("260", NAMES), 260)

    def test_dex_number_out_of_range(self):
        self.assertIsNone(name_to_dex("9999", NAMES))

    def test_empty(self):
        self.assertIsNone(name_to_dex("   ", NAMES))

    def test_unknown(self):
        self.assertIsNone(name_to_dex("notapokemon", NAMES))


if __name__ == "__main__":
    unittest.main()
