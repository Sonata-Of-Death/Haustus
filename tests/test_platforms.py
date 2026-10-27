# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import core.archive as core_archive
import core.cookies as core_cookies
import core.urls as core_urls
import platforms.facebook as platforms_facebook
import platforms.pinterest as platforms_pinterest
import platforms.spotify as platforms_spotify
import platforms.threads as platforms_threads
import platforms.twitch as platforms_twitch
from core.config import ConfigManager

sys.path.insert(0, os.path.dirname(__file__))
from helpers import patch_everywhere, restore_config_mgr, swap_config_mgr


class TestFacebookAndPinterestFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_fb_pin_cfg.json")
        self.cfg = ConfigManager(self.cfg_path)
        self.cfg.set_archive_missing_policy("skip")
        self._orig_cfg = swap_config_mgr(self.cfg)

    def tearDown(self):
        restore_config_mgr(self._orig_cfg)
        self.tmp_dir.cleanup()

    def test_is_facebook_url(self):
        self.assertTrue(core_urls.is_facebook_url("https://www.facebook.com/reel/123456789/"))
        self.assertTrue(core_urls.is_facebook_url("https://fb.watch/xyz123/"))
        self.assertTrue(core_urls.is_facebook_url("https://facebook.com/watch/?v=987654321"))
        self.assertTrue(core_urls.is_facebook_url("https://www.facebook.com/share/r/abcDEF/"))
        self.assertFalse(core_urls.is_facebook_url("https://www.instagram.com/reel/abc/"))

    def test_is_pinterest_url(self):
        self.assertTrue(core_urls.is_pinterest_url("https://www.pinterest.com/pin/123456789/"))
        self.assertTrue(core_urls.is_pinterest_url("https://pin.it/7dK2G4H"))
        self.assertTrue(core_urls.is_pinterest_url("https://www.pinterest.com/designer/room-ideas/"))
        self.assertFalse(core_urls.is_pinterest_url("https://www.youtube.com/watch?v=123"))

    def test_extract_url_item_id_facebook_and_pinterest(self):
        plat_fb, id_fb1 = core_archive.extract_url_item_id("https://www.facebook.com/reel/123456789/")
        self.assertEqual(plat_fb, "facebook")
        self.assertEqual(id_fb1, "123456789")

        plat_fb, id_fb2 = core_archive.extract_url_item_id("https://facebook.com/watch/?v=987654321")
        self.assertEqual(plat_fb, "facebook")
        self.assertEqual(id_fb2, "987654321")

        plat_fb, id_fb3 = core_archive.extract_url_item_id("https://fb.watch/xyz123/")
        self.assertEqual(plat_fb, "facebook")
        self.assertEqual(id_fb3, "xyz123")

        plat_pin, id_pin1 = core_archive.extract_url_item_id("https://www.pinterest.com/pin/555666777/")
        self.assertEqual(plat_pin, "pinterest")
        self.assertEqual(id_pin1, "555666777")

        plat_pin, id_pin2 = core_archive.extract_url_item_id("https://pin.it/7dK2G4H")
        self.assertEqual(plat_pin, "pinterest")
        self.assertEqual(id_pin2, "7dK2G4H")

    def test_resolve_short_links_mocked(self):
        mock_resp_fb = unittest.mock.MagicMock()
        mock_resp_fb.url = "https://www.facebook.com/reel/999888777/"

        with unittest.mock.patch("requests.head", return_value=mock_resp_fb):
            resolved = platforms_facebook.resolve_facebook_url("https://fb.watch/xyz123/")
            self.assertEqual(resolved, "https://www.facebook.com/reel/999888777/")

        mock_resp_pin = unittest.mock.MagicMock()
        mock_resp_pin.url = "https://www.pinterest.com/pin/111222333/"

        with unittest.mock.patch("requests.head", return_value=mock_resp_pin):
            resolved_pin = platforms_pinterest.resolve_pinterest_url("https://pin.it/abcDEF")
            self.assertEqual(resolved_pin, "https://www.pinterest.com/pin/111222333/")

    def test_facebook_cookie_preparation(self):
        raw_cookie = "c_user=1000987654; xs=secret_xs_session_value;"
        c_path = core_cookies.prepare_facebook_cookies(raw_cookie)
        self.assertIsNotNone(c_path)
        self.assertTrue(os.path.isfile(c_path))

        with open(c_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".facebook.com", content)
        self.assertIn("c_user", content)
        self.assertIn("1000987654", content)
        self.assertIn("xs", content)

        profiles = self.cfg.get_cookie_profiles("facebook")
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "@1000987654")

    def test_pinterest_cookie_preparation(self):
        raw_cookie = "_pinterest_sess=TW96aWxsYTAxMjM0NQ==;"
        c_path = core_cookies.prepare_pinterest_cookies(raw_cookie)
        self.assertIsNotNone(c_path)
        self.assertTrue(os.path.isfile(c_path))

        with open(c_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".pinterest.com", content)
        self.assertIn("_pinterest_sess", content)

        profiles = self.cfg.get_cookie_profiles("pinterest")
        self.assertEqual(len(profiles), 1)

    def test_process_facebook_item_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None
        mock_ydl.download.return_value = 0
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None
        mock_ydl.extract_info.return_value = {"id": "123456", "title": "FB Reel"}

        with unittest.mock.patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            res = platforms_facebook.process_facebook_item(
                "https://www.facebook.com/reel/123456/",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
            self.assertIn("facebook 123456", archive_set)

            # Test duplicate skip
            res2 = platforms_facebook.process_facebook_item(
                "https://www.facebook.com/reel/123456/",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res2, core_archive.RESULT_SKIPPED)

    def test_process_pinterest_photo_pin_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None

        pin_info = {
            "id": "pin777",
            "title": "Minimalist Room Design",
            "description": "Clean interior decor",
            "uploader": "architect_daily",
            "formats": [],  # static photo pin
            "thumbnails": [
                {"url": "https://i.pinimg.com/736x/ab/cd/ef/abcdef.jpg", "width": 736, "height": 1000}
            ]
        }
        mock_ydl.extract_info.return_value = pin_info

        with unittest.mock.patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch_everywhere("download_file", return_value=True):
            res = platforms_pinterest.process_pinterest_pin(
                "https://www.pinterest.com/pin/pin777/",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
            self.assertIn("pinterest pin777", archive_set)

            # Verify metadata.json was written
            meta_path = os.path.join(self.tmp_dir.name, "pinterest_pin777_metadata.json")
            self.assertTrue(os.path.isfile(meta_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            self.assertEqual(meta_data["id"], "pin777")
            self.assertEqual(meta_data["title"], "Minimalist Room Design")
            self.assertIn("/originals/", meta_data["image_url"])


class TestTwitchAndThreadsFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp_dir.name, "test_config_tw_th.json")
        self.cfg = ConfigManager(self.cfg_path)
        self.cfg.set_archive_missing_policy("skip")
        self._orig_cfg = swap_config_mgr(self.cfg)

    def tearDown(self):
        restore_config_mgr(self._orig_cfg)
        self.tmp_dir.cleanup()

    def test_twitch_url_validators_and_id_extraction(self):
        url_clip = "https://clips.twitch.tv/EnergeticSillyLlama"
        url_clip2 = "https://www.twitch.tv/streamer/clip/AwesomeClip-xyz"
        url_vod = "https://www.twitch.tv/videos/987654321"
        url_chan = "https://www.twitch.tv/ninja"

        self.assertTrue(core_urls.is_twitch_url(url_clip))
        self.assertTrue(core_urls.is_twitch_url(url_clip2))
        self.assertTrue(core_urls.is_twitch_url(url_vod))
        self.assertTrue(core_urls.is_twitch_url(url_chan))

        plat1, id1 = core_archive.extract_url_item_id(url_clip)
        self.assertEqual(plat1, "twitch")
        self.assertEqual(id1, "EnergeticSillyLlama")

        plat2, id2 = core_archive.extract_url_item_id(url_clip2)
        self.assertEqual(plat2, "twitch")
        self.assertEqual(id2, "AwesomeClip-xyz")

        plat3, id3 = core_archive.extract_url_item_id(url_vod)
        self.assertEqual(plat3, "twitch")
        self.assertEqual(id3, "987654321")

    def test_threads_url_validators_and_id_extraction(self):
        url_post = "https://www.threads.net/@zuck/post/C4_32abcde"
        url_post2 = "https://www.threads.net/t/C4_32abcde?xmt=AQGz"
        url_com = "https://threads.com/@creator/post/xyz123"

        self.assertTrue(core_urls.is_threads_url(url_post))
        self.assertTrue(core_urls.is_threads_url(url_post2))
        self.assertTrue(core_urls.is_threads_url(url_com))

        plat1, id1 = core_archive.extract_url_item_id(url_post)
        self.assertEqual(plat1, "threads")
        self.assertEqual(id1, "C4_32abcde")

        plat2, id2 = core_archive.extract_url_item_id(url_post2)
        self.assertEqual(plat2, "threads")
        self.assertEqual(id2, "C4_32abcde")

    def test_twitch_cookie_formatting_and_saving(self):
        raw_token = "twitch_oauth_secret_token_123456"
        c_path = core_cookies.prepare_twitch_cookies(raw_token)
        self.assertIsNotNone(c_path)
        self.assertTrue(os.path.isfile(c_path))

        with open(c_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".twitch.tv", content)
        self.assertIn("auth-token", content)

        profiles = self.cfg.get_cookie_profiles("twitch")
        self.assertEqual(len(profiles), 1)

    def test_threads_cookie_formatting_and_saving(self):
        raw_cookie = "sessionid=test_threads_session; ds_user_id=1234567"
        c_path = core_cookies.prepare_threads_cookies(raw_cookie)
        self.assertIsNotNone(c_path)
        self.assertTrue(os.path.isfile(c_path))

        with open(c_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".threads.net", content)
        self.assertIn("sessionid", content)

        profiles = self.cfg.get_cookie_profiles("threads")
        self.assertEqual(len(profiles), 1)

    def test_process_twitch_item_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None
        mock_ydl.download.return_value = 0
        mock_ydl.extract_info.return_value = {"id": "TestClip123", "title": "Epic Gaming Clip"}

        with unittest.mock.patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            res = platforms_twitch.process_twitch_item(
                "https://clips.twitch.tv/TestClip123",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
            self.assertIn("twitch TestClip123", archive_set)

            # Test duplicate skip
            res2 = platforms_twitch.process_twitch_item(
                "https://clips.twitch.tv/TestClip123",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res2, core_archive.RESULT_SKIPPED)

    def test_process_threads_photo_item_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None

        thread_info = {
            "id": "TH_POST_99",
            "title": "A beautiful sunset post",
            "description": "Captured this on the weekend",
            "uploader": "photographer_pro",
            "formats": [],  # static photo post
            "thumbnails": [
                {"url": "https://scontent.cdninstagram.com/v/t51.2885-15/sunset.jpg", "width": 1080, "height": 1080}
            ]
        }
        mock_ydl.extract_info.return_value = thread_info

        with unittest.mock.patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
             patch_everywhere("download_file", return_value=True):
            res = platforms_threads.process_threads_item(
                "https://www.threads.net/@photographer_pro/post/TH_POST_99",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
            self.assertIn("threads TH_POST_99", archive_set)

            # Verify metadata.json was written
            meta_path = os.path.join(self.tmp_dir.name, "threads_TH_POST_99_metadata.json")
            self.assertTrue(os.path.isfile(meta_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            self.assertEqual(meta_data["id"], "TH_POST_99")
            self.assertEqual(meta_data["uploader"], "photographer_pro")
            self.assertEqual(meta_data["title"], "A beautiful sunset post")


class TestSpotifyFeatures(unittest.TestCase):
    """Unit tests for Spotify integration, metadata extraction, audio matching, and cookie verification."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp_dir.name, "test_config.json")
        self.cfg = ConfigManager(self.config_path)
        self.cfg.set_archive_missing_policy("skip")
        self._orig_cfg = swap_config_mgr(self.cfg)

    def tearDown(self):
        restore_config_mgr(self._orig_cfg)
        self.tmp_dir.cleanup()

    def test_is_spotify_url_and_resolve(self):
        valid_urls = [
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
            "https://open.spotify.com/album/2ANVost0y2y52ema1E9xAZ",
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            "https://open.spotify.com/episode/2LK6f4oCeGauchNieHQhtf",
            "https://open.spotify.com/show/4rOoJ6Egrf8K2IrywzwOMk",
            "https://open.spotify.com/artist/1dfeR4HaWDbWqFsssgavss",
            "https://spotify.link/AbCdEf123",
            "spotify:track:4cOdK2wGLETKBW3PvgPWqT",
            "spotify:album:2ANVost0y2y52ema1E9xAZ",
        ]
        for u in valid_urls:
            self.assertTrue(core_urls.is_spotify_url(u), f"Failed for {u}")

        self.assertFalse(core_urls.is_spotify_url("https://www.youtube.com/watch?v=12345"))
        self.assertFalse(core_urls.is_spotify_url("https://soundcloud.com/artist/track"))

        # Resolve URI to open.spotify.com
        res = platforms_spotify.resolve_spotify_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(res, "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")

        # Strip query params
        res2 = platforms_spotify.resolve_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123xyz")
        self.assertEqual(res2, "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")

    def test_extract_url_item_id_spotify(self):
        plat, item_id = core_archive.extract_url_item_id("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "4cOdK2wGLETKBW3PvgPWqT")

        plat, item_id = core_archive.extract_url_item_id("https://open.spotify.com/album/2ANVost0y2y52ema1E9xAZ")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "2ANVost0y2y52ema1E9xAZ")

        plat, item_id = core_archive.extract_url_item_id("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "37i9dQZF1DXcBWIGoYBM5M")

        plat, item_id = core_archive.extract_url_item_id("https://open.spotify.com/episode/2LK6f4oCeGauchNieHQhtf")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "2LK6f4oCeGauchNieHQhtf")

        plat, item_id = core_archive.extract_url_item_id("https://open.spotify.com/show/4rOoJ6Egrf8K2IrywzwOMk")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "4rOoJ6Egrf8K2IrywzwOMk")

        plat, item_id = core_archive.extract_url_item_id("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(plat, "spotify")
        self.assertEqual(item_id, "4cOdK2wGLETKBW3PvgPWqT")

    def test_spotify_cookie_preparation_and_verification(self):
        # 1. Raw sp_dc token string
        cookie_file = core_cookies.prepare_spotify_cookies("AQB7_dummy_spotify_token_value_1234567890", save_profile=False)
        self.assertTrue(os.path.isfile(cookie_file))
        with open(cookie_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(".spotify.com", content)
        self.assertIn("sp_dc", content)
        self.assertIn("AQB7_dummy_spotify_token_value_1234567890", content)

        # 2. Verify valid session
        valid, msg = core_cookies.verify_spotify_session(cookie_file)
        self.assertTrue(valid)
        self.assertIn("sp_dc verified", msg)

        # 3. Invalid cookie file without sp_dc
        invalid_path = os.path.join(self.tmp_dir.name, "invalid_sp.txt")
        with open(invalid_path, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n.spotify.com\tTRUE\t/\tTRUE\t2147483647\tother_cookie\tvalue\n")
        valid, msg = core_cookies.verify_spotify_session(invalid_path)
        self.assertFalse(valid)
        self.assertIn("No sp_dc session cookie found", msg)

    def test_config_manager_spotify_integration(self):
        self.assertEqual(self.cfg._norm_plat("sp"), "spotify")
        self.assertEqual(self.cfg._norm_plat("spotify"), "spotify")

        profiles = self.cfg.get_cookie_profiles("spotify")
        self.assertEqual(len(profiles), 0)

        # Add profile
        dummy_netscape = "# Netscape HTTP Cookie File\n.spotify.com\tTRUE\t/\tTRUE\t2147483647\tsp_dc\tdummy_token\n"
        self.cfg.add_cookie_profile("spotify", "@spotify_premium", dummy_netscape, set_as_default=True)
        profiles = self.cfg.get_cookie_profiles("spotify")
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], "@spotify_premium")
        self.assertEqual(self.cfg.get_default_cookie_profile_name("spotify"), "@spotify_premium")

        # Effective cookie file
        eff_file = self.cfg.get_effective_cookie_file("spotify")
        self.assertTrue(os.path.isfile(eff_file))

        # Delete profile
        self.cfg.delete_cookie_profile("spotify", "@spotify_premium")
        self.assertEqual(len(self.cfg.get_cookie_profiles("spotify")), 0)

    def test_process_spotify_item_track_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None

        fake_meta = {
            "type": "track",
            "id": "track_test_123",
            "title": "Never Gonna Give You Up",
            "artist": "Rick Astley",
            "album": "Whenever You Need Somebody",
            "release_date": "1987-11-12",
            "cover_url": "https://example.com/cover.jpg",
            "preview_url": "https://example.com/preview.mp3",
            "track_list": []
        }

        with patch_everywhere("fetch_spotify_embed_metadata", return_value=fake_meta), \
             patch_everywhere("_download_single_spotify_audio", return_value=core_archive.RESULT_DOWNLOADED):
            res = platforms_spotify.process_spotify_item(
                "https://open.spotify.com/track/track_test_123",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)

        # Second run should skip if in archive
        archive_set.add("spotify track_test_123")
        with patch_everywhere("fetch_spotify_embed_metadata", return_value=fake_meta):
            res2 = platforms_spotify.process_spotify_item(
                "https://open.spotify.com/track/track_test_123",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set
            )
            self.assertEqual(res2, core_archive.RESULT_SKIPPED)

    def test_process_spotify_item_collection_mocked(self):
        archive_path = os.path.join(self.tmp_dir.name, "history.txt")
        archive_set = set()
        mock_ydl = unittest.mock.MagicMock()
        mock_ydl.params = {}
        mock_ydl.cookiejar = None

        fake_col_meta = {
            "type": "album",
            "id": "album_thriller_123",
            "title": "Thriller",
            "artist": "Michael Jackson",
            "album": "Thriller",
            "release_date": "1982-11-30",
            "cover_url": "https://example.com/thriller.jpg",
            "preview_url": None,
            "track_list": [
                {"id": "t1", "title": "Wanna Be Startin' Somethin'", "artist": "Michael Jackson", "duration": 363400, "preview_url": None},
                {"id": "t2", "title": "Baby Be Mine", "artist": "Michael Jackson", "duration": 260000, "preview_url": None},
            ]
        }

        with patch_everywhere("fetch_spotify_embed_metadata", return_value=fake_col_meta), \
             patch_everywhere("_download_single_spotify_audio", return_value=core_archive.RESULT_DOWNLOADED):
            res = platforms_spotify.process_spotify_item(
                "https://open.spotify.com/album/album_thriller_123",
                self.tmp_dir.name,
                mock_ydl,
                unittest.mock.MagicMock(),
                archive_path,
                archive_set,
                delay=0.0
            )
            self.assertEqual(res, core_archive.RESULT_DOWNLOADED)
