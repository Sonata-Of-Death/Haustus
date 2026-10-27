# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console

import core.archive as core_archive
import core.constants as core_constants
import core.cookies as core_cookies
import core.instances as core_instances
import core.urls as core_urls
import core.ytdl_format as core_ytdl_format
import features.settings as features_settings
import platforms.instagram as platforms_instagram
import platforms.reddit as platforms_reddit
import platforms.x_twitter as platforms_x_twitter
import platforms.youtube as platforms_youtube
import ui.components as ui_components
import ui.dashboard as ui_dashboard
import ui.quality as ui_quality
import ui.theme as ui_theme
from core.config import ConfigManager

sys.path.insert(0, os.path.dirname(__file__))
from helpers import patch_everywhere


class TestHelpers(unittest.TestCase):
    def test_prepare_youtube_cookies_header_string(self):
        header_str = "VISITOR_INFO1_LIVE=abc123xyz; LOGIN_INFO=AFmmF2kwRA...; SID=987"
        path = core_cookies.prepare_youtube_cookies(header_str, save_profile=False)
        try:
            self.assertIsNotNone(path)
            self.assertTrue(os.path.isfile(path))
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(".youtube.com", content)
            self.assertIn("VISITOR_INFO1_LIVE", content)
        finally:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_authenticated_youtube_cookie_detection(self):
        # Visitor-only cookies
        visitor_content = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1807687084\tVISITOR_INFO1_LIVE\tsSjICCW_qdU\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1792136634\tGPS\t1\n"
        )
        t_visitor = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
        t_visitor.write(visitor_content)
        t_visitor.close()
        try:
            self.assertFalse(core_cookies.is_authenticated_youtube_cookie_file(t_visitor.name))
        finally:
            if os.path.isfile(t_visitor.name):
                os.remove(t_visitor.name)

        # Authenticated cookies with LOGIN_INFO / SID
        auth_content = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1807687084\tLOGIN_INFO\tAFmmF2swRQ...\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1807687084\tSID\tabcdef123456\n"
        )
        t_auth = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
        t_auth.write(auth_content)
        t_auth.close()
        try:
            self.assertTrue(core_cookies.is_authenticated_youtube_cookie_file(t_auth.name))
        finally:
            if os.path.isfile(t_auth.name):
                os.remove(t_auth.name)

    def test_no_emojis_in_source_files(self):
        for path in ("haustus.py", "core/config.py", "core/constants.py", "core/instances.py", "core/archive.py", "core/cookies.py", "core/urls.py", "core/ytdl_format.py", "core/resilience.py", "core/engine.py", "core/media.py"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for ch in content:
                cp = ord(ch)
                is_emoji = (
                    (0x1F600 <= cp <= 0x1F64F) or (0x1F300 <= cp <= 0x1F5FF) or
                    (0x1F680 <= cp <= 0x1F6FF) or (0x1F700 <= cp <= 0x1F77F) or
                    (0x1F780 <= cp <= 0x1F7FF) or (0x1F800 <= cp <= 0x1F8FF) or
                    (0x1F900 <= cp <= 0x1F9FF) or (0x1FA00 <= cp <= 0x1FA6F) or
                    (0x1FA70 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x26FF) or
                    (0x2700 <= cp <= 0x27BF)
                )
                self.assertFalse(is_emoji, f"Emoji {repr(ch)} found in {path}")

    def test_core_instances_and_constants_decoupled_from_ui(self):
        """Verify core constants and runtime instances exist in core layer without depending on ui."""
        self.assertEqual(len(core_constants.PLATFORMS_REGISTRY), 11)
        self.assertIn("User-Agent", core_constants.HEADERS)
        self.assertIsNotNone(core_instances.config_mgr)
        self.assertIsNotNone(core_instances.media_maestro)
        self.assertIsNotNone(core_instances.network_mgr)

    def test_youtube_playlists_structure(self):
        playlists = platforms_youtube.fetch_youtube_user_playlists(cookie_file=None)
        self.assertIsInstance(playlists, list)
        self.assertGreaterEqual(len(playlists), 2)
        titles = [p["title"] for p in playlists]
        self.assertTrue(any("Watch Later" in t for t in titles))
        self.assertTrue(any("Liked" in t for t in titles))

    def test_ask_input_non_interactive(self):
        with unittest.mock.patch("builtins.input", return_value=""):
            res = ui_components.ask_input("Test prompt", default="fallback")
            self.assertEqual(res, "fallback")

    def test_render_current_settings_panel(self):
        tmp_cfg = ConfigManager()
        try:
            res = features_settings.render_current_settings_panel(tmp_cfg)
            rendered = (res is not None)
        except Exception:
            rendered = False
        self.assertTrue(rendered)

    def test_manage_configuration_menu_navigation(self):
        tmp_cfg = ConfigManager()
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.write"), \
             mock.patch("sys.stdout.flush"), \
             patch_everywhere("get_key", side_effect=["right", "down", "0"]):
            try:
                features_settings.manage_configuration_menu(tmp_cfg)
                success = True
            except Exception:
                success = False
            self.assertTrue(success)

    def test_manage_configuration_menu_wasd_enter(self):
        tmp_cfg = ConfigManager()
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.write"), \
             mock.patch("sys.stdout.flush"), \
             patch_everywhere("get_key", side_effect=["d", "s", "d", "d", "enter"]):
            try:
                features_settings.manage_configuration_menu(tmp_cfg)
                success = True
            except Exception:
                success = False
            self.assertTrue(success)

    def test_x_url_detection(self):
        self.assertTrue(core_urls.is_x_url("https://x.com/user/status/1234567890"))
        self.assertTrue(core_urls.is_x_url("https://twitter.com/user/status/1234567890"))
        self.assertFalse(core_urls.is_x_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(core_urls.is_x_url("https://www.tiktok.com/@user/video/123456"))

    def test_extract_url_item_id_x(self):
        plat, item_id = core_archive.extract_url_item_id("https://x.com/elonmusk/status/1880000000000000000")
        self.assertEqual(plat, "x")
        self.assertEqual(item_id, "1880000000000000000")

        plat2, item_id2 = core_archive.extract_url_item_id("https://twitter.com/jack/status/20")
        self.assertEqual(plat2, "x")
        self.assertEqual(item_id2, "20")

    def test_prepare_x_cookies(self):
        # 1. Header string
        c_path = core_cookies.prepare_x_cookies("auth_token=abcdef0123456789; ct0=xyz987654321", save_profile=False)
        self.assertIsNotNone(c_path)
        self.assertTrue(os.path.isfile(c_path))
        with open(c_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".x.com", content)
        self.assertIn(".twitter.com", content)
        self.assertIn("auth_token", content)
        self.assertIn("ct0", content)

        # 2. Raw token value
        raw_token = "4b2f1e0a8d7c6b5a4b3c2d1e0f9a8b7c6d5e4f3a"
        c_path2 = core_cookies.prepare_x_cookies(raw_token, save_profile=False)
        self.assertIsNotNone(c_path2)
        with open(c_path2, "r", encoding="utf-8") as f:
            content2 = f.read()
        self.assertIn(raw_token, content2)

    def test_parse_x_data_archive(self):
        sample_js = 'window.YTD.bookmark.part0 = [{"bookmark": {"tweetId": "188111222333444555"}}, {"bookmark": {"tweetId": "188999888777666555"}}]'
        urls = platforms_x_twitter.parse_x_data_archive(sample_js, kind="bookmarks")
        self.assertEqual(len(urls), 2)
        self.assertIn("https://x.com/i/status/188111222333444555", urls)
        self.assertIn("https://x.com/i/status/188999888777666555", urls)

    def test_x_cookie_profile_crud(self):
        tmp_cfg = ConfigManager()
        tmp_file = os.path.join(tempfile.gettempdir(), "test_x_cookie.txt")
        with open(tmp_file, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")

        # Add profile using 'x'
        tmp_cfg.add_cookie_profile("x", "@x_tester", tmp_file, set_as_default=True)
        self.assertEqual(tmp_cfg.get_default_cookie_profile_name("x"), "@x_tester")
        # Verify normalization of 'twitter' to 'x'
        self.assertEqual(tmp_cfg.get_default_cookie_profile_name("twitter"), "@x_tester")

        # Cleanup
        tmp_cfg.delete_cookie_profile("x", "@x_tester")
        if os.path.isfile(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

    def test_instagram_reposts_constants_and_helpers(self):
        self.assertEqual(core_archive.DEFAULT_INSTAGRAM_REPOSTS_DIR, "my_instagram_reposts")
        self.assertEqual(core_archive.DEFAULT_INSTAGRAM_SAVED_DIR, "my_saved_posts")

        eff = core_cookies.get_effective_instagram_cookie_file("non_existent_file.txt")
        self.assertTrue(eff is None or os.path.isfile(eff))

    def test_parse_instagram_reposts_json_structured(self):
        sample_json = json.dumps({
            "reposted_posts": [
                {
                    "title": "sample_creator",
                    "string_list_data": [
                        {
                            "href": "https://www.instagram.com/reel/C3abc123DEF/",
                            "timestamp": 1700000000
                        }
                    ]
                },
                {
                    "title": "another_creator",
                    "media_list_data": [
                        {
                            "href": "https://www.instagram.com/p/C4xyz789GHI/",
                            "timestamp": 1700000500
                        }
                    ]
                }
            ]
        })
        urls = platforms_instagram.parse_instagram_reposts_json(sample_json)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://www.instagram.com/p/C3abc123DEF/", urls)
        self.assertIn("https://www.instagram.com/p/C4xyz789GHI/", urls)

    def test_parse_instagram_reposts_json_regex_fallback(self):
        unstructured = (
            "Here is my exported data from instagram: "
            "found repost at https://www.instagram.com/p/C5uvw123XYZ/ and reel "
            "https://www.instagram.com/reel/C6rst456UVW/ in user archive."
        )
        urls = platforms_instagram.parse_instagram_reposts_json(unstructured)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://www.instagram.com/p/C5uvw123XYZ/", urls)
        self.assertIn("https://www.instagram.com/p/C6rst456UVW/", urls)

    def test_embed_metadata_config(self):
        tmp_cfg = ConfigManager()
        tmp_cfg.set_default_embed_metadata(True)
        self.assertTrue(tmp_cfg.get_default_embed_metadata())
        tmp_cfg.set_default_embed_metadata(False)
        self.assertFalse(tmp_cfg.get_default_embed_metadata())
        tmp_cfg.set_default_embed_metadata(None)
        self.assertIsNone(tmp_cfg.get_default_embed_metadata())

    def test_speed_limiter_config_and_bytes_parsing(self):
        tmp_cfg = ConfigManager()
        tmp_cfg.set_default_speed_limit("5M")
        self.assertEqual(tmp_cfg.get_default_speed_limit(), "5M")
        self.assertEqual(tmp_cfg.get_speed_limit_bytes(), 5 * 1024 * 1024)

        tmp_cfg.set_default_speed_limit("500K")
        self.assertEqual(tmp_cfg.get_speed_limit_bytes(), 500 * 1024)

        tmp_cfg.set_default_speed_limit("unlimited")
        self.assertIsNone(tmp_cfg.get_speed_limit_bytes())

        tmp_cfg.set_default_speed_limit(None)
        self.assertIsNone(tmp_cfg.get_speed_limit_bytes())

    def test_no_notifications_in_config(self):
        tmp_cfg = ConfigManager()
        self.assertNotIn("notifications", tmp_cfg.data)
        self.assertFalse(hasattr(tmp_cfg, "get_notification_settings"))

    def test_zero_default_cookie_profiles(self):
        tmp_cfg = ConfigManager()
        platforms = ["instagram", "tiktok", "youtube", "x", "soundcloud", "reddit", "facebook", "pinterest", "twitch", "threads", "spotify"]
        for p in platforms:
            profs = tmp_cfg.get_cookie_profiles(p)
            for prof in profs:
                self.assertNotIn("user", prof["name"].lower())
                self.assertNotIn("default", prof["name"].lower())

    def test_rich_live_download_dashboard_lifecycle(self):
        """Test RichLiveDownloadDashboard progress tracking without raising errors."""
        dashboard = ui_dashboard.RichLiveDownloadDashboard(ui_theme.console)
        # Test download hook
        dashboard.hook({
            "status": "downloading",
            "filename": "test_video_file.mp4",
            "downloaded_bytes": 2048576,
            "total_bytes": 10485760,
            "speed": 1048576,
            "eta": 8
        })
        # Test finished hook
        dashboard.hook({
            "status": "finished",
            "filename": "test_video_file.mp4",
            "downloaded_bytes": 10485760,
            "total_bytes": 10485760
        })
        dashboard.stop()
        self.assertIsNone(dashboard._progress)

    def test_make_progress_bar_unicode_and_ascii(self):
        """Verify make_progress_bar renders proper characters in Unicode and ASCII fallback."""
        # Unicode rendering
        orig_ascii = os.environ.get("UI_ASCII")
        try:
            if "UI_ASCII" in os.environ:
                del os.environ["UI_ASCII"]
            bar_text = ui_theme.make_progress_bar(50.0, width=20)
            self.assertIn("━", bar_text.plain)

            # ASCII rendering
            os.environ["UI_ASCII"] = "1"
            bar_ascii = ui_theme.make_progress_bar(50.0, width=20)
            self.assertIn("=", bar_ascii.plain)
            self.assertIn("-", bar_ascii.plain)
        finally:
            if orig_ascii is not None:
                os.environ["UI_ASCII"] = orig_ascii
            elif "UI_ASCII" in os.environ:
                del os.environ["UI_ASCII"]

    def test_rich_live_download_dashboard_full_redesign_features(self):
        """Verify full redesign dashboard features: queue, batch, current, logs, and zero emojis."""
        test_console = Console(width=100, record=True)
        dashboard = ui_dashboard.RichLiveDownloadDashboard(test_console)
        urls = [
            "https://www.youtube.com/watch?v=video1",
            "https://www.tiktok.com/@user/video/222222",
            "https://www.instagram.com/reel/333333/"
        ]
        dashboard.init_queue(urls)
        self.assertEqual(len(dashboard._queue), 3)

        dashboard.set_batch(current=1, total=3, done=0, skip=0, fail=0)
        dashboard.start_item(1, title="YouTube Video 1", platform="YouTube", mode="VIDEO", quality="1080p")
        dashboard.hook({
            "status": "downloading",
            "filename": "video1.mp4",
            "downloaded_bytes": 5242880,
            "total_bytes": 10485760,
            "speed": 2097152,
            "eta": 2.5,
            "info_dict": {"title": "Full YouTube Video Title"}
        })
        self.assertEqual(dashboard._current_title, "Full YouTube Video Title")
        self.assertEqual(dashboard._stage, "download")

        # Test finish item
        dashboard.finish_item(1, status="DONE", log_msg="Saved: Full YouTube Video Title", done=1, skip=0, fail=0)
        self.assertEqual(dashboard._done_count, 1)
        self.assertEqual(dashboard._queue[0]["status"], "DONE")

        # Start item 2 as SKIP
        dashboard.set_batch(current=2, total=3, done=1, skip=0, fail=0)
        dashboard.start_item(2, title="TikTok Video 2", platform="TikTok", mode="AUDIO", quality="320k")
        dashboard.finish_item(2, status="SKIP", log_msg="Skipped: already downloaded", done=1, skip=1, fail=0)
        self.assertEqual(dashboard._skip_count, 1)
        self.assertEqual(dashboard._queue[1]["status"], "SKIP")

        # Verify screen layout rendering in wide mode
        screen_wide = dashboard._build_screen()
        test_console.print(screen_wide)
        rendered_text = test_console.export_text()
        self.assertIn("HAUSTUS", rendered_text)
        self.assertIn("BATCH", rendered_text)
        self.assertIn("CURRENT", rendered_text)
        self.assertIn("QUEUE", rendered_text)
        self.assertIn("LOG", rendered_text)
        self.assertIn("[Ctrl+C] Stop after current item", rendered_text)

        # Verify screen layout rendering in narrow mode (< 76 cols)
        narrow_console = Console(width=60, record=True)
        narrow_dashboard = ui_dashboard.RichLiveDownloadDashboard(narrow_console)
        narrow_dashboard.init_queue(urls)
        narrow_dashboard.start_item(1, title="Narrow Title", platform="IG", mode="VIDEO", quality="best")
        screen_narrow = narrow_dashboard._build_screen()
        narrow_console.print(screen_narrow)
        narrow_rendered = narrow_console.export_text()
        self.assertIn("CURRENT", narrow_rendered)
        self.assertIn("BATCH", narrow_rendered)

        # Strictly zero emojis check
        for c in rendered_text:
            self.assertFalse(0x1F300 <= ord(c) <= 0x1F9FF, f"Emoji detected in dashboard: {c}")

    def test_resolve_embed_metadata_presets(self):
        """Verify resolve_embed_metadata honors config without prompting."""
        orig_pref = ui_theme.config_mgr.get_default_embed_metadata()
        try:
            ui_theme.config_mgr.set_default_embed_metadata(True)
            self.assertTrue(ui_quality.resolve_embed_metadata())

            ui_theme.config_mgr.set_default_embed_metadata(False)
            self.assertFalse(ui_quality.resolve_embed_metadata())
        finally:
            ui_theme.config_mgr.set_default_embed_metadata(orig_pref)

    def test_detect_account_username_auto_fetch(self):
        """Verify detect_account_username fetches handle automatically without user input."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Instagram with ds_user_id
            ig_cookie = os.path.join(tmp_dir, "ig_cookie.txt")
            with open(ig_cookie, "w") as f:
                f.write("# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t1999999999\tds_user_id\t987654321\n")
            u = core_cookies.detect_account_username("instagram", ig_cookie)
            self.assertEqual(u, "@user_987654321")

            # 2. Twitch with login cookie
            tw_cookie = os.path.join(tmp_dir, "tw_cookie.txt")
            with open(tw_cookie, "w") as f:
                f.write("# Netscape HTTP Cookie File\n.twitch.tv\tTRUE\t/\tTRUE\t1999999999\tlogin\tstreamer_pro\n")
            u2 = core_cookies.detect_account_username("twitch", tw_cookie)
            self.assertEqual(u2, "@streamer_pro")

    def test_get_ydl_format_metadata_postprocessors(self):
        """Verify get_ydl_format includes FFmpegMetadata and EmbedThumbnail when embed_metadata is True."""
        # Video mode with metadata
        fmt, pps = core_ytdl_format.get_ydl_format(mode="video", video_quality="1080", embed_metadata=True)
        self.assertTrue(any(p.get("key") == "FFmpegMetadata" for p in pps))
        self.assertTrue(any(p.get("key") == "EmbedThumbnail" for p in pps))

        # Audio mode with metadata
        fmt_a, pps_a = core_ytdl_format.get_ydl_format(mode="audio", audio_format="mp3", audio_quality="320", embed_metadata=True)
        self.assertTrue(any(p.get("key") == "FFmpegMetadata" for p in pps_a))
        self.assertTrue(any(p.get("key") == "EmbedThumbnail" for p in pps_a))

        # Video mode without metadata
        fmt_no, pps_no = core_ytdl_format.get_ydl_format(mode="video", video_quality="1080", embed_metadata=False)
        self.assertEqual(len(pps_no), 0)

    def test_archive_config_defaults_and_setters(self):
        """Verify archive mode getters, setters and fallback default values."""
        tmp_path = os.path.join(tempfile.gettempdir(), f"test_arch_defaults_{os.getpid()}.json")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        tmp_cfg = ConfigManager(tmp_path)
        # Defaults
        self.assertEqual(tmp_cfg.get_archive_bulk_mode(), "always")
        self.assertEqual(tmp_cfg.get_archive_single_mode(), "disabled")
        self.assertEqual(tmp_cfg.get_archive_missing_policy(), "prompt")

        # Setters & validations
        tmp_cfg.set_archive_bulk_mode("disabled")
        self.assertEqual(tmp_cfg.get_archive_bulk_mode(), "disabled")
        tmp_cfg.set_archive_bulk_mode("prompt")
        self.assertEqual(tmp_cfg.get_archive_bulk_mode(), "prompt")

        tmp_cfg.set_archive_single_mode("always")
        self.assertEqual(tmp_cfg.get_archive_single_mode(), "always")
        tmp_cfg.set_archive_single_mode("prompt")
        self.assertEqual(tmp_cfg.get_archive_single_mode(), "prompt")

        tmp_cfg.set_archive_missing_policy("skip")
        self.assertEqual(tmp_cfg.get_archive_missing_policy(), "skip")
        tmp_cfg.set_archive_missing_policy("redownload")
        self.assertEqual(tmp_cfg.get_archive_missing_policy(), "redownload")

    def test_resolve_archive_policy(self):
        """Verify resolve_archive_policy logic based on bulk vs single mode settings."""
        orig_bulk = ui_theme.config_mgr.get_archive_bulk_mode()
        orig_single = ui_theme.config_mgr.get_archive_single_mode()
        try:
            ui_theme.config_mgr.set_archive_bulk_mode("always")
            self.assertTrue(core_archive.resolve_archive_policy(is_bulk=True))

            ui_theme.config_mgr.set_archive_bulk_mode("disabled")
            self.assertFalse(core_archive.resolve_archive_policy(is_bulk=True))

            ui_theme.config_mgr.set_archive_single_mode("disabled")
            self.assertFalse(core_archive.resolve_archive_policy(is_bulk=False))

            ui_theme.config_mgr.set_archive_single_mode("always")
            self.assertTrue(core_archive.resolve_archive_policy(is_bulk=False))
        finally:
            ui_theme.config_mgr.set_archive_bulk_mode(orig_bulk)
            ui_theme.config_mgr.set_archive_single_mode(orig_single)

    def test_is_archived_missing_file_logic(self):
        """Verify smart detection of deleted files and missing file policies."""
        with tempfile.TemporaryDirectory() as tmp_out:
            archive_set = {"youtube test_vid_123"}
            core_archive.reset_missing_decision_cache()

            # 1. Not in archive
            self.assertFalse(core_archive.is_archived(archive_set, "unknown_vid", "youtube", output_dir=tmp_out))

            # 2. In archive, file physically present on disk
            sample_file = os.path.join(tmp_out, "video_test_vid_123.mp4")
            with open(sample_file, "wb") as f:
                f.write(b"x" * 2048)  # > 1024 bytes
            self.assertTrue(core_archive.is_archived(archive_set, "test_vid_123", "youtube", output_dir=tmp_out))

            # 3. File deleted from disk!
            os.remove(sample_file)
            self.assertFalse(core_archive.check_disk_presence(tmp_out, "test_vid_123"))

            # When prompt_missing=False (inventory scan), should report False (missing from disk)
            self.assertFalse(core_archive.is_archived(archive_set, "test_vid_123", "youtube", output_dir=tmp_out, prompt_missing=False))

            # With policy = 'skip', should treat as intentionally deleted (skip re-downloading -> return True)
            orig_pol = ui_theme.config_mgr.get_archive_missing_policy()
            try:
                ui_theme.config_mgr.set_archive_missing_policy("skip")
                core_archive.reset_missing_decision_cache()
                self.assertTrue(core_archive.is_archived(archive_set, "test_vid_123", "youtube", output_dir=tmp_out))

                # With policy = 'redownload', should proceed to download -> return False
                ui_theme.config_mgr.set_archive_missing_policy("redownload")
                core_archive.reset_missing_decision_cache()
                self.assertFalse(core_archive.is_archived(archive_set, "test_vid_123", "youtube", output_dir=tmp_out))
            finally:
                ui_theme.config_mgr.set_archive_missing_policy(orig_pol)
                core_archive.reset_missing_decision_cache()

    def test_session_missing_decision_caching(self):
        """Verify in-session skip_all and redownload_all flags prevent repeated questions."""
        with tempfile.TemporaryDirectory() as tmp_out:
            archive_set = {"youtube vid_a", "youtube vid_b"}
            core_archive.reset_missing_decision_cache()

            # Set session decision to skip_all
            core_archive._missing_file_session_decision = "skip_all"
            self.assertTrue(core_archive.is_archived(archive_set, "vid_a", "youtube", output_dir=tmp_out))
            self.assertTrue(core_archive.is_archived(archive_set, "vid_b", "youtube", output_dir=tmp_out))

            # Set session decision to redownload_all
            core_archive._missing_file_session_decision = "redownload_all"
            self.assertFalse(core_archive.is_archived(archive_set, "vid_a", "youtube", output_dir=tmp_out))
            self.assertFalse(core_archive.is_archived(archive_set, "vid_b", "youtube", output_dir=tmp_out))

            # Reset cache
            core_archive.reset_missing_decision_cache()
            self.assertIsNone(core_archive._missing_file_session_decision)

    def test_soundcloud_url_detection(self):
        """Verify SoundCloud track, set, artist, and likes URLs are recognized."""
        valid_urls = [
            "https://soundcloud.com/artist/track-name",
            "https://soundcloud.com/artist/sets/album-name",
            "https://soundcloud.com/artist",
            "https://soundcloud.com/artist/likes",
            "https://snd.sc/abc1234",
        ]
        for u in valid_urls:
            self.assertTrue(core_urls.is_soundcloud_url(u), f"Failed to match valid SoundCloud URL: {u}")

        invalid_urls = [
            "https://www.youtube.com/watch?v=123",
            "https://www.instagram.com/reel/123",
            "https://www.reddit.com/r/videos",
        ]
        for u in invalid_urls:
            self.assertFalse(core_urls.is_soundcloud_url(u), f"False positive for SoundCloud URL: {u}")

    def test_reddit_url_detection(self):
        """Verify Reddit comments, gallery, redd.it, and v.redd.it URLs are recognized."""
        valid_urls = [
            "https://www.reddit.com/r/technology/comments/123456/sample_post/",
            "https://reddit.com/gallery/789xyz",
            "https://v.redd.it/abcdef12345",
            "https://redd.it/sampleid",
        ]
        for u in valid_urls:
            self.assertTrue(core_urls.is_reddit_url(u), f"Failed to match valid Reddit URL: {u}")

        invalid_urls = [
            "https://soundcloud.com/artist/track",
            "https://twitter.com/user/status/123",
        ]
        for u in invalid_urls:
            self.assertFalse(core_urls.is_reddit_url(u), f"False positive for Reddit URL: {u}")

    def test_extract_url_item_id_soundcloud_reddit(self):
        """Verify ID extraction for SoundCloud tracks and Reddit posts."""
        plat, sc_id = core_archive.extract_url_item_id("https://soundcloud.com/chopin/nocturne-op9")
        self.assertEqual(plat, "soundcloud")
        self.assertEqual(sc_id, "chopin_nocturne-op9")

        plat_sc2, sc_id2 = core_archive.extract_url_item_id("https://snd.sc/short123")
        self.assertEqual(plat_sc2, "soundcloud")
        self.assertEqual(sc_id2, "short123")

        plat_rd, rd_id = core_archive.extract_url_item_id("https://www.reddit.com/r/pics/comments/abc123z/my_photo/")
        self.assertEqual(plat_rd, "reddit")
        self.assertEqual(rd_id, "abc123z")

        plat_rd2, rd_id2 = core_archive.extract_url_item_id("https://redd.it/xyz987")
        self.assertEqual(plat_rd2, "reddit")
        self.assertEqual(rd_id2, "xyz987")

    def test_soundcloud_cookie_management(self):
        """Verify SoundCloud cookie token formatting and profile management."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            cfg_path = f.name
        try:
            cfg = ConfigManager(cfg_path)
            self.assertEqual(cfg.get_cookie_profiles("soundcloud"), [])

            raw_token = "2-293482-123456789-abcdefg"
            cfg.add_cookie_profile("soundcloud", "@sc_test", f"oauth_token={raw_token}", set_as_default=True)
            profiles = cfg.get_cookie_profiles("soundcloud")
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["name"], "@sc_test")
            self.assertEqual(cfg.get_default_cookie_profile_name("soundcloud"), "@sc_test")

            eff_file = cfg.get_effective_cookie_file("soundcloud")
            self.assertIsNotNone(eff_file)
            self.assertTrue(os.path.isfile(eff_file))
            with open(eff_file, "r") as cf:
                content = cf.read()
            self.assertIn("oauth_token", content)
            self.assertIn(raw_token, content)
        finally:
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)

    def test_reddit_cookie_management(self):
        """Verify Reddit session cookie formatting and profile management."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            cfg_path = f.name
        try:
            cfg = ConfigManager(cfg_path)
            self.assertEqual(cfg.get_cookie_profiles("reddit"), [])

            raw_session = "12345678%2C2026-10-21%2Cabcd1234efgh5678"
            cfg.add_cookie_profile("reddit", "@rd_test", f"reddit_session={raw_session}", set_as_default=True)
            profiles = cfg.get_cookie_profiles("reddit")
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["name"], "@rd_test")
            self.assertEqual(cfg.get_default_cookie_profile_name("reddit"), "@rd_test")

            eff_file = cfg.get_effective_cookie_file("reddit")
            self.assertIsNotNone(eff_file)
            self.assertTrue(os.path.isfile(eff_file))
            with open(eff_file, "r") as cf:
                content = cf.read()
            self.assertIn("reddit_session", content)
            self.assertIn(raw_session, content)
        finally:
            if os.path.isfile(cfg_path):
                os.remove(cfg_path)

    def test_reddit_gallery_download(self):
        """Verify Reddit image gallery folder creation, image saving, and metadata.json."""
        with tempfile.TemporaryDirectory() as tmp_out:
            gallery_post = {
                "id": "gal123",
                "subreddit": "EarthPorn",
                "author": "nature_photographer",
                "title": "Stunning Mountain Sunrise",
                "permalink": "/r/EarthPorn/comments/gal123/stunning_mountain_sunrise/",
                "created_utc": 1690000000,
                "score": 4500,
                "upvote_ratio": 0.98,
                "is_gallery": True,
                "gallery_data": {
                    "items": [
                        {"media_id": "img_001"},
                        {"media_id": "img_002"}
                    ]
                },
                "media_metadata": {
                    "img_001": {
                        "s": {"u": "https://preview.redd.it/mock1.jpg?width=1920&amp;format=pjpg"}
                    },
                    "img_002": {
                        "s": {"u": "https://preview.redd.it/mock2.jpg?width=1920&amp;format=pjpg"}
                    }
                }
            }

            class MockResponse:
                def __init__(self):
                    self.status_code = 200
                def iter_content(self, chunk_size=16384):
                    yield b"fake_jpeg_image_data"

            mock_session = unittest.mock.MagicMock()
            mock_session.get.return_value = MockResponse()

            archive_path = os.path.join(tmp_out, ".download_history.txt")
            archive_set = set()

            res = platforms_reddit.download_reddit_gallery(gallery_post, tmp_out, mock_session, archive_path, archive_set)
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
            self.assertIn("reddit gal123", archive_set)

            # Check created gallery subfolder
            expected_folder = os.path.join(tmp_out, "reddit_EarthPorn_gal123_gallery")
            self.assertTrue(os.path.isdir(expected_folder))

            # Check metadata.json
            meta_file = os.path.join(expected_folder, "metadata.json")
            self.assertTrue(os.path.isfile(meta_file))
            with open(meta_file, "r", encoding="utf-8") as f:
                saved_meta = json.load(f)
            self.assertEqual(saved_meta["id"], "gal123")
            self.assertEqual(saved_meta["subreddit"], "EarthPorn")
            self.assertEqual(saved_meta["author"], "nature_photographer")
            self.assertEqual(saved_meta["item_count"], 2)

            # Check image files
            img1 = os.path.join(expected_folder, "01_img_001.jpg")
            img2 = os.path.join(expected_folder, "02_img_002.jpg")
            self.assertTrue(os.path.isfile(img1))
            self.assertTrue(os.path.isfile(img2))

    def test_reddit_feed_fetching_mocked(self):
        """Verify fetch_reddit_feed_posts queries API and extracts normalized post items."""
        mock_api_payload = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "feed_post_1",
                            "title": "Tech Breakthrough",
                            "author": "tech_lead",
                            "subreddit": "technology",
                            "permalink": "/r/technology/comments/feed_post_1/tech_breakthrough/",
                            "is_video": True,
                            "created_utc": 1695000000,
                            "score": 1200,
                            "upvote_ratio": 0.95
                        }
                    }
                ],
                "after": None
            }
        }

        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_api_payload

        with unittest.mock.patch("requests.Session.get", return_value=mock_resp):
            posts = platforms_reddit.fetch_reddit_feed_posts("r/technology", sort="hot", limit=10)
            self.assertEqual(len(posts), 1)
            p = posts[0]
            self.assertEqual(p["id"], "feed_post_1")
            self.assertEqual(p["title"], "Tech Breakthrough")
            self.assertEqual(p["author"], "tech_lead")
            self.assertEqual(p["subreddit"], "technology")
            self.assertTrue(p["is_video"])
