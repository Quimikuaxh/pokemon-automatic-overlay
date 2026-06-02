import unittest
from pathlib import Path

from pvo import paths


class TestPaths(unittest.TestCase):
    def test_not_frozen_in_dev(self):
        self.assertFalse(paths.is_frozen())

    def test_data_dir_is_directory(self):
        self.assertTrue(paths.data_dir().is_dir())

    def test_bundled_profiles_has_example(self):
        # El ejemplo gba_emerald viaja dentro del paquete.
        self.assertTrue((paths.bundled_profiles_dir() / "gba_emerald.yaml").exists())

    def test_config_path_under_data_dir(self):
        self.assertEqual(paths.config_path().parent, paths.data_dir())


if __name__ == "__main__":
    unittest.main()
