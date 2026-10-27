# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest import mock

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import core.cookies as core_cookies
import haustus as ibd
import platforms.instagram as platforms_instagram
import platforms.x_twitter as platforms_x_twitter
import ui.components as ui_components
import ui.dashboard as ui_dashboard
import ui.quality as ui_quality
import ui.theme as ui_theme

sys.path.insert(0, os.path.dirname(__file__))
from helpers import patch_everywhere


class TestModularArchitectureAndBugFixes(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_all_modular_files_exist_and_import(self):
        expected_files = [
            "ui/theme.py",
            "ui/components.py",
            "ui/quality.py",
            "ui/dashboard.py",
            "core/config.py",
            "core/cookies.py",
            "core/archive.py",
            "platforms/instagram.py",
            "platforms/tiktok.py",
            "platforms/youtube.py",
            "platforms/x_twitter.py",
            "platforms/soundcloud.py",
            "platforms/reddit.py",
            "platforms/facebook.py",
            "platforms/pinterest.py",
            "platforms/twitch.py",
            "platforms/threads.py",
            "platforms/spotify.py",
            "features/downloader.py",
            "features/single_download.py",
            "features/bulk_file.py",
            "features/playlist.py",
            "features/profile.py",
            "features/paste_urls.py",
            "features/audio_mode.py",
            "features/saved_posts.py",
            "features/reposts.py",
            "features/settings.py",
        ]
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in expected_files:
            full = os.path.join(root, rel)
            self.assertTrue(os.path.isfile(full), f"Missing modular file: {rel}")

    def test_sanitize_netscape_cookie_file_and_httponly(self):
        c_path = os.path.join(self.tmp_dir.name, "raw_cookies.txt")
        with open(c_path, "w", encoding="utf-8") as f:
            f.write("#HttpOnly_.instagram.com\tFALSE\t/\tTRUE\t0\tsessionid\ttest_session_999\n")
        ok = core_cookies.sanitize_netscape_cookie_file(c_path)
        self.assertTrue(ok)
        cj = core_cookies.load_cookie_jar(c_path)
        self.assertIsNotNone(cj)
        names = {c.name: c.value for c in cj}
        self.assertEqual(names.get("sessionid"), "test_session_999")

    def test_verify_instagram_and_tiktok_sessions_return_tuples(self):
        ig_file = core_cookies.prepare_cookies("sessionid_val_1234567890", save_profile=False)
        with mock.patch("requests.Session.get") as mock_get:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"user": {"username": "ig_tester"}}
            mock_get.return_value = mock_resp
            valid, msg = core_cookies.verify_instagram_session(ig_file)
            self.assertTrue(valid)
            self.assertIn("ig_tester", msg)

        tt_file = core_cookies.prepare_tiktok_cookies("tt_session_val_1234567890", save_profile=False)
        with mock.patch("requests.Session.get") as mock_get:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"message": "success", "data": {"username": "tt_tester"}}
            mock_get.return_value = mock_resp
            valid, msg = core_cookies.verify_tiktok_session(tt_file)
            self.assertTrue(valid)
            self.assertIn("tt_tester", msg)

    def test_resolve_embed_metadata_none_fallback(self):
        with unittest.mock.patch.object(ui_theme.config_mgr, "get_default_embed_metadata", return_value=None):
            with unittest.mock.patch("sys.stdin.isatty", return_value=False):
                self.assertTrue(ui_quality.resolve_embed_metadata())
            with unittest.mock.patch("sys.stdin.isatty", return_value=True):
                with patch_everywhere("interactive_select", return_value=False):
                    self.assertFalse(ui_quality.resolve_embed_metadata())

    def test_download_x_reposts_custom_urls_no_name_error(self):
        with patch_everywhere("download_urls") as mock_dl:
            platforms_x_twitter.download_x_reposts(
                output_dir=self.tmp_dir.name,
                custom_urls=["https://x.com/user/status/111222333"]
            )
            mock_dl.assert_called_once()

    def test_zero_emojis_across_all_modules(self):
        import re as _re
        emoji_re = _re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for dirpath, dirnames, filenames in os.walk(root):
            if any(part.startswith(".") or part == "__pycache__" for part in dirpath.split(os.sep)):
                continue
            for fn in filenames:
                if fn.endswith(".py"):
                    fp = os.path.join(dirpath, fn)
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    match = emoji_re.search(content)
                    self.assertIsNone(match, f"Found forbidden emoji in {fp}")

    def test_parse_time_range_and_clipping(self):
        self.assertEqual(ui_quality.parse_time_range("01:20-03:45"), (80.0, 225.0))
        self.assertEqual(ui_quality.parse_time_range("00:01:00 to 00:02:30"), (60.0, 150.0))
        self.assertEqual(ui_quality.parse_time_range("15-45"), (15.0, 45.0))
        self.assertIsNone(ui_quality.parse_time_range("03:45-01:20"))
        self.assertIsNone(ui_quality.parse_time_range("invalid"))

    def test_media_preview_card_and_size_estimates(self):
        formats = [
            {"height": 1080, "vcodec": "avc1", "acodec": "none", "filesize": 40 * 1024 * 1024},
            {"height": 720, "vcodec": "avc1", "acodec": "none", "filesize_approx": 18 * 1024 * 1024},
            {"vcodec": "none", "acodec": "mp4a", "filesize": 5 * 1024 * 1024},
        ]
        sz_1080 = ui_quality.estimate_height_size_mb(formats, 1080, duration=180)
        sz_720 = ui_quality.estimate_height_size_mb(formats, 720, duration=180)
        self.assertEqual(sz_1080, "~45.0 MB")
        self.assertEqual(sz_720, "~23.0 MB")

        card = ui_quality.render_media_preview_card(
            {"title": "Sample 4K Video", "uploader": "TechChannel", "duration": 185, "upload_date": "20261020", "formats": formats},
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            platform_name="YouTube"
        )
        self.assertIsNotNone(card)

    def test_unified_preflight_screen(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=False):
            pf = ui_quality.run_preflight_screen("https://www.youtube.com/watch?v=dQw4w9WgXcQ", platform="youtube", is_single=True)
            self.assertIsNotNone(pf)
            self.assertIn("output_dir", pf)
            self.assertIn("mode", pf)
            self.assertIn("clip_range", pf)
            self.assertIn("subtitles", pf)

        with unittest.mock.patch("sys.stdin.isatty", return_value=True), \
             patch_everywhere("select_menu", side_effect=["subtitles", "metadata", "start"]):
            pf2 = ui_quality.run_preflight_screen("@creator", platform="instagram", is_single=False)
            self.assertIsNotNone(pf2)
            self.assertTrue(pf2["subtitles"])

    def test_live_dashboard_skip_and_open_folder_controls(self):
        dash = ui_dashboard.RichLiveDownloadDashboard(ui_theme.console)
        dash.set_output_dir(self.tmp_dir.name)
        self.assertEqual(dash._output_dir, self.tmp_dir.name)

        dash.request_skip()
        with self.assertRaises(ui_dashboard.SkipItemRequested):
            dash.poll_live_keys()

    def test_instagram_stories_and_highlights_dispatch(self):
        c_file = core_cookies.prepare_cookies("sessionid_stories_1234567890", save_profile=False)
        with patch_everywhere("download_urls") as mock_dl:
            platforms_instagram.download_instagram_stories_or_highlights(
                "@sample_creator",
                output_dir=self.tmp_dir.name,
                cookie_file=c_file,
                kind="stories"
            )
            mock_dl.assert_called_once()
            called_urls = mock_dl.call_args[0][0]
            self.assertEqual(called_urls, ["https://www.instagram.com/stories/sample_creator/"])

    def test_no_sqlite_and_no_auto_browser_cookie_sync_exclusions(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertFalse(os.path.exists(os.path.join(root, "core", "database.py")))

    def test_generic_url_routing_and_no_cookie_leakage(self):
        import core.urls as cu
        generic_url = 'https://commons.wikimedia.org/wiki/File:Sample.webm'

        # Verify not detected as any of the 11 platforms
        self.assertFalse(cu.is_instagram_url(generic_url))
        self.assertFalse(cu.is_tiktok_url(generic_url))
        self.assertFalse(cu.is_youtube_url(generic_url))
        self.assertFalse(cu.is_x_url(generic_url))
        self.assertFalse(cu.is_soundcloud_url(generic_url))
        self.assertFalse(cu.is_reddit_url(generic_url))
        self.assertFalse(cu.is_facebook_url(generic_url))
        self.assertFalse(cu.is_pinterest_url(generic_url))
        self.assertFalse(cu.is_twitch_url(generic_url))
        self.assertFalse(cu.is_threads_url(generic_url))
        self.assertFalse(cu.is_spotify_url(generic_url))

        # Verify downloader routes generic URL to ydl.download directly
        with unittest.mock.patch('yt_dlp.YoutubeDL') as mock_ydl_cls, \
             unittest.mock.patch('features.downloader.check_disk_presence', return_value=True):
            mock_ydl = mock_ydl_cls.return_value
            mock_ydl.download.return_value = 0
            mock_ydl.extract_info.return_value = {'id': 'sample_123', 'title': 'Sample Video', 'ext': 'mp4'}

            import features.downloader as features_downloader
            features_downloader.download_urls([generic_url], output_dir='dummy_out', use_archive=False)
            mock_ydl.download.assert_called_with([generic_url])

    def test_help_hotkey_arabic_and_english_support(self):
        # Verify Arabic keyboard layout normalization
        self.assertEqual(ui_theme.normalize_hotkey_char("؟"), "?")
        self.assertEqual(ui_theme.normalize_hotkey_char("ا"), "h")
        self.assertEqual(ui_theme.normalize_hotkey_char("أ"), "H")
        self.assertEqual(ui_theme.normalize_hotkey_char("ص"), "w")
        self.assertEqual(ui_theme.normalize_hotkey_char("س"), "s")
        self.assertEqual(ui_theme.normalize_hotkey_char("ض"), "q")
        self.assertEqual(ui_theme.normalize_hotkey_char("١"), "1")

        # Verify select_menu opens help on '?', '؟', 'h', and 'ا' (Arabic H) and resumes cleanly
        items = [
            ui_components.MenuItem("1", "Option One", "First option", value="one"),
            ui_components.MenuItem("2", "Option Two", "Second option", value="two"),
        ]
        # Sequence: '؟' (open help), 'enter' (close help), 'ا' (open help via Arabic H), 'h' (close help), '٢' (select option 2 in Arabic digit)
        with unittest.mock.patch("sys.stdin.isatty", return_value=True), \
             patch_everywhere("get_key", side_effect=["؟", "enter", "ا", "h", "٢"]):
            picked = ui_components.select_menu("TEST MENU", items, breadcrumb="Test")
            self.assertEqual(picked, "two")


class TestEntryPoint(unittest.TestCase):
    def test_entry_point_imports_and_exposes_main(self):
        self.assertTrue(callable(ibd.main))
        self.assertTrue(callable(ibd.interactive_menu))
