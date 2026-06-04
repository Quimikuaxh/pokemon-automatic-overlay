import unittest

from pvo.autolocate import name_to_dex

NAMES = {"manectric": 310, "breloom": 286, "mr-mime": 122, "gardevoir": 282}


class TestNameToDex(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(name_to_dex("breloom", NAMES), 286)

    def test_case_and_spaces(self):
        self.assertEqual(name_to_dex("MANECTRIC", NAMES), 310)
        self.assertEqual(name_to_dex("Mr Mime", NAMES), 122)

    def test_dex_number(self):
        self.assertEqual(name_to_dex("282", NAMES), 282)

    def test_unknown(self):
        self.assertIsNone(name_to_dex("nope", NAMES))

    def test_empty(self):
        self.assertIsNone(name_to_dex("  ", NAMES))


if __name__ == "__main__":
    unittest.main()
