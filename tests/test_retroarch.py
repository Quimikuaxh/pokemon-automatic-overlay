import unittest

from pvo.memory.retroarch import parse_read_response


class TestParse(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_read_response("READ_CORE_MEMORY 20244ec 25 00 ff"),
                         bytes([0x25, 0x00, 0xFF]))

    def test_error_minus_one(self):
        with self.assertRaises(IOError):
            parse_read_response("READ_CORE_MEMORY 20244ec -1")

    def test_unexpected(self):
        with self.assertRaises(IOError):
            parse_read_response("garbage response")


if __name__ == "__main__":
    unittest.main()
