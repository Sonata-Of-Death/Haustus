# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console

import core.archive as core_archive
import features.downloader as features_downloader
import platforms.base as platforms_base
import platforms.instagram as platforms_instagram
import platforms.youtube as platforms_youtube
import ui.dashboard as ui_dashboard

sys.path.insert(0, os.path.dirname(__file__))

class TestLiveDashboardAndDownloaderEnhancements(unittest.TestCase):
    def test_ytdl_quiet_logger_suppresses_progress_and_captures_logs(self):
        console = Console(file=open(os.devnull, "w"), force_terminal=True)
        dash = ui_dashboard.RichLiveDownloadDashboard(console)
        logger = ui_dashboard.YtdlQuietLogger(dash)

        # Progress should be suppressed
        logger.info("[download]  45.0% of 10.00MiB at 2.50MiB/s ETA 00:02")
        self.assertEqual(len(dash._logs), 0)

        # Info message should be added
        logger.info("Extracting URL: https://example.com")
        self.assertEqual(len(dash._logs), 1)
        self.assertEqual(dash._logs[-1][0], "[INFO]")
        self.assertIn("Extracting URL", dash._logs[-1][1])

        # Warning message should be added
        logger.warning("Could not find subtitle stream")
        self.assertEqual(len(dash._logs), 2)
        self.assertEqual(dash._logs[-1][0], "[WARN]")

        # Benign warnings like --paths is ignored should be suppressed
        logger.warning("--paths is ignored since an absolute path is given in output template")
        self.assertEqual(len(dash._logs), 2)

        # Transient JSONDecodeError in error should be suppressed
        logger.error("ERROR: [Instagram] test: Failed to parse JSON (caused by JSONDecodeError('Expecting value'))")
        self.assertEqual(len(dash._logs), 2)

        # Error message should be added
        logger.error("HTTP 403 Forbidden")
        self.assertEqual(len(dash._logs), 3)
        self.assertEqual(dash._logs[-1][0], "[FAIL]")

    def test_hook_metric_fallbacks_speed_eta_and_estimated_size(self):
        console = Console(file=open(os.devnull, "w"), force_terminal=True)
        dash = ui_dashboard.RichLiveDownloadDashboard(console)
        dash.start_item(1, title="Test Stream", platform="Instagram")

        d_chunked = {
            "status": "downloading",
            "downloaded_bytes": 5 * 1024 * 1024,
            "total_bytes": None,
            "total_bytes_estimate": None,
            "speed": None,
            "_speed_str": " 2.50MiB/s",
            "eta": None,
            "_eta_str": "00:04",
            "_percent_str": " 50.0%",
            "filename": "chunked_stream.mp4"
        }
        dash.hook(d_chunked)

        self.assertAlmostEqual(dash._percent, 50.0, places=1)
        self.assertIn("MB", dash._speed_str)
        self.assertEqual(dash._eta_str, "00:04")
        self.assertIn("5.0 MB", dash._size_str)
        self.assertIn("10.0 MB", dash._size_str)

    def test_postprocessor_hook_stage_transitions(self):
        console = Console(file=open(os.devnull, "w"), force_terminal=True)
        dash = ui_dashboard.RichLiveDownloadDashboard(console)
        dash.start_item(1, title="Test Stream", platform="YouTube")

        d_merge = {
            "status": "started",
            "postprocessor": "FFmpegMerger",
            "info_dict": {"title": "Test Video"}
        }
        dash.postprocessor_hook(d_merge)
        self.assertEqual(dash._stage, "merge")
        self.assertEqual(dash._percent, 100.0)

        d_tag = {
            "status": "started",
            "postprocessor": "FFmpegMetadata",
            "info_dict": {"title": "Test Video"}
        }
        dash.postprocessor_hook(d_tag)
        self.assertEqual(dash._stage, "tag")

    def test_download_file_with_streaming_progress_callback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            save_path = os.path.join(tmp_dir, "test_file.bin")
            progress_events = []

            def _dummy_cb(d):
                progress_events.append(d)

            class MockStreamingResp:
                def __init__(self):
                    self.status_code = 200
                    self.headers = {"Content-Length": "30"}
                def iter_content(self, chunk_size=16384):
                    yield b"chunk_1_"
                    yield b"chunk_2_"
                    yield b"chunk_3_"

            mock_session = mock.MagicMock()
            mock_session.get.return_value = MockStreamingResp()

            ok = core_archive.download_file("https://example.com/file.bin", save_path, mock_session, progress_callback=_dummy_cb)
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(save_path))
            self.assertEqual(os.path.getsize(save_path), 24)
            self.assertTrue(any(e.get("status") == "finished" for e in progress_events))

    def test_check_disk_presence_with_min_mtime(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            start_t = time.time()
            test_file = os.path.join(tmp_dir, "fresh_download.mp4")
            with open(test_file, "wb") as f:
                f.write(b"data")

            self.assertTrue(core_archive.check_disk_presence(tmp_dir, "unknown_id", min_mtime=start_t - 1.0))
            self.assertFalse(core_archive.check_disk_presence(tmp_dir, "unknown_id", min_mtime=start_t + 100.0))

    def test_check_disk_presence_mode_awareness(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_f = os.path.join(tmp_dir, "youtube_artist_vid123_track.mp3")
            with open(audio_f, "wb") as f:
                f.write(b"audio_bytes")

            # Check that audio mode sees it, but video mode does not
            self.assertTrue(core_archive.check_disk_presence(tmp_dir, "vid123", mode="audio"))
            self.assertFalse(core_archive.check_disk_presence(tmp_dir, "vid123", mode="video"))
            self.assertTrue(core_archive.check_disk_presence(tmp_dir, "vid123", mode=None))

    def test_is_archived_mode_switch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_f = os.path.join(tmp_dir, "youtube_artist_vid999_title.mp3")
            with open(audio_f, "wb") as f:
                f.write(b"audio_bytes")

            archive_set = {"youtube vid999"}
            # Audio mode is already present on disk -> True (skipped)
            self.assertTrue(core_archive.is_archived(archive_set, "vid999", "youtube", output_dir=tmp_dir, mode="audio"))
            # Video mode was never downloaded -> False (mode-switch allows download)
            self.assertFalse(core_archive.is_archived(archive_set, "vid999", "youtube", output_dir=tmp_dir, mode="video"))

    def test_filter_playlist_items(self):
        entries = [{"id": f"item_{i}"} for i in range(1, 11)]

        # Positive selection
        res1 = platforms_base.filter_playlist_items(entries, "1,3,5")
        self.assertEqual([e["id"] for e in res1], ["item_1", "item_3", "item_5"])

        # Range selection
        res2 = platforms_base.filter_playlist_items(entries, "2-5")
        self.assertEqual([e["id"] for e in res2], ["item_2", "item_3", "item_4", "item_5"])

        # Exclusion
        res3 = platforms_base.filter_playlist_items(entries, "~2,~4")
        self.assertEqual([e["id"] for e in res3], ["item_1", "item_3", "item_5", "item_6", "item_7", "item_8", "item_9", "item_10"])

        # Combined range and exclusion
        res4 = platforms_base.filter_playlist_items(entries, "1-5,~3")
        self.assertEqual([e["id"] for e in res4], ["item_1", "item_2", "item_4", "item_5"])

    def test_check_disk_presence_photo_carousel_folder_in_video_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            carousel_dir = os.path.join(tmp_dir, "instagram_creator_DZhsypslW2__photos")
            os.makedirs(carousel_dir, exist_ok=True)
            photo_file = os.path.join(carousel_dir, "photo_1.jpg")
            with open(photo_file, "wb") as f:
                f.write(b"jpeg_data")

            # In video mode, check_disk_presence should detect the photo carousel directory
            self.assertTrue(core_archive.check_disk_presence(tmp_dir, "DZhsypslW2_", mode="video"))
            self.assertTrue(core_archive.check_disk_presence(tmp_dir, "DZhsypslW2_", mode=None))

    def test_dashboard_batch_eta_calculation(self):
        console = Console(file=open(os.devnull, "w"), force_terminal=True)
        dash = ui_dashboard.RichLiveDownloadDashboard(console)
        dash.set_batch(1, 5)
        dash.start_item(1, title="Item 1", platform="Instagram")
        dash._batch_start_time = time.time() - 10.0
        dash.finish_item(1, "DONE")
        dash.start_item(2, title="Item 2", platform="Instagram")
        self.assertIsNotNone(dash._batch_eta_str)
        self.assertNotEqual(dash._batch_eta_str, "--:--")
        screen = dash._build_screen()
        with console.capture() as cap:
            console.print(screen)
        self.assertIn("Total ETA:", cap.get())

    def test_initial_skipped_in_download_urls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("features.downloader.print_summary_table") as mock_summary:
                res = features_downloader.download_urls([], output_dir=tmp_dir, initial_skipped=5)
                self.assertEqual(res, (0, 0, 5))
                mock_summary.assert_called_once()
                kwargs = mock_summary.call_args.kwargs
                self.assertEqual(kwargs.get("total"), 5)
                self.assertEqual(kwargs.get("succeeded"), 0)
                self.assertEqual(kwargs.get("skipped"), 5)

    def test_process_youtube_url_playlist_dashboard_queue(self):
        mock_dashboard = mock.MagicMock()
        mock_ydl = mock.MagicMock()
        entries = [
            {"id": "v1", "title": "Video One", "url": "https://youtube.com/watch?v=v1"},
            {"id": "v2", "title": "Video Two", "url": "https://youtube.com/watch?v=v2"},
        ]
        mock_info = {
            "_type": "playlist",
            "title": "Test Playlist",
            "entries": entries,
        }
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.params = {}
        mock_ydl.cookiejar = None
        with tempfile.TemporaryDirectory() as tmp_dir:
            archive_path = os.path.join(tmp_dir, "history.txt")
            archive_set = set()
            with mock.patch("platforms.youtube.check_disk_presence", return_value=True), \
                 mock.patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
                mock_sub = mock.MagicMock()
                mock_sub.download.return_value = 0
                mock_ydl_cls.return_value.__enter__.return_value = mock_sub
                res = platforms_youtube.process_youtube_url(
                    "https://youtube.com/playlist?list=PL123",
                    tmp_dir,
                    mock_ydl,
                    archive_path,
                    archive_set,
                    dashboard=mock_dashboard
                )
                mock_dashboard.init_queue.assert_called_once()
                queue_items = mock_dashboard.init_queue.call_args[0][0]
                self.assertEqual(len(queue_items), 2)
                self.assertEqual(queue_items[0], "Video One")
                self.assertEqual(queue_items[1], "Video Two")
                self.assertEqual(res[0], core_archive.RESULT_DOWNLOADED)
                self.assertEqual(res[1], 2)

    def test_remove_from_failed_urls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            failed_file = os.path.join(tmp_dir, "failed_urls.txt")
            with open(failed_file, "w", encoding="utf-8") as f:
                f.write("https://www.instagram.com/p/De4sHhSRGLO/\nhttps://www.instagram.com/p/De4yREpguz5/\n")

            # Remove first by full URL
            core_archive.remove_from_failed_urls(tmp_dir, "https://www.instagram.com/p/De4sHhSRGLO/")
            self.assertTrue(os.path.isfile(failed_file))
            with open(failed_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self.assertEqual(content, "https://www.instagram.com/p/De4yREpguz5/")

            # Remove second by item_id
            core_archive.remove_from_failed_urls(tmp_dir, "De4yREpguz5")
            self.assertFalse(os.path.exists(failed_file))

    def test_extract_instagram_info_anonymous_fallback(self):
        mock_ydl = mock.MagicMock()
        mock_ydl.params = {"cookiefile": "some_cookie.txt"}
        mock_ydl.cookiejar = None
        # Primary extraction fails with JSONDecodeError
        mock_ydl.extract_info.side_effect = Exception("JSONDecodeError: Expecting value in ''")

        with mock.patch("yt_dlp.extractor.get_info_extractor") as mock_get_ie, \
             mock.patch("yt_dlp.YoutubeDL") as mock_anon_cls:
            # First extractor (with cookies) fails
            mock_ie_instance = mock.MagicMock()
            mock_ie_instance.suitable.return_value = True
            mock_ie_instance._real_extract.side_effect = Exception("Failed to parse JSON")
            mock_get_ie.return_value.return_value = mock_ie_instance

            # Anonymous extractor succeeds
            mock_anon_ydl = mock.MagicMock()
            mock_anon_ydl.extract_info.return_value = {"id": "De4sHhSRGLO", "title": "Test Video"}
            mock_anon_cls.return_value.__enter__.return_value = mock_anon_ydl

            info, is_single = platforms_instagram.extract_instagram_info("https://www.instagram.com/p/De4sHhSRGLO/", mock_ydl)
            self.assertIsNotNone(info)
            self.assertEqual(info.get("id"), "De4sHhSRGLO")

if __name__ == "__main__":
    unittest.main()


