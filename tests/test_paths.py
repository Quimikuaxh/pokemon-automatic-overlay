import unittest

from pvo import paths


class TestPaths(unittest.TestCase):
    def test_not_frozen_in_dev(self):
        self.assertFalse(paths.is_frozen())

    def test_data_dir_is_directory(self):
        self.assertTrue(paths.data_dir().is_dir())

    def test_config_path_under_data_dir(self):
        self.assertEqual(paths.config_path().parent, paths.data_dir())

    def test_log_path_under_data_dir(self):
        self.assertEqual(paths.log_path().parent, paths.data_dir())


if __name__ == "__main__":
    unittest.main()
