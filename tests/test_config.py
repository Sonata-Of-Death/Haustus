# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from core.config import ConfigManager

sys.path.insert(0, os.path.dirname(__file__))

class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.cfg = ConfigManager(self.cfg_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_default_output_dir_initialized(self):
        def_dir = self.cfg.get_default_output_dir()
        self.assertTrue(os.path.basename(def_dir) == "HaustusDownloads")
        self.assertIn(def_dir, self.cfg.get_output_dirs())

    def test_add_and_set_default_output_dir(self):
        custom = os.path.join(self.tmp_dir.name, "custom_downloads")
        self.cfg.add_output_dir(custom, set_as_default=True)
        self.assertEqual(os.path.abspath(custom), self.cfg.get_default_output_dir())
        self.assertIn(os.path.abspath(custom), self.cfg.get_output_dirs())

    def test_links_files_management(self):
        test_file = os.path.join(self.tmp_dir.name, "my_links.txt")
        with open(test_file, "w") as f:
            f.write("https://www.youtube.com/watch?v=dQw4w9WgXcQ\n")

        self.cfg.add_links_file(test_file, set_as_default=True)
        self.assertEqual(os.path.abspath(test_file), self.cfg.get_default_links_file())
        self.assertIn(os.path.abspath(test_file), self.cfg.get_links_files())

        self.cfg.remove_links_file(test_file)
        self.assertNotIn(os.path.abspath(test_file), self.cfg.get_links_files())
        self.assertIsNone(self.cfg.get_default_links_file())

    def test_cookie_profiles_crud(self):
        cookie_file = os.path.join(self.tmp_dir.name, "yt_test.txt")
        with open(cookie_file, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")

        initial_count = len(self.cfg.get_cookie_profiles("youtube"))
        # 1. Add
        self.cfg.add_cookie_profile("youtube", "Work Account", cookie_file, set_as_default=True)
        self.assertEqual(self.cfg.get_default_cookie_profile_name("youtube"), "Work Account")
        eff = self.cfg.get_effective_cookie_file("youtube")
        self.assertTrue(os.path.isfile(eff))
        with open(eff, "r") as f:
            self.assertIn("# Netscape HTTP Cookie File", f.read())

        # 2. Add second
        cookie_file2 = os.path.join(self.tmp_dir.name, "yt_test2.txt")
        with open(cookie_file2, "w") as f:
            f.write("# Netscape HTTP Cookie File 2\n")
        self.cfg.add_cookie_profile("youtube", "Personal Account", cookie_file2, set_as_default=False)
        self.assertEqual(len(self.cfg.get_cookie_profiles("youtube")), initial_count + 2)

        # 3. Edit / Rename
        self.cfg.edit_cookie_profile_name("youtube", "Work Account", "Primary Account")
        self.assertEqual(self.cfg.get_default_cookie_profile_name("youtube"), "Primary Account")

        # 4. Delete
        self.cfg.delete_cookie_profile("youtube", "Primary Account")
        profiles = self.cfg.get_cookie_profiles("youtube")
        self.assertEqual(len(profiles), initial_count + 1)
        self.assertIn("Personal Account", [p["name"] for p in profiles])

    def test_quality_defaults(self):
        self.cfg.set_default_mode("video")
        self.assertEqual(self.cfg.get_default_mode(), "video")

        self.cfg.set_default_video_quality("1080")
        self.assertEqual(self.cfg.get_default_video_quality(), "1080")

        self.cfg.set_default_audio_format("opus")
        self.assertEqual(self.cfg.get_default_audio_format(), "opus")

        self.cfg.set_default_audio_quality("320")
        self.assertEqual(self.cfg.get_default_audio_quality(), "320")

    def test_internal_session_isolation(self):
        f = self.cfg.save_internal_session("tiktok", "@test_user", "sample_token_value", set_as_default=True)
        self.assertTrue(os.path.isfile(f))
        self.assertNotIn(os.path.abspath("."), os.path.dirname(os.path.abspath(f)))
        profiles = self.cfg.get_cookie_profiles("tiktok")
        self.assertIn("@test_user", [p["name"] for p in profiles])
        # Verify removal deletes the session file
        self.cfg.delete_cookie_profile("tiktok", "@test_user")
        self.assertFalse(os.path.isfile(f))

    def test_json_first_cookie_storage(self):
        netscape_sample = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tTEST_KEY\tTEST_VAL\n"
        self.cfg.add_cookie_profile("youtube", "@json_test_user", netscape_sample, set_as_default=True)
        # Verify stored in JSON data
        raw_data = self.cfg.get_effective_cookie_data("youtube")
        self.assertIn("TEST_KEY", raw_data)
        # Verify in-memory cookie jar loading
        jar = self.cfg.get_effective_cookie_jar("youtube")
        self.assertIsNotNone(jar)
        cookie_names = [c.name for c in jar]
        self.assertIn("TEST_KEY", cookie_names)
        # Verify config.json on disk does not store ephemeral "file" pointers
        with open(self.cfg.config_path, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        for prof in persisted.get("cookies", {}).get("youtube", {}).get("profiles", []):
            self.assertNotIn("file", prof)
            if prof.get("name") == "@json_test_user":
                self.assertIn("data", prof)
        # Clean up
        self.cfg.delete_cookie_profile("youtube", "@json_test_user")
